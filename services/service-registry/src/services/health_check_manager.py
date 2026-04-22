import asyncio
from datetime import UTC, datetime
from typing import Optional

import structlog
from prometheus_client import REGISTRY, Counter, Gauge
from src.clients.autocura_producer import AutocuraEventProducer
from src.clients.redis_registry_client import RedisRegistryClient
from src.models import AgentStatus, AgentType

logger = structlog.get_logger()


def _get_or_create_counter(name: str, description: str, labelnames=None):
    """Get existing counter or create new one to avoid duplicate registration errors"""
    try:
        return Counter(name, description, labelnames or [])
    except ValueError:
        return REGISTRY._names_to_collectors.get(name)


def _get_or_create_gauge(name: str, description: str, labelnames=None):
    """Get existing gauge or create new one to avoid duplicate registration errors"""
    try:
        return Gauge(name, description, labelnames or [])
    except ValueError:
        return REGISTRY._names_to_collectors.get(name)


# Métricas Prometheus
health_checks_total = _get_or_create_counter(
    "health_checks_total", "Total de health checks executados"
)

agents_marked_unhealthy_total = _get_or_create_counter(
    "agents_marked_unhealthy_total", "Total de agentes marcados como unhealthy", ["agent_type"]
)

agents_removed_total = _get_or_create_counter(
    "agents_removed_total", "Total de agentes removidos por inatividade", ["agent_type"]
)

agents_active = _get_or_create_gauge(
    "agents_active", "Número de agentes ativos", ["agent_type", "status"]
)


