"""Producer Kafka para hipóteses validadas."""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class HypothesisValidatedProducer:
    """Publica eventos hypotheses.validated quando hipóteses são processadas."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "hypotheses.validated",
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
            acks="all",
            compression_type="gzip",
            enable_idempotence=True,
        )
        await self._producer.start()
        self._logger.info(
            "hypothesis_validated_producer_started",
            topic=self._topic,
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._logger.info("hypothesis_validated_producer_stopped")

    async def publish_hypothesis_validated(
        self,
        hypothesis_id: str,
        statement: str,
        status: str,
        priority: str,
        source: str,
        experiment_id: str | None,
        validation_score: float,
    ) -> None:
        """Publica evento de hipótese validada.

        Args:
            hypothesis_id: ID da hipótese
            statement: Enunciado da hipótese
            status: Status da hipótese
            priority: Prioridade da hipótese
            source: Fonte da hipótese
            experiment_id: ID do experimento relacionado
            validation_score: Score de validação calculado
        """
        if not self._producer:
            self._logger.warning("producer_not_started", action="skip_publish")
            return

        event = {
            "event_type": "hypotheses.validated",
            "hypothesis_id": hypothesis_id,
            "statement": statement[:200],  # Truncado para o evento
            "status": status,
            "priority": priority,
            "source": source,
            "experiment_id": experiment_id,
            "validation_score": validation_score,
            "timestamp": structlog.get_logger().bind().info("event_timestamp"),  # type: ignore
        }

        try:
            await self._producer.send_and_wait(self._topic, event)
            self._logger.info(
                "hypothesis_validated_published",
                hypothesis_id=hypothesis_id,
                topic=self._topic,
            )
        except KafkaError as e:
            self._logger.error(
                "failed_to_publish_hypothesis_validated",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )
            raise
