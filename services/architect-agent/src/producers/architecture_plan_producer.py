"""Producer Kafka para planos de arquitetura gerados."""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class ArchitecturePlanProducer:
    """Publica eventos architecture.plans.generated quando arquiteturas são criadas."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "architecture.plans.generated",
    ):
        """Inicializa o produtor.

        Args:
            bootstrap_servers: Endereço do Kafka (padrão: settings)
            topic: Tópico para publicar
        """
        settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or getattr(
            settings, "kafka_bootstrap_servers", "localhost:9092"
        )
        self._topic = topic
        self._producer: AIOKafkaProducer | None = None
        self._logger = logger

    async def start(self) -> None:
        """Inicia o produtor Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",  # Aguardar confirmação de todos os replicas
            compression_type="gzip",
            enable_idempotence=True,  # Evitar duplicações
        )
        await self._producer.start()
        self._logger.info(
            "architecture_plan_producer_started",
            topic=self._topic,
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._logger.info("architecture_plan_producer_stopped")

    async def publish_plan_created(
        self,
        plan_id: str,
        cognitive_plan_id: str | None,
        architecture_type: str,
        components: list[dict[str, Any]],
        rationale: str,
    ) -> None:
        """Publica evento de plano de arquitetura criado.

        Args:
            plan_id: ID do plano de arquitetura
            cognitive_plan_id: ID do CognitivePlan de origem
            architecture_type: Tipo de arquitetura (microservices, monolith, etc)
            components: Lista de componentes da arquitetura
            rationale: Justificativa das decisões
        """
        if not self._producer:
            self._logger.warning("producer_not_started", action="skip_publish")
            return

        event = {
            "event_type": "architecture.plans.generated",
            "plan_id": plan_id,
            "cognitive_plan_id": cognitive_plan_id,
            "architecture_type": architecture_type,
            "components_count": len(components),
            "patterns": components[0].get("patterns", []) if components else [],
            "rationale": rationale,
            "timestamp": structlog.get_logger().bind().info("event_timestamp"),  # type: ignore
        }

        try:
            await self._producer.send_and_wait(self._topic, event)
            self._logger.info(
                "architecture_plan_published",
                plan_id=plan_id,
                topic=self._topic,
            )
        except KafkaError as e:
            self._logger.error(
                "failed_to_publish_architecture_plan",
                plan_id=plan_id,
                error=str(e),
            )
            raise

    async def publish_plan_updated(
        self,
        plan_id: str,
        updates: dict[str, Any],
    ) -> None:
        """Publica evento de plano de arquitetura atualizado.

        Args:
            plan_id: ID do plano de arquitetura
            updates: Campos atualizados
        """
        if not self._producer:
            self._logger.warning("producer_not_started", action="skip_publish")
            return

        event = {
            "event_type": "architecture.plans.updated",
            "plan_id": plan_id,
            "updates": list(updates.keys()),
            "timestamp": structlog.get_logger().bind().info("event_timestamp"),  # type: ignore
        }

        try:
            await self._producer.send_and_wait(self._topic, event)
            self._logger.info(
                "architecture_plan_update_published",
                plan_id=plan_id,
                topic=self._topic,
            )
        except KafkaError as e:
            self._logger.error(
                "failed_to_publish_architecture_update",
                plan_id=plan_id,
                error=str(e),
            )
            raise
