"""
Redis-based Registry Client

Substitui o etcd_client.py para eliminar a dependência do etcd3
que é incompatível com protobuf >= 4.0.

Mantém a mesma interface do EtcdClient para compatibilidade.
"""

import json
import asyncio
from typing import Dict, List, Optional, Callable
from uuid import UUID
import redis.asyncio as redis
import structlog
from src.models import AgentInfo, AgentType, AgentStatus

logger = structlog.get_logger()


class RedisRegistryClient:
    """Cliente assíncrono para operações de registro com Redis"""

    def __init__(self, cluster_nodes: List[str], prefix: str, password: str = "", timeout: int = 5):
        self.cluster_nodes = cluster_nodes
        self.prefix = prefix
        self.password = password
        self.timeout = timeout
        self.client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._watch_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Inicializa conexão com Redis"""
        try:
            host, port = self.cluster_nodes[0].split(":")
            self.client = redis.Redis(
                host=host,
                port=int(port),
                password=self.password if self.password else None,
                decode_responses=True,
                socket_timeout=self.timeout,
                socket_connect_timeout=self.timeout
            )

            # Test connection
            await self.client.ping()
            logger.info("redis_registry_client_initialized", nodes=self.cluster_nodes)

        except Exception as e:
            logger.error("redis_registry_client_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fecha conexão com Redis"""
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        if self.client:
            await self.client.close()
            logger.info("redis_registry_client_closed")

    def _get_agent_key(self, agent_type: AgentType, agent_id: str) -> str:
        """Gera chave Redis para o agente"""
        return f"{self.prefix}:{agent_type.value.lower()}:{agent_id}"

    async def put_agent(self, agent_info: AgentInfo) -> bool:
        """Salva informações do agente no Redis"""
        try:
            key = self._get_agent_key(agent_info.agent_type, str(agent_info.agent_id))
            value = json.dumps(agent_info.to_proto_dict())

            # Salvar com TTL de 5 minutos (heartbeat deve renovar)
            await self.client.setex(key, 300, value)

            # Adicionar ao set de agentes por tipo para listagem rápida
            type_set_key = f"{self.prefix}:index:{agent_info.agent_type.value.lower()}"
            await self.client.sadd(type_set_key, str(agent_info.agent_id))

            # Publicar evento de registro
            await self.client.publish(
                f"{self.prefix}:events",
                json.dumps({"event": "registered", "agent_id": str(agent_info.agent_id)})
            )

            logger.info(
                "agent_stored_in_redis",
                agent_id=str(agent_info.agent_id),
                agent_type=agent_info.agent_type.value,
                key=key
            )
            return True

        except Exception as e:
            logger.error(
                "redis_put_agent_failed",
                agent_id=str(agent_info.agent_id),
                error=str(e)
            )
            raise

    async def get_agent(self, agent_id: UUID) -> Optional[AgentInfo]:
        """Busca informações do agente no Redis"""
        try:
            # Try all agent types
            for agent_type in AgentType:
                key = self._get_agent_key(agent_type, str(agent_id))
                value = await self.client.get(key)

                if value:
                    data = json.loads(value)
                    return AgentInfo.from_proto_dict(data)

            logger.warning("agent_not_found_in_redis", agent_id=str(agent_id))
            return None

        except Exception as e:
            logger.error("redis_get_agent_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Remove agente do Redis"""
        try:
            deleted = False
            for agent_type in AgentType:
                key = self._get_agent_key(agent_type, str(agent_id))
                result = await self.client.delete(key)

                if result:
                    deleted = True
                    # Remover do índice
                    type_set_key = f"{self.prefix}:index:{agent_type.value.lower()}"
                    await self.client.srem(type_set_key, str(agent_id))

                    # Publicar evento de desregistro
                    await self.client.publish(
                        f"{self.prefix}:events",
                        json.dumps({"event": "deregistered", "agent_id": str(agent_id)})
                    )

                    logger.info(
                        "agent_deleted_from_redis",
                        agent_id=str(agent_id),
                        agent_type=agent_type.value
                    )

            return deleted

        except Exception as e:
            logger.error("redis_delete_agent_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def list_agents(
        self,
        agent_type: Optional[AgentType] = None,
        filters: Optional[Dict[str, str]] = None
    ) -> List[AgentInfo]:
        """Lista agentes com filtros opcionais"""
        try:
            agents = []

            # Define types to scan
            types_to_scan = [agent_type] if agent_type else list(AgentType)

            for at in types_to_scan:
                # Usar índice para listagem rápida
                type_set_key = f"{self.prefix}:index:{at.value.lower()}"
                agent_ids = await self.client.smembers(type_set_key)

                for aid in agent_ids:
                    key = self._get_agent_key(at, aid)
                    value = await self.client.get(key)

                    if value:
                        data = json.loads(value)
                        agent = AgentInfo.from_proto_dict(data)

                        # Apply filters
                        if filters and not self._matches_filters(agent, filters):
                            continue

                        agents.append(agent)
                    else:
                        # Agent expirou, remover do índice
                        await self.client.srem(type_set_key, aid)

            logger.info(
                "agents_listed_from_redis",
                count=len(agents),
                agent_type=agent_type.value if agent_type else "all"
            )
            return agents

        except Exception as e:
            logger.error("redis_list_agents_failed", error=str(e))
            raise

    def _matches_filters(self, agent: AgentInfo, filters: Dict[str, str]) -> bool:
        """Verifica se agente atende aos filtros"""
        for key, value in filters.items():
            if key == "namespace" and agent.namespace != value:
                return False
            if key == "cluster" and agent.cluster != value:
                return False
            if key == "version" and agent.version != value:
                return False
            if key == "status" and agent.status.value != value:
                return False

        return True

    async def watch_agents(self, callback: Callable[[str, Dict], None]) -> None:
        """Observa mudanças em agentes usando pub/sub do Redis"""
        try:
            self._pubsub = self.client.pubsub()
            await self._pubsub.subscribe(f"{self.prefix}:events")

            async def listen():
                async for message in self._pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            callback(data.get("event", "unknown"), data)
                        except Exception as e:
                            logger.error("watch_callback_error", error=str(e))

            self._watch_task = asyncio.create_task(listen())
            logger.info("redis_watch_started", prefix=self.prefix)

        except Exception as e:
            logger.error("redis_watch_failed", error=str(e))
            raise

    async def heartbeat(self, agent_id: UUID, agent_type: AgentType) -> bool:
        """Renova TTL do agente (heartbeat)"""
        try:
            key = self._get_agent_key(agent_type, str(agent_id))

            # Verificar se agente existe
            if not await self.client.exists(key):
                logger.warning("heartbeat_agent_not_found", agent_id=str(agent_id))
                return False

            # Renovar TTL para 5 minutos
            await self.client.expire(key, 300)

            logger.debug("heartbeat_renewed", agent_id=str(agent_id))
            return True

        except Exception as e:
            logger.error("heartbeat_failed", agent_id=str(agent_id), error=str(e))
            return False

    async def health_check(self) -> bool:
        """Verifica conectividade com Redis"""
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))
            return False


# Alias para compatibilidade com código existente
EtcdClient = RedisRegistryClient
