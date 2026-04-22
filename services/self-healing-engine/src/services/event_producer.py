"""Kafka Event Producer para Self-Healing Engine.

Publica eventos relacionados a:
- Detecção de anomalias
- Execução de remediação
- Mudanças de estado
- Métricas de health
"""

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

import structlog
from aiokafka import AIOKafkaProducer
from prometheus_client import Counter

logger = structlog.get_logger()

# Métricas de publicação
KAFKA_EVENT_PUBLISHED_TOTAL = Counter(
    "self_healing_kafka_events_published_total",
    "Total de eventos publicados no Kafka",
    ["event_type", "status"],
)
KAFKA_EVENT_PUBLISH_FAILED_TOTAL = Counter(
    "self_healing_kafka_events_publish_failed_total",
    "Total de falhas ao publicar eventos",
    ["event_type"],
)


class EventType(str, Enum):
    """Tipos de eventos publicados pelo Self-Healing."""

    # Eventos de detecção
    ANOMALY_DETECTED = "anomaly.detected"
    DEADLOCK_DETECTED = "deadlock.detected"
    MEMORY_LEAK_DETECTED = "memory_leak.detected"
    KAFKA_LAG_DETECTED = "kafka_lag.detected"
    POD_CRASH_LOOP_DETECTED = "pod_crash_loop.detected"
    DATABASE_CONNECTION_ISSUE = "database_connection.issue"

    # Eventos de remediação
    REMEDIATION_STARTED = "remediation.started"
    REMEDIATION_COMPLETED = "remediation.completed"
    REMEDIATION_FAILED = "remediation.failed"
    REMEDIATION_CANCELLED = "remediation.cancelled"
    PLAYBOOK_EXECUTED = "playbook.executed"

    # Eventos de playbook
    PLAYBOOK_VALIDATED = "playbook.validated"
    PLAYBOOK_VALIDATION_FAILED = "playbook.validation_failed"

    # Eventos de health
    HEALTH_CHECK_PASSED = "health_check.passed"
    HEALTH_CHECK_FAILED = "health_check.failed"
    SERVICE_RECOVERED = "service.recovered"
    SERVICE_DEGRADED = "service.degraded"

    # Eventos de estado
    CIRCUIT_BREAKER_OPENED = "circuit_breaker.opened"
    CIRCUIT_BREAKER_CLOSED = "circuit_breaker.closed"
    CIRCUIT_BREAKER_HALF_OPEN = "circuit_breaker.half_open"


