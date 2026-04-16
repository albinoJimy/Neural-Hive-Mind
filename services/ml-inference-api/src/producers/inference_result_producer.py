"""Producer Kafka para resultados de inferência ML."""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

logger = structlog.get_logger(__name__)


class InferenceResultProducer:
    """Publica eventos inference.results quando inferências são concluídas."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "inference.results",
    ):
        """Inicializa o produtor.

        Args:
            bootstrap_servers: Endereço do Kafka
            topic: Tópico para publicar
        """
        self._bootstrap_servers = bootstrap_servers
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
            "inference_result_producer_started",
            topic=self._topic,
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._logger.info("inference_result_producer_stopped")

    async def publish_inference_result(
        self,
        request_id: str,
        model_name: str,
        model_version: str,
        status: str,
        prediction: dict[str, Any] | None,
        confidence: float | None,
        latency_ms: int,
        cached: bool,
        error: str | None = None,
    ) -> None:
        """Publica evento de resultado de inferência.

        Args:
            request_id: ID da requisição
            model_name: Nome do modelo usado
            model_version: Versão do modelo
            status: Status da inferência
            prediction: Resultado da predição
            confidence: Confiança da predição
            latency_ms: Latência em ms
            cached: Se veio do cache
            error: Mensagem de erro se falhou
        """
        if not self._producer:
            self._logger.warning("producer_not_started", action="skip_publish")
            return

        event = {
            "event_type": "inference.results",
            "request_id": request_id,
            "model_name": model_name,
            "model_version": model_version,
            "status": status,
            "prediction": prediction,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "cached": cached,
            "error": error,
            "timestamp": structlog.get_logger().bind().info("event_timestamp"),  # type: ignore
        }

        try:
            await self._producer.send_and_wait(self._topic, event)
            self._logger.info(
                "inference_result_published",
                request_id=request_id,
                topic=self._topic,
            )
        except KafkaError as e:
            self._logger.error(
                "failed_to_publish_inference_result",
                request_id=request_id,
                error=str(e),
            )
            raise
