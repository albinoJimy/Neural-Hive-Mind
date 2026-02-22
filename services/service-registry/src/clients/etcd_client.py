import json
import asyncio
from typing import Dict, List, Optional, Callable
from uuid import UUID
import etcd3
import structlog
from src.models import AgentInfo, AgentType


logger = structlog.get_logger()


class EtcdClient:
    """Cliente assíncrono para operações com etcd"""

    def __init__(self, endpoints: List[str], prefix: str, timeout: int):
        self.endpoints = endpoints
        self.prefix = prefix
        self.timeout = timeout
        self.client: Optional[etcd3.Etcd3Client] = None
        self._watch_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Inicializa conexão com cluster etcd"""
        try:
            # Parse first endpoint
            host, port = self.endpoints[0].replace("http://", "").split(":")
            self.client = etcd3.client(host=host, port=int(port), timeout=self.timeout)

            # Test connection
            await asyncio.to_thread(self.client.status)
            logger.info("etcd_client_initialized", endpoints=self.endpoints)

        except Exception as e:
            logger.error("etcd_client_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fecha conexão com etcd"""
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        if self.client:
            await asyncio.to_thread(self.client.close)
            logger.info("etcd_client_closed")

    async def put_agent(self, agent_info: AgentInfo) -> bool:
        """Salva informações do agente no etcd"""
        try:
            key = agent_info.get_etcd_key(self.prefix)
            value = json.dumps(agent_info.to_proto_dict())

            await asyncio.to_thread(self.client.put, key, value)
            logger.info(
                "agent_stored_in_etcd",
                agent_id=str(agent_info.agent_id),
                agent_type=agent_info.agent_type.value,
                key=key
            )
            return True

        except Exception as e:
            logger.error(
                "etcd_put_agent_failed",
                agent_id=str(agent_info.agent_id),
                error=str(e)
            )
            raise

    async def get_agent(self, agent_id: UUID) -> Optional[AgentInfo]:
        """Busca informações do agente no etcd"""
        try:
            # Try all agent types
            for agent_type in AgentType:
                key = f"{self.prefix}/{agent_type.value.lower()}/{str(agent_id)}"
                value, _ = await asyncio.to_thread(self.client.get, key)

                if value:
                    data = json.loads(value.decode('utf-8'))
                    return AgentInfo.from_proto_dict(data)

            logger.warning("agent_not_found_in_etcd", agent_id=str(agent_id))
            return None

        except Exception as e:
            logger.error("etcd_get_agent_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Remove agente do etcd"""
        try:
            # Try all agent types
            deleted = False
            for agent_type in AgentType:
                key = f"{self.prefix}/{agent_type.value.lower()}/{str(agent_id)}"
                result = await asyncio.to_thread(self.client.delete, key)
                if result:
                    deleted = True
                    logger.info(
                        "agent_deleted_from_etcd",
                        agent_id=str(agent_id),
                        agent_type=agent_type.value
                    )

            return deleted

        except Exception as e:
            logger.error("etcd_delete_agent_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def list_agents(
        self,
        agent_type: Optional[AgentType] = None,
        filters: Optional[Dict[str, str]] = None
    ) -> List[AgentInfo]:
        """Lista agentes com filtros opcionais"""
        try:
            agents = []

            # Define prefixes to scan
            if agent_type:
                prefixes = [f"{self.prefix}/{agent_type.value.lower()}/"]
            else:
                prefixes = [f"{self.prefix}/{t.value.lower()}/" for t in AgentType]

            # Scan each prefix
            for prefix in prefixes:
                items = await asyncio.to_thread(
                    self.client.get_prefix,
                    prefix
                )

                for value, _ in items:
                    data = json.loads(value.decode('utf-8'))
                    agent = AgentInfo.from_proto_dict(data)

                    # Apply filters
                    if filters:
                        if not self._matches_filters(agent, filters):
                            continue

                    agents.append(agent)

            logger.info(
                "agents_listed_from_etcd",
                count=len(agents),
                agent_type=agent_type.value if agent_type else "all"
            )
            return agents

        except Exception as e:
            logger.error("etcd_list_agents_failed", error=str(e))
            raise

    def _matches_filters(self, agent: AgentInfo, filters: Dict[str, str]) -> bool:
        """
        Verifica se agente atende aos filtros.

        Suporta filtros de:
        - namespace: campo direto do AgentInfo
        - cluster: campo direto do AgentInfo
        - version: campo direto do AgentInfo
        - status: campo direto do AgentStatus (com suporte a HEALTHY/DEGRADED)
        - security_level: campo armazenado no metadata
        """
        for key, value in filters.items():
            if key == "namespace" and agent.namespace != value:
                return False
            if key == "cluster" and agent.cluster != value:
                return False
            if key == "version" and agent.version != value:
                return False
            # Filtro de status: aceita HEALTHY ou DEGRADED como fallback
            # Isso permite que workers degradados sejam considerados quando
            # não há workers totalmente saudáveis disponíveis
            if key == "status":
                # Se filtro é "HEALTHY", aceita tanto HEALTHY quanto DEGRADED
                if value == "HEALTHY":
                    if agent.status not in (AgentStatus.HEALTHY, AgentStatus.DEGRADED):
                        return False
                # Para outros valores de status, faz comparação exata
                elif agent.status.value != value:
                    return False
            # Filtro de security_level: verifica no metadata do agente
            if key == "security_level":
                agent_security_level = agent.metadata.get("security_level", "INTERNAL")
                if agent_security_level != value:
                    return False

        return True

    async def watch_agents(self, callback: Callable[[str, Dict], None]) -> None:
        """Observa mudanças em agentes usando watch API do etcd"""
        try:
            watch_id = await asyncio.to_thread(
                self.client.add_watch_prefix_callback,
                self.prefix,
                callback
            )
            logger.info("etcd_watch_started", prefix=self.prefix, watch_id=watch_id)

        except Exception as e:
            logger.error("etcd_watch_failed", error=str(e))
            raise

    async def health_check(self) -> bool:
        """Verifica conectividade com etcd"""
        try:
            await asyncio.to_thread(self.client.status)
            return True
        except Exception as e:
            logger.error("etcd_health_check_failed", error=str(e))
            return False
