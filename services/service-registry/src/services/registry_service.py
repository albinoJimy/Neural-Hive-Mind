import structlog
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Dict, List, Optional
from src.models import AgentInfo, AgentType, AgentStatus, AgentTelemetry
from src.clients import EtcdClient
from prometheus_client import Counter, Histogram


logger = structlog.get_logger()


# Métricas Prometheus
agents_registered_total = Counter(
    'agents_registered_total',
    'Total de agentes registrados',
    ['agent_type']
)

agents_deregistered_total = Counter(
    'agents_deregistered_total',
    'Total de agentes desregistrados',
    ['agent_type']
)

heartbeats_received_total = Counter(
    'heartbeats_received_total',
    'Total de heartbeats recebidos',
    ['agent_type', 'status']
)

heartbeat_latency_seconds = Histogram(
    'heartbeat_latency_seconds',
    'Latência de processamento de heartbeat'
)

registry_operations_total = Counter(
    'registry_operations_total',
    'Total de operações do registry',
    ['operation', 'status']
)


class RegistryService:
    """Serviço principal de registro de agentes"""

    def __init__(self, etcd_client: EtcdClient):
        self.etcd_client = etcd_client

    async def register_agent(
        self,
        agent_type: AgentType,
        capabilities: List[str],
        metadata: Dict[str, str],
        namespace: str = "default",
        cluster: str = "local",
        version: str = "1.0.0"
    ) -> tuple[UUID, str]:
        """
        Registra um novo agente no registry.

        Returns:
            tuple[agent_id, registration_token]
        """
        try:
            # Validações
            if not capabilities:
                raise ValueError("Capabilities não podem estar vazias")

            if not metadata.get("namespace") and not namespace:
                raise ValueError("Namespace é obrigatório")

            # Criar AgentInfo
            agent_info = AgentInfo(
                agent_id=uuid4(),
                agent_type=agent_type,
                capabilities=capabilities,
                metadata=metadata,
                namespace=namespace,
                cluster=cluster,
                version=version,
                status=AgentStatus.HEALTHY,
                registered_at=int(datetime.now(timezone.utc).timestamp()),
                last_seen=int(datetime.now(timezone.utc).timestamp())
            )

            # Salvar no etcd
            await self.etcd_client.put_agent(agent_info)

            # Gerar registration token (simplificado - em produção usar JWT)
            registration_token = f"token-{agent_info.agent_id}"

            # Métricas
            agents_registered_total.labels(agent_type=agent_type.value).inc()
            registry_operations_total.labels(operation="register", status="success").inc()

            logger.info(
                "agent_registered",
                agent_id=str(agent_info.agent_id),
                agent_type=agent_type.value,
                capabilities=capabilities,
                namespace=namespace
            )

            return agent_info.agent_id, registration_token

        except Exception as e:
            registry_operations_total.labels(operation="register", status="error").inc()
            logger.error("agent_registration_failed", error=str(e))
            raise

    @heartbeat_latency_seconds.time()
    async def update_heartbeat(
        self,
        agent_id: UUID,
        telemetry: Optional[AgentTelemetry] = None
    ) -> AgentStatus:
        """
        Atualiza heartbeat do agente e recalcula health status.

        Returns:
            AgentStatus atualizado
        """
        try:
            # Buscar agente
            agent_info = await self.etcd_client.get_agent(agent_id)
            if not agent_info:
                raise ValueError(f"Agente {agent_id} não encontrado")

            # Atualizar last_seen
            agent_info.last_seen = int(datetime.now(timezone.utc).timestamp())

            # Atualizar telemetria se fornecida
            if telemetry:
                agent_info.telemetry = telemetry

            # Recalcular health status baseado em telemetria
            if agent_info.telemetry.success_rate < 0.3:
                agent_info.status = AgentStatus.UNHEALTHY
            elif agent_info.telemetry.success_rate < 0.5:
                agent_info.status = AgentStatus.DEGRADED
            else:
                agent_info.status = AgentStatus.HEALTHY

            # Salvar no etcd
            await self.etcd_client.put_agent(agent_info)

            # Métricas
            heartbeats_received_total.labels(
                agent_type=agent_info.agent_type.value,
                status=agent_info.status.value
            ).inc()
            registry_operations_total.labels(operation="heartbeat", status="success").inc()

            logger.debug(
                "heartbeat_updated",
                agent_id=str(agent_id),
                status=agent_info.status.value,
                success_rate=agent_info.telemetry.success_rate
            )

            return agent_info.status

        except Exception as e:
            registry_operations_total.labels(operation="heartbeat", status="error").inc()
            logger.error("heartbeat_update_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def deregister_agent(self, agent_id: UUID) -> bool:
        """
        Remove agente do registry.

        Returns:
            True se removido com sucesso
        """
        try:
            # Buscar agente para obter tipo (para métricas)
            agent_info = await self.etcd_client.get_agent(agent_id)

            # Remover do etcd
            deleted = await self.etcd_client.delete_agent(agent_id)

            if deleted and agent_info:
                # Métricas
                agents_deregistered_total.labels(
                    agent_type=agent_info.agent_type.value
                ).inc()
                registry_operations_total.labels(operation="deregister", status="success").inc()

                logger.info(
                    "agent_deregistered",
                    agent_id=str(agent_id),
                    agent_type=agent_info.agent_type.value
                )

            return deleted

        except Exception as e:
            registry_operations_total.labels(operation="deregister", status="error").inc()
            logger.error("agent_deregistration_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def get_agent(self, agent_id: UUID) -> Optional[AgentInfo]:
        """Retorna informações de um agente específico"""
        try:
            agent_info = await self.etcd_client.get_agent(agent_id)
            registry_operations_total.labels(operation="get_agent", status="success").inc()
            return agent_info

        except Exception as e:
            registry_operations_total.labels(operation="get_agent", status="error").inc()
            logger.error("get_agent_failed", agent_id=str(agent_id), error=str(e))
            raise

    async def list_agents(
        self,
        agent_type: Optional[AgentType] = None,
        filters: Optional[Dict[str, str]] = None
    ) -> List[AgentInfo]:
        """Lista agentes com filtros opcionais"""
        try:
            agents = await self.etcd_client.list_agents(agent_type, filters)
            registry_operations_total.labels(operation="list_agents", status="success").inc()

            logger.info(
                "agents_listed",
                count=len(agents),
                agent_type=agent_type.value if agent_type else "all"
            )

            return agents

        except Exception as e:
            registry_operations_total.labels(operation="list_agents", status="error").inc()
            logger.error("list_agents_failed", error=str(e))
            raise