class SelfHealingEvent:
    """Evento de Self-Healing para publicação no Kafka."""

    def __init__(
        self,
        event_type: EventType,
        source: str,
        data: dict[str, Any],
        severity: str = "info",
        timestamp: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """Cria um novo evento.

        Args:
            event_type: Tipo do evento
            source: Fonte do evento (serviço/componente)
            data: Dados específicos do evento
            severity: Severidade (debug, info, warning, error, critical)
            timestamp: Timestamp do evento (default: agora)
            correlation_id: ID de correlação para rastreamento
            metadata: Metadados adicionais
        """
        self.event_type = event_type
        self.source = source
        self.data = data
        self.severity = severity
        self.timestamp = timestamp or datetime.now(UTC)
        self.correlation_id = correlation_id
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "correlation_id": self.correlation_id,
            "data": self.data,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Converte para JSON string."""
        return json.dumps(self.to_dict())


class EventProducer:
    """Produtor de eventos para o Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str = "self-healing.events",
        client_id: Optional[str] = None,
        ack_timeout_seconds: int = 5,
        max_retries: int = 3,
        enabled: bool = True,
    ):
        """Inicializa o produtor de eventos.

        Args:
            bootstrap_servers: Endereços do Kafka
            topic: Tópico para publicação
            client_id: ID do cliente (opcional)
            ack_timeout_seconds: Timeout para ACK
            max_retries: Máximo de tentativas
            enabled: Se o produtor está habilitado
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.client_id = client_id or "self-healing-event-producer"
        self.ack_timeout_seconds = ack_timeout_seconds
        self.max_retries = max_retries
        self.enabled = enabled

        self._producer: Optional[AIOKafkaProducer] = None
        self._running = False

    async def start(self):
        """Inicia o produtor Kafka."""
        if not self.enabled:
            logger.info("event_producer.disabled")
            return

        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                request_timeout_ms=self.ack_timeout_seconds * 1000,
                value_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
            )
            logger.info(
                "event_producer.started",
                bootstrap_servers=self.bootstrap_servers,
                topic=self.topic,
            )
        except Exception as exc:
            logger.error("event_producer.start_failed", error=str(exc))
            raise

    async def stop(self):
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
        self._running = False
        logger.info("event_producer.stopped")

    async def publish_event(
        self,
        event: SelfHealingEvent,
        key: Optional[str] = None,
    ) -> bool:
        """Publica um evento no Kafka.

        Args:
            event: Evento a publicar
            key: Chave de partição (opcional)

        Returns:
            True se publicado com sucesso
        """
        if not self.enabled or not self._producer:
            logger.debug("event_producer.skipped", event_type=event.event_type)
            return False

        try:
            value = event.to_json()
            await self._producer.send_and_wait(
                topic=self.topic,
                value=value,
                key=key.encode("utf-8") if key else None,
            )

            KAFKA_EVENT_PUBLISHED_TOTAL.labels(
                event_type=event.event_type.value, status="success"
            ).inc()

            logger.debug(
                "event_producer.published",
                event_type=event.event_type.value,
                source=event.source,
                correlation_id=event.correlation_id,
            )
            return True

        except Exception as exc:
            KAFKA_EVENT_PUBLISHED_TOTAL.labels(
                event_type=event.event_type.value, status="failed"
            ).inc()
            KAFKA_EVENT_PUBLISH_FAILED_TOTAL.labels(event_type=event.event_type.value).inc()

            logger.error(
                "event_producer.publish_failed",
                event_type=event.event_type.value,
                error=str(exc),
            )
            return False

    async def publish_anomaly_detected(
        self,
        anomaly_type: str,
        entity_id: str,
        details: dict[str, Any],
        severity: str = "warning",
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de anomalia detectada."""
        event = SelfHealingEvent(
            event_type=EventType.ANOMALY_DETECTED,
            source="detection_service",
            data={
                "anomaly_type": anomaly_type,
                "entity_id": entity_id,
                "details": details,
            },
            severity=severity,
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=entity_id)

    async def publish_remediation_started(
        self,
        remediation_id: str,
        incident_type: str,
        playbook_name: str,
        context: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de remediação iniciada."""
        event = SelfHealingEvent(
            event_type=EventType.REMEDIATION_STARTED,
            source="remediation_manager",
            data={
                "remediation_id": remediation_id,
                "incident_type": incident_type,
                "playbook_name": playbook_name,
                "context": context,
            },
            severity="info",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=remediation_id)

    async def publish_remediation_completed(
        self,
        remediation_id: str,
        result: dict[str, Any],
        duration_seconds: float,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de remediação completada."""
        event = SelfHealingEvent(
            event_type=EventType.REMEDIATION_COMPLETED,
            source="remediation_manager",
            data={
                "remediation_id": remediation_id,
                "success": result.get("success", False),
                "duration_seconds": duration_seconds,
                "actions_completed": result.get("actions", []),
            },
            severity="info",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=remediation_id)

    async def publish_remediation_failed(
        self,
        remediation_id: str,
        error: str,
        context: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de falha na remediação."""
        event = SelfHealingEvent(
            event_type=EventType.REMEDIATION_FAILED,
            source="remediation_manager",
            data={
                "remediation_id": remediation_id,
                "error": error,
                "context": context,
            },
            severity="error",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=remediation_id)

    async def publish_health_check_failed(
        self,
        service_name: str,
        check_type: str,
        error: str,
        details: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de health check falhando."""
        event = SelfHealingEvent(
            event_type=EventType.HEALTH_CHECK_FAILED,
            source="health_monitor",
            data={
                "service_name": service_name,
                "check_type": check_type,
                "error": error,
                "details": details,
            },
            severity="warning",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=service_name)

    async def publish_playbook_executed(
        self,
        playbook_name: str,
        action_count: int,
        duration_seconds: float,
        success: bool,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de playbook executado."""
        event = SelfHealingEvent(
            event_type=EventType.PLAYBOOK_EXECUTED,
            source="playbook_executor",
            data={
                "playbook_name": playbook_name,
                "action_count": action_count,
                "duration_seconds": duration_seconds,
                "success": success,
            },
            severity="info" if success else "warning",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=playbook_name)

    async def publish_circuit_breaker_opened(
        self,
        service_name: str,
        failure_count: int,
        last_error: str,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de circuit breaker abrindo."""
        event = SelfHealingEvent(
            event_type=EventType.CIRCUIT_BREAKER_OPENED,
            source="circuit_breaker",
            data={
                "service_name": service_name,
                "failure_count": failure_count,
                "last_error": last_error,
            },
            severity="warning",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=service_name)

    async def publish_memory_leak_detected(
        self,
        pod_name: str,
        namespace: str,
        usage_percent: float,
        duration_above_threshold: int,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publica evento de memory leak detectado."""
        event = SelfHealingEvent(
            event_type=EventType.MEMORY_LEAK_DETECTED,
            source="detection_service",
            data={
                "pod_name": pod_name,
                "namespace": namespace,
                "usage_percent": usage_percent,
                "duration_above_threshold_seconds": duration_above_threshold,
            },
            severity="warning",
            correlation_id=correlation_id,
        )
        return await self.publish_event(event, key=f"{namespace}/{pod_name}")

    async def publish_batch_events(
        self,
        events: list[SelfHealingEvent],
    ) -> dict[str, int]:
        """Publica múltiplos eventos em batch.

        Args:
            events: Lista de eventos a publicar

        Returns:
            Dict com contagem de sucessos e falhas
        """
        results = {"success": 0, "failed": 0}

        for event in events:
            success = await self.publish_event(event)
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

        return results
