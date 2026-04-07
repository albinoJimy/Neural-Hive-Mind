"""Producer Kafka para eventos de otimização."""
import json
from datetime import datetime, timezone

UTC = timezone.utc  # type: ignore

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError
from structlog import get_logger

from src.config.settings import get_settings

logger = get_logger(__name__)


class OptimizationProducer:
    """Producer para enviar eventos ticket.completed."""

    def __init__(self, settings: get_settings | None = None):
        """Inicializa producer."""
        self.settings = settings or get_settings()
        self._producer: AIOKafkaProducer | None = None

    async def initialize(self) -> None:
        """Inicializa producer Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        try:
            await self._producer.start()
            logger.info(
                "optimization_producer_started",
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
            )
        except KafkaConnectionError as e:
            logger.exception("kafka_producer_connection_failed", error=str(e))
            raise

    async def publish_ticket_completed(
        self,
        ticket_id: str,
        workflow_id: str,
        status: str,
        duration_ms: int,
        peak_memory_mb: int,
        task_count: int,
        tasks: list,
    ) -> None:
        """
        Publica evento ticket.completed.

        Args:
            ticket_id: ID do ticket
            workflow_id: ID do workflow
            status: Status do ticket
            duration_ms: Duração em ms
            peak_memory_mb: Pico de memória
            task_count: Número de tarefas
            tasks: Lista de tarefas executadas
        """
        event = {
            "ticket_id": ticket_id,
            "workflow_id": workflow_id,
            "status": status,
            "duration_ms": duration_ms,
            "peak_memory_mb": peak_memory_mb,
            "task_count": task_count,
            "tasks": tasks,
            "created_at": datetime.now(UTC).isoformat(),
        }

        topic = "ticket.completed"
        await self._producer.send_and_wait(topic, value=event)

        logger.debug(
            "ticket_completed_published",
            ticket_id=ticket_id,
            workflow_id=workflow_id,
        )

    async def close(self) -> None:
        """Fecha producer."""
        if self._producer:
            await self._producer.stop()
            logger.info("optimization_producer_closed")
