"""Kafka producer para eventos de documentos."""

import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class DocProducer:
    """Produz eventos de documentos para o Kafka."""

    def __init__(self):
        """Inicializa o producer."""
        settings = get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._docs_topic = "doc.events"
        self._dlq_topic = settings.kafka_dlq_topic
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
            "doc_producer_started",
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o producer Kafka."""
        self._running = False
        if self._producer:
            await self._producer.stop()
            self._logger.info("doc_producer_stopped")

    def _create_event_base(self, event_type: str) -> dict:
        """Cria base do evento.

        Args:
            event_type: Tipo do evento.

        Returns:
            Dicionário com campos base do evento.
        """
        return {
            "event_type": event_type,
            "event_id": f"evt-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_service": "doc-ingestion",
        }

    async def publish_doc_uploaded(
        self,
        document_id: str,
        filename: str,
        format_type: str,
        file_size_bytes: int,
        uploaded_by: str,
        s3_key: str,
        project_id: str | None = None,
    ) -> None:
        """Publica evento de documento recebido.

        Args:
            document_id: ID do documento.
            filename: Nome do arquivo.
            format_type: Formato do documento (pdf, docx, vsd, vsdx, postman).
            file_size_bytes: Tamanho em bytes.
            uploaded_by: Usuário que fez upload.
            s3_key: Chave S3 do arquivo.
            project_id: ID do projeto (opcional).
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = self._create_event_base("doc.uploaded")
        event.update(
            {
                "document_id": document_id,
                "filename": filename,
                "format": format_type,
                "file_size_bytes": file_size_bytes,
                "uploaded_by": uploaded_by,
                "s3_key": s3_key,
                "project_id": project_id,
            }
        )

        try:
            await self._producer.send_and_wait(
                self._docs_topic,
                value=event,
            )
            self._logger.info(
                "doc_uploaded_published",
                document_id=document_id,
                filename=filename,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_doc_uploaded", error=str(e))
            raise

    async def publish_doc_parsed(
        self,
        document_id: str,
        parsed_text_length: int,
        parsing_duration_ms: int,
        has_error: bool = False,
        error_message: str | None = None,
    ) -> None:
        """Publica evento de documento parseado.

        Args:
            document_id: ID do documento.
            parsed_text_length: Tamanho do texto extraído.
            parsing_duration_ms: Duração do parsing em ms.
            has_error: Se houve erro no parsing.
            error_message: Mensagem de erro (se aplicável).
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = self._create_event_base("doc.parsed")
        event.update(
            {
                "document_id": document_id,
                "parsed_text_length": parsed_text_length,
                "parsing_duration_ms": parsing_duration_ms,
                "has_error": has_error,
                "error_message": error_message,
            }
        )

        try:
            await self._producer.send_and_wait(
                self._docs_topic,
                value=event,
            )
            self._logger.info(
                "doc_parsed_published",
                document_id=document_id,
                success=not has_error,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_doc_parsed", error=str(e))
            raise

    async def publish_doc_entities_extracted(
        self,
        document_id: str,
        entity_count: int,
        entity_types: list[str],
        extraction_duration_ms: int,
    ) -> None:
        """Publica evento de entidades extraídas.

        Args:
            document_id: ID do documento.
            entity_count: Número de entidades extraídas.
            entity_types: Tipos de entidades extraídas.
            extraction_duration_ms: Duração da extração em ms.
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = self._create_event_base("doc.entities_extracted")
        event.update(
            {
                "document_id": document_id,
                "entity_count": entity_count,
                "entity_types": entity_types,
                "extraction_duration_ms": extraction_duration_ms,
            }
        )

        try:
            await self._producer.send_and_wait(
                self._docs_topic,
                value=event,
            )
            self._logger.info(
                "doc_entities_extracted_published",
                document_id=document_id,
                entity_count=entity_count,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_entities_extracted", error=str(e))
            raise

    async def publish_doc_approved(
        self,
        document_id: str,
        approved_by: str,
        approval_notes: str | None = None,
    ) -> None:
        """Publica evento de documento aprovado.

        Args:
            document_id: ID do documento.
            approved_by: Usuário que aprovou.
            approval_notes: Notas da aprovação (opcional).
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = self._create_event_base("doc.approved")
        event.update(
            {
                "document_id": document_id,
                "approved_by": approved_by,
                "approval_notes": approval_notes,
            }
        )

        try:
            await self._producer.send_and_wait(
                self._docs_topic,
                value=event,
            )
            self._logger.info(
                "doc_approved_published",
                document_id=document_id,
                approved_by=approved_by,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_doc_approved", error=str(e))
            raise

    async def send_to_dlq(
        self,
        original_value: bytes,
        reason: str,
    ) -> None:
        """Envia mensagem para Dead Letter Queue.

        Args:
            original_value: Valor bruto da mensagem.
            reason: Razão do envio para DLQ.
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        dlq_event = {
            "original_topic": self._docs_topic,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_value": original_value.decode("utf-8", errors="replace"),
        }

        try:
            await self._producer.send_and_wait(self._dlq_topic, value=dlq_event)
            self._logger.info("sent_to_dlq", reason=reason)

        except KafkaError as e:
            self._logger.error("failed_to_send_to_dlq", error=str(e))

    async def publish_doc_sent_to_gateway(
        self,
        document_id: str,
        intent_id: str,
        ingestion_id: str,
        duration_ms: int,
    ) -> None:
        """Publica evento de documento enviado para Gateway.

        Args:
            document_id: ID do documento.
            intent_id: ID da intenção criada no Gateway.
            ingestion_id: ID do processo de ingestão.
            duration_ms: Duração do envio em ms.
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = self._create_event_base("doc.sent_to_gateway")
        event.update(
            {
                "document_id": document_id,
                "intent_id": intent_id,
                "ingestion_id": ingestion_id,
                "duration_ms": duration_ms,
            }
        )

        try:
            await self._producer.send_and_wait(
                self._docs_topic,
                value=event,
            )
            self._logger.info(
                "doc_sent_to_gateway_published",
                document_id=document_id,
                intent_id=intent_id,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_sent_to_gateway", error=str(e))
            raise