class HealthCheckManager:
    """Gerenciador de health checks periódicos para agentes"""

    def __init__(
        self,
        redis_client: RedisRegistryClient,
        check_interval_seconds: int,
        heartbeat_timeout_seconds: int,
        autocura_producer: Optional[AutocuraEventProducer] = None,
    ):
        self.redis_client = redis_client
        self.check_interval = check_interval_seconds
        self.heartbeat_timeout = heartbeat_timeout_seconds
        self.autocura_producer = autocura_producer
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._unhealthy_counts = {}  # agent_id -> consecutive_unhealthy_count

    async def start(self) -> None:
        """Inicia o loop de health checks"""
        if self._running:
            logger.warning("health_check_manager_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._health_check_loop())
        logger.info(
            "health_check_manager_started",
            interval_seconds=self.check_interval,
            timeout_seconds=self.heartbeat_timeout,
        )

    async def stop(self) -> None:
        """Para o loop de health checks gracefully"""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("health_check_manager_stopped")

    async def _health_check_loop(self) -> None:
        """Loop principal de health checks"""
        while self._running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_check_loop_error", error=str(e))
                await asyncio.sleep(self.check_interval)

    async def _perform_health_checks(self) -> None:
        """Executa verificação de saúde em todos os agentes"""
        try:
            health_checks_total.inc()

            # Listar todos os agentes
            all_agents = await self.redis_client.list_agents()

            # Resetar gauges
            for agent_type in AgentType:
                for status in AgentStatus:
                    agents_active.labels(agent_type=agent_type.value, status=status.value).set(0)

            current_time = int(datetime.now(UTC).timestamp())

            for agent in all_agents:
                # Verificar se agente está expirado
                time_since_last_seen = current_time - agent.last_seen

                if time_since_last_seen > self.heartbeat_timeout:
                    await self._handle_expired_agent(agent, time_since_last_seen)
                else:
                    # Agente está saudável, resetar contador
                    self._unhealthy_counts.pop(str(agent.agent_id), None)

                # Atualizar gauge
                agents_active.labels(
                    agent_type=agent.agent_type.value, status=agent.status.value
                ).inc()

            logger.info(
                "health_checks_completed",
                total_agents=len(all_agents),
                unhealthy_tracked=len(self._unhealthy_counts),
            )

        except Exception as e:
            logger.error("perform_health_checks_failed", error=str(e))
            raise

    async def _handle_expired_agent(self, agent, time_since_last_seen: int) -> None:
        """Trata agente expirado (sem heartbeat)"""
        agent_id_str = str(agent.agent_id)

        # Incrementar contador de unhealthy consecutivos
        unhealthy_count = self._unhealthy_counts.get(agent_id_str, 0) + 1
        self._unhealthy_counts[agent_id_str] = unhealthy_count

        logger.warning(
            "agent_expired",
            agent_id=agent_id_str,
            agent_type=agent.agent_type.value,
            time_since_last_seen=time_since_last_seen,
            unhealthy_count=unhealthy_count,
        )

        # Ciclo 1: Marcar como UNHEALTHY
        if unhealthy_count == 1:
            agent.status = AgentStatus.UNHEALTHY
            await self.redis_client.put_agent(agent)

            agents_marked_unhealthy_total.labels(agent_type=agent.agent_type.value).inc()

            logger.info(
                "agent_marked_unhealthy", agent_id=agent_id_str, agent_type=agent.agent_type.value
            )

        # Ciclo 2: Marcar como DEGRADED e notificar autocura
        elif unhealthy_count == 2:
            agent.status = AgentStatus.DEGRADED
            await self.redis_client.put_agent(agent)

            # TODO: Publicar evento para motor de autocura
            await self._notify_autocura(agent)

            logger.warning(
                "agent_marked_degraded", agent_id=agent_id_str, agent_type=agent.agent_type.value
            )

        # Ciclo 5+: Remover do registry
        elif unhealthy_count >= 5:
            await self.redis_client.delete_agent(agent.agent_id)
            self._unhealthy_counts.pop(agent_id_str, None)

            agents_removed_total.labels(agent_type=agent.agent_type.value).inc()

            logger.error(
                "agent_removed",
                agent_id=agent_id_str,
                agent_type=agent.agent_type.value,
                reason="prolonged_inactivity",
            )

    async def _notify_autocura(self, agent) -> None:
        """
        Notifica motor de autocura sobre agente degradado.

        Publica evento no Kafka para o Self-Healing Engine.
        """
        logger.info(
            "autocura_notification_sending",
            agent_id=str(agent.agent_id),
            agent_type=agent.agent_type.value,
            status=agent.status.value,
        )

        # Publicar evento no Kafka se produtor disponível
        if self.autocura_producer:
            try:
                if agent.status == AgentStatus.DEGRADED:
                    success = self.autocura_producer.publish_agent_degraded(
                        agent_id=str(agent.agent_id),
                        agent_type=agent.agent_type.value,
                        status=agent.status.value,
                        last_seen=int(agent.last_seen),
                    )
                elif agent.status == AgentStatus.UNHEALTHY:
                    success = self.autocura_producer.publish_agent_unhealthy(
                        agent_id=str(agent.agent_id),
                        agent_type=agent.agent_type.value,
                        status=agent.status.value,
                        last_seen=int(agent.last_seen),
                    )
                else:
                    # Agente recuperou
                    success = self.autocura_producer.publish_agent_recovered(
                        agent_id=str(agent.agent_id),
                        agent_type=agent.agent_type.value,
                        status=agent.status.value,
                    )

                if success:
                    logger.info(
                        "autocura_notification_published",
                        agent_id=str(agent.agent_id),
                        status=agent.status.value,
                    )
                else:
                    logger.warning(
                        "autocura_notification_failed",
                        agent_id=str(agent.agent_id),
                    )

            except Exception as e:
                logger.error("autocura_notification_exception", error=str(e))
        else:
            # Fallback: log apenas
            logger.info(
                "autocura_notification_logged",
                agent_id=str(agent.agent_id),
                agent_type=agent.agent_type.value,
                status=agent.status.value,
            )

    async def check_agent_health(self, agent_id) -> Optional[AgentStatus]:
        """Verifica saúde de um agente específico"""
        try:
            agent = await self.redis_client.get_agent(agent_id)
            if not agent:
                return None

            current_time = int(datetime.now(UTC).timestamp())
            time_since_last_seen = current_time - agent.last_seen

            if time_since_last_seen > self.heartbeat_timeout:
                return AgentStatus.UNHEALTHY

            return agent.status

        except Exception as e:
            logger.error("check_agent_health_failed", agent_id=str(agent_id), error=str(e))
            return None
