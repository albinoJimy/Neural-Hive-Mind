"""Producer Kafka para análises de impacto analisadas."""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class ImpactAnalyzedProducer:
    """Publica eventos impact.analyzed quando análises são concluídas."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "impact.analyzed",
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
            "impact_analyzed_producer_started",
            topic=self._topic,
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._logger.info("impact_analyzed_producer_stopped")

    async def publish_impact_analyzed(
        self,
        experiment_id: str,
        variant: str,
        short_term_impacts: int,
        long_term_available: bool,
        overall_impact_score: float,
        key_metrics: list[dict[str, Any]],
    ) -> None:
        """Publica evento de impacto analisado.

        Args:
            experiment_id: ID do experimento
            variant: Variante do experimento
            short_term_impacts: Número de impactos de curto prazo
            long_term_available: Se análise de longo prazo está disponível
            overall_impact_score: Score de impacto agregado
            key_metrics: Métricas chave afetadas
        """
        if not self._producer:
            self._logger.warning("producer_not_started", action="skip_publish")
            return

        event = {
            "event_type": "impact.analyzed",
            "experiment_id": experiment_id,
            "variant": variant,
            "short_term_impacts_count": short_term_impacts,
            "long_term_available": long_term_available,
            "overall_impact_score": overall_impact_score,
            "key_metrics_count": len(key_metrics),
            "key_metrics": key_metrics[:5],  # Top 5 métricas
            "timestamp": structlog.get_logger().bind().info("event_timestamp"),  # type: ignore
        }

        try:
            await self._producer.send_and_wait(self._topic, event)
            self._logger.info(
                "impact_analyzed_published",
                experiment_id=experiment_id,
                topic=self._topic,
            )
        except KafkaError as e:
            self._logger.error(
                "failed_to_publish_impact_analyzed",
                experiment_id=experiment_id,
                error=str(e),
            )
            raise
