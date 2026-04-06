"""Producer Kafka para publicar eventos de Saga."""
import json
from datetime import datetime
from neural_hive_domain import UTC
from typing import Any, Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError
from structlog import get_logger

from src.config.settings import OrchestratorSettings, get_settings

from .saga_state import SagaState

logger = get_logger(__name__)

# Producer singleton
_producer: Optional["SagaProducer"] = None


class SagaProducer:
    """Producer Kafka para eventos de saga (saga.events).

    Publica eventos de Saga para observabilidade e tracing distribuido.
    """

    def __init__(self, settings: OrchestratorSettings | None = None):
        """Inicializa producer.

        Args:
            settings: Configuracoes do servico (opcional)
        """
        self.settings = settings or get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._metrics = None

    @property
    def SAGA_TOPIC(self) -> str:
        """Retorna o tópico configurado para eventos de Saga."""
        return getattr(self.settings, "kafka_saga_events_topic", "saga.events")

    def __init__(self, settings: OrchestratorSettings | None = None):
        """Inicializa producer.

        Args:
            settings: Configuracoes do servico (opcional)
        """
        self.settings = settings or get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._metrics = None

    async def initialize(self) -> None:
        """Inicializa producer Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        try:
            await self._producer.start()
            logger.info(
                "saga_producer_initialized",
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                topic=self.SAGA_TOPIC,
            )
        except KafkaConnectionError as e:
            logger.exception("saga_producer_connection_failed", error=str(e))
            raise

    async def _publish_event(
        self,
        event_type: str,
        saga_id: str,
        data: dict[str, Any],
        timestamp_ms: int | None = None,
    ) -> bool:
        """Publica evento no Kafka.

        Args:
            event_type: Tipo do evento
            saga_id: ID da Saga
            data: Dados do evento
            timestamp_ms: Timestamp em millis (opcional, usa agora se None)

        Returns:
            True se publicado com sucesso
        """
        if not self._producer:
            logger.warning("saga_producer_not_initialized")
            return False

        event = {
            "event_type": event_type,
            "saga_id": saga_id,
            "timestamp": timestamp_ms or int(datetime.now(UTC).timestamp() * 1000),
            "data": data,
        }

        try:
            await self._producer.send_and_wait(
                self.SAGA_TOPIC, value=event, key=saga_id.encode("utf-8")
            )
            logger.debug(
                "saga_event_published",
                event_type=event_type,
                saga_id=saga_id,
            )
            return True
        except Exception as e:
            logger.exception(
                "saga_event_publish_failed",
                event_type=event_type,
                saga_id=saga_id,
                error=str(e),
            )
            return False

    async def publish_saga_created(self, saga: SagaState) -> bool:
        """Publica evento saga_created.

        Args:
            saga: Estado da Saga criada

        Returns:
            True se publicado com sucesso
        """
        data = {
            "workflow_id": saga.workflow_id,
            "plan_id": saga.plan_id,
            "intent_id": saga.intent_id,
            "steps_count": len(saga.steps),
            "metadata": saga.metadata,
        }

        result = await self._publish_event(
            event_type="saga_created",
            saga_id=saga.saga_id,
            data=data,
            timestamp_ms=saga.created_at,
        )

        if self._metrics:
            self._metrics.increment("saga_created", 1, {"plan_id": saga.plan_id})

        return result

    async def publish_saga_started(self, saga: SagaState) -> bool:
        """Publica evento saga_started.

        Args:
            saga: Estado da Saga iniciada

        Returns:
            True se publicado com sucesso
        """
        data = {
            "workflow_id": saga.workflow_id,
            "plan_id": saga.plan_id,
            "steps_count": len(saga.steps),
            "started_at": saga.started_at,
        }

        result = await self._publish_event(
            event_type="saga_started",
            saga_id=saga.saga_id,
            data=data,
            timestamp_ms=saga.started_at,
        )

        if self._metrics:
            self._metrics.increment("saga_started", 1, {"plan_id": saga.plan_id})

        return result

    async def publish_saga_step_completed(
        self,
        saga_id: str,
        step_id: str,
        step_name: str,
        result: dict[str, Any] | None = None,
        step_index: int = 0,
    ) -> bool:
        """Publica evento saga_step_completed.

        Args:
            saga_id: ID da Saga
            step_id: ID do step completado
            step_name: Nome do step
            result: Resultado da execucao
            step_index: Indice do step

        Returns:
            True se publicado com sucesso
        """
        data = {
            "step_id": step_id,
            "step_name": step_name,
            "step_index": step_index,
            "result": result or {},
        }

        result = await self._publish_event(
            event_type="saga_step_completed",
            saga_id=saga_id,
            data=data,
        )

        if self._metrics:
            self._metrics.increment("step_completed", 1, {"step_name": step_name})

        return result

    async def publish_saga_step_failed(
        self, saga_id: str, step_id: str, step_name: str, error: str, step_index: int = 0
    ) -> bool:
        """Publica evento saga_step_failed.

        Args:
            saga_id: ID da Saga
            step_id: ID do step que falhou
            step_name: Nome do step
            error: Mensagem de erro
            step_index: Indice do step

        Returns:
            True se publicado com sucesso
        """
        data = {
            "step_id": step_id,
            "step_name": step_name,
            "step_index": step_index,
            "error": error,
        }

        result = await self._publish_event(
            event_type="saga_step_failed",
            saga_id=saga_id,
            data=data,
        )

        if self._metrics:
            self._metrics.increment("step_failed", 1, {"step_name": step_name})

        return result

    async def publish_saga_compensating(
        self, saga_id: str, reason: str, failed_step_id: str, steps_to_compensate: int
    ) -> bool:
        """Publica evento saga_compensating.

        Args:
            saga_id: ID da Saga
            reason: Razao da compensacao
            failed_step_id: ID do step que falhou
            steps_to_compensate: Numero de steps a compensar

        Returns:
            True se publicado com sucesso
        """
        data = {
            "reason": reason,
            "failed_step_id": failed_step_id,
            "steps_to_compensate": steps_to_compensate,
        }

        result = await self._publish_event(
            event_type="saga_compensating",
            saga_id=saga_id,
            data=data,
        )

        if self._metrics:
            self._metrics.increment("saga_compensating", 1, {"reason": reason})

        return result

    async def publish_saga_compensated(self, saga: SagaState) -> bool:
        """Publica evento saga_compensated.

        Args:
            saga: Estado da Saga compensada

        Returns:
            True se publicado com sucesso
        """
        compensated_steps = [s for s in saga.steps if s.status.value == "COMPENSATED"]

        data = {
            "workflow_id": saga.workflow_id,
            "plan_id": saga.plan_id,
            "steps_compensated": len(compensated_steps),
            "compensated_at": saga.compensated_at,
            "error": saga.error,
        }

        result = await self._publish_event(
            event_type="saga_compensated",
            saga_id=saga.saga_id,
            data=data,
            timestamp_ms=saga.compensated_at,
        )

        if self._metrics:
            self._metrics.increment("saga_compensated", 1, {"plan_id": saga.plan_id})

        return result

    async def publish_saga_completed(self, saga: SagaState) -> bool:
        """Publica evento saga_completed.

        Args:
            saga: Estado da Saga completada

        Returns:
            True se publicado com sucesso
        """
        completed_steps = [s for s in saga.steps if s.status.value == "COMPLETED"]

        data = {
            "workflow_id": saga.workflow_id,
            "plan_id": saga.plan_id,
            "steps_completed": len(completed_steps),
            "completed_at": saga.completed_at,
        }

        result = await self._publish_event(
            event_type="saga_completed",
            saga_id=saga.saga_id,
            data=data,
            timestamp_ms=saga.completed_at,
        )

        if self._metrics:
            self._metrics.increment("saga_completed", 1, {"plan_id": saga.plan_id})

        return result

    async def publish_saga_failed(self, saga: SagaState, final_error: str) -> bool:
        """Publica evento saga_failed.

        Args:
            saga: Estado da Saga falhada
            final_error: Erro final que causou a falha

        Returns:
            True se publicado com sucesso
        """
        data = {
            "workflow_id": saga.workflow_id,
            "plan_id": saga.plan_id,
            "error": final_error,
            "failed_at": saga.failed_at,
            "retry_count": saga.retry_count,
            "max_retries": saga.max_retries,
        }

        result = await self._publish_event(
            event_type="saga_failed",
            saga_id=saga.saga_id,
            data=data,
            timestamp_ms=saga.failed_at,
        )

        if self._metrics:
            self._metrics.increment("saga_failed", 1, {"plan_id": saga.plan_id})

        return result

    def set_metrics(self, metrics: "SagaMetrics") -> None:
        """Define instancia de metrics para registro.

        Args:
            metrics: Instancia de SagaMetrics
        """
        self._metrics = metrics

    async def close(self) -> None:
        """Fecha producer."""
        if self._producer:
            await self._producer.stop()
            logger.info("saga_producer_closed")


async def get_saga_producer() -> SagaProducer:
    """Retorna instância singleton do SagaProducer.

    Returns:
        Instancia de SagaProducer inicializada
    """
    global _producer
    if _producer is None:
        settings = get_settings()
        _producer = SagaProducer(settings)
        await _producer.initialize()
    return _producer
