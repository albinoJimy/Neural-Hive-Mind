"""Kafka producer para Documentation events."""

import json
from datetime import UTC, datetime

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class DocumentationProducer:
    """Produz eventos Documentation para o Kafka."""

    def __init__(self):
        """Inicializa o producer."""
        settings = get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._output_topic = getattr(settings, "kafka_output_topic", "documentation.generated")
        self._dlq_topic = getattr(settings, "kafka_dlq_topic", "documentation.dlq")
        self._logger = logger
        self._running = False

    async def start(self) -> None:
        """Inicia o producer Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            compression_type="gzip",
            acks="all",
            enable_idempotence=True,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()
        self._running = True
        self._logger.info(
            "documentation_producer_started",
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o producer Kafka."""
        self._running = False
        if self._producer:
            await self._producer.stop()
            self._logger.info("documentation_producer_stopped")

    async def publish_documentation_generated(
        self,
        document_id: str,
        doc_type: str,
        source_type: str,
        source_id: str,
        title: str,
        file_path: str | None = None,
    ) -> None:
        """Publica evento de documentação gerada.

        Args:
            document_id: ID do documento
            doc_type: Tipo de documento (readme, api_docs, architecture, diagram)
            source_type: Tipo da fonte (code, architecture, requirements)
            source_id: ID da fonte
            title: Título do documento
            file_path: Caminho do arquivo gerado
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = {
            "event_type": "documentation.generated",
            "event_id": f"evt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now(UTC).isoformat(),
            "document_id": document_id,
            "doc_type": doc_type,
            "source_type": source_type,
            "source_id": source_id,
            "title": title,
            "file_path": file_path,
        }

        try:
            await self._producer.send_and_wait(
                self._output_topic,
                value=event,
            )
            self._logger.info(
                "documentation_generated_published",
                document_id=document_id,
                doc_type=doc_type,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_documentation", error=str(e))
            raise

    async def publish_diagram_generated(
        self,
        diagram_id: str,
        diagram_type: str,
        source_id: str,
        title: str,
        format: str = "svg",
    ) -> None:
        """Publica evento de diagrama gerado.

        Args:
            diagram_id: ID do diagrama
            diagram_type: Tipo de diagrama (c4, sequence, flowchart, erd)
            source_id: ID da fonte
            title: Título do diagrama
            format: Formato de saída
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = {
            "event_type": "diagram.generated",
            "event_id": f"evt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now(UTC).isoformat(),
            "diagram_id": diagram_id,
            "diagram_type": diagram_type,
            "source_id": source_id,
            "title": title,
            "format": format,
        }

        try:
            await self._producer.send_and_wait(
                self._output_topic,
                value=event,
            )
            self._logger.info(
                "diagram_generated_published",
                diagram_id=diagram_id,
                diagram_type=diagram_type,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_diagram", error=str(e))
            raise
