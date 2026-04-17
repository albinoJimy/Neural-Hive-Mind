"""
Kafka producer para eventos de migração de dados.

Produz eventos para o progresso da migração no tópico migration.events.
"""

import json
from datetime import datetime, timezone
from typing import Optional

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

# Singleton instance
_migration_producer: Optional["MigrationProducer"] = None


def get_migration_producer() -> "MigrationProducer":
    """Retorna instância singleton do MigrationProducer.

    Returns:
        Instância do MigrationProducer.
    """
    global _migration_producer
    if _migration_producer is None:
        _migration_producer = MigrationProducer()
    return _migration_producer


class MigrationProducer:
    """Produz eventos de migração para o Kafka.

    Emite eventos para tracking do progresso de migrações de dados,
    incluindo início, progresso, conclusão e falhas.
    """

    # Tópicos Kafka
    MIGRATION_EVENTS_TOPIC = "migration.events"

    def __init__(self):
        """Inicializa o producer."""
        settings = get_settings()
        self._producer: Optional[AIOKafkaProducer] = None
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._running = False
        self._logger = logger

    async def start(self) -> None:
        """Inicia o producer Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            compression_type="gzip",
            acks="all",
            enable_idempotence=True,
            value_serializer=lambda v: json.dumps(v, default=self._json_serializer).encode("utf-8"),
        )
        await self._producer.start()
        self._running = True
        self._logger.info(
            "migration_producer_started",
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o producer Kafka."""
        self._running = False
        if self._producer:
            await self._producer.stop()
            self._logger.info("migration_producer_stopped")

    def _create_event_base(self, event_type: str, job_id: str) -> dict:
        """Cria base do evento.

        Args:
            event_type: Tipo do evento.
            job_id: ID do job de migração.

        Returns:
            Dicionário com campos base do evento.
        """
        return {
            "event_type": event_type,
            "job_id": job_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_service": "data-migration",
        }

    @staticmethod
    def _json_serializer(obj):
        """Serializa objetos para JSON.

        Args:
            obj: Objeto a serializar.

        Returns:
            String JSON serializável.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    @retry(
        retry=retry_if_exception_type(KafkaError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _send_event(self, topic: str, event: dict) -> None:
        """Envia evento para o Kafka com retry.

        Args:
            topic: Tópico Kafka.
            event: Evento a enviar.

        Raises:
            RuntimeError: Se producer não iniciado.
            KafkaError: Se falhar após retries.
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        await self._producer.send_and_wait(topic, value=event)

    async def publish_migration_started(
        self,
        job_id: str,
        legacy_db: str,
        tables: list[str],
    ) -> None:
        """Publica evento de migração iniciada.

        Args:
            job_id: ID do job de migração.
            legacy_db: String de conexão do banco legado (sanitizada).
            tables: Lista de tabelas a migrar.
        """
        event = self._create_event_base("migration.started", job_id)
        event.update(
            {
                "legacy_db": self._sanitize_connection_string(legacy_db),
                "tables": tables,
            }
        )

        try:
            await self._send_event(self.MIGRATION_EVENTS_TOPIC, event)
            self._logger.info(
                "migration_started_published",
                job_id=job_id,
                tables=tables,
            )
        except KafkaError as e:
            self._logger.error("failed_to_publish_migration_started", job_id=job_id, error=str(e))
            raise

    async def publish_migration_progress(
        self,
        job_id: str,
        phase: str,
        table: Optional[str] = None,
        offset: int = 0,
        batch_size: int = 0,
        total_migrated: int = 0,
        total_expected: Optional[int] = None,
        progress_percent: float = 0.0,
    ) -> None:
        """Publica evento de progresso da migração.

        Args:
            job_id: ID do job de migração.
            phase: Fase atual (batch_migration, cdc, validation, etc).
            table: Tabela sendo migrada (opcional).
            offset: Offset atual na tabela.
            batch_size: Tamanho do batch.
            total_migrated: Total de linhas migradas.
            total_expected: Total esperado de linhas.
            progress_percent: Percentual de progresso (0-100).
        """
        event = self._create_event_base("migration.progress", job_id)
        event.update(
            {
                "phase": phase,
                "table": table,
                "offset": offset,
                "batch_size": batch_size,
                "total_migrated": total_migrated,
                "total_expected": total_expected,
                "progress_percent": round(progress_percent, 2),
            }
        )

        try:
            await self._send_event(self.MIGRATION_EVENTS_TOPIC, event)
            self._logger.debug(
                "migration_progress_published",
                job_id=job_id,
                phase=phase,
                progress_percent=progress_percent,
            )
        except KafkaError as e:
            self._logger.error("failed_to_publish_migration_progress", job_id=job_id, error=str(e))
            raise

    async def publish_batch_completed(
        self,
        job_id: str,
        tables_completed: list[str],
        total_rows: int,
        duration_seconds: float,
    ) -> None:
        """Publica evento de batch migration completa.

        Args:
            job_id: ID do job de migração.
            tables_completed: Lista de tabelas completadas.
            total_rows: Total de linhas migradas.
            duration_seconds: Duração em segundos.
        """
        event = self._create_event_base("migration.batch_completed", job_id)
        event.update(
            {
                "tables_completed": tables_completed,
                "total_rows": total_rows,
                "duration_seconds": round(duration_seconds, 2),
            }
        )

        try:
            await self._send_event(self.MIGRATION_EVENTS_TOPIC, event)
            self._logger.info(
                "batch_completed_published",
                job_id=job_id,
                tables_completed=tables_completed,
                total_rows=total_rows,
            )
        except KafkaError as e:
            self._logger.error("failed_to_publish_batch_completed", job_id=job_id, error=str(e))
            raise

    async def publish_cdc_started(
        self,
        job_id: str,
        connector_id: str,
        kafka_topic: str,
    ) -> None:
        """Publica evento de CDC iniciado.

        Args:
            job_id: ID do job de migração.
            connector_id: ID do connector Debezium.
            kafka_topic: Tópico Kafka do CDC.
        """
        event = self._create_event_base("migration.cdc_started", job_id)
        event.update(
            {
                "connector_id": connector_id,
                "kafka_topic": kafka_topic,
            }
        )

        try:
            await self._send_event(self.MIGRATION_EVENTS_TOPIC, event)
            self._logger.info(
                "cdc_started_published",
                job_id=job_id,
                connector_id=connector_id,
                kafka_topic=kafka_topic,
            )
        except KafkaError as e:
            self._logger.error("failed_to_publish_cdc_started", job_id=job_id, error=str(e))
            raise

    async def publish_migration_completed(
        self,
        job_id: str,
        status: str = "completed",
        total_rows: int = 0,
        cdc_lag: int = 0,
    ) -> None:
        """Publica evento de migração completa.

        Args:
            job_id: ID do job de migração.
            status: Status final (completed, completed_with_warnings).
            total_rows: Total de linhas migradas.
            cdc_lag: Lag do CDC em milissegundos.
        """
        event = self._create_event_base("migration.completed", job_id)
        event.update(
            {
                "status": status,
                "total_rows": total_rows,
                "cdc_lag": cdc_lag,
            }
        )

        try:
            await self._send_event(self.MIGRATION_EVENTS_TOPIC, event)
            self._logger.info(
                "migration_completed_published",
                job_id=job_id,
                status=status,
                total_rows=total_rows,
            )
        except KafkaError as e:
            self._logger.error("failed_to_publish_migration_completed", job_id=job_id, error=str(e))
            raise

    async def publish_migration_failed(
        self,
        job_id: str,
        error: str,
        phase: str,
    ) -> None:
        """Publica evento de falha na migração.

        Args:
            job_id: ID do job de migração.
            error: Mensagem de erro.
            phase: Fase em que ocorreu a falha.
        """
        event = self._create_event_base("migration.failed", job_id)
        event.update(
            {
                "error": error,
                "phase": phase,
            }
        )

        try:
            await self._send_event(self.MIGRATION_EVENTS_TOPIC, event)
            self._logger.error(
                "migration_failed_published",
                job_id=job_id,
                phase=phase,
                error=error,
            )
        except KafkaError as e:
            self._logger.error("failed_to_publish_migration_failed", job_id=job_id, error=str(e))
            raise

    def _sanitize_connection_string(self, connection_string: str) -> str:
        """Sanitiza string de conexão para logging.

        Args:
            connection_string: String de conexão original.

        Returns:
            String de conexão sanitizada (sem senha).
        """
        if "://" in connection_string and "@" in connection_string:
            # Remove credenciais
            parts = connection_string.split("@")
            if len(parts) == 2:
                protocol_host = parts[0].split("://")
                if len(protocol_host) == 2:
                    return f"{protocol_host[0]}://***@{parts[1]}"
        return connection_string
