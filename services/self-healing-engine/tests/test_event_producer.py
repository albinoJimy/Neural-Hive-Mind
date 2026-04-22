"""Testes para o Event Producer Kafka."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.services.event_producer import (
    EventProducer,
    EventType,
    SelfHealingEvent,
)


@pytest.fixture()
def mock_kafka_producer():
    """Mock do AIOKafkaProducer."""
    producer = MagicMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock(return_value=None)
    return producer


@pytest.fixture()
def event_producer(mock_kafka_producer):
    """EventProducer com Kafka mockado."""
    producer = EventProducer(
        bootstrap_servers="localhost:9092",
        topic="self-healing.events",
    )
    producer._producer = mock_kafka_producer
    return producer


class TestSelfHealingEvent:
    """Testes para SelfHealingEvent."""

    def test_event_to_dict(self):
        """Testa conversão para dicionário."""
        event = SelfHealingEvent(
            event_type=EventType.ANOMALY_DETECTED,
            source="detection_service",
            data={"anomaly_type": "memory_leak", "pod": "worker-1"},
            severity="warning",
        )

        result = event.to_dict()

        assert result["event_type"] == "anomaly.detected"
        assert result["source"] == "detection_service"
        assert result["severity"] == "warning"
        assert "timestamp" in result
        assert result["data"]["anomaly_type"] == "memory_leak"

    def test_event_to_json(self):
        """Testa conversão para JSON."""
        event = SelfHealingEvent(
            event_type=EventType.REMEDIATION_STARTED,
            source="remediation_manager",
            data={"remediation_id": "rem-123"},
        )

        json_str = event.to_json()

        assert isinstance(json_str, str)
        assert '"event_type": "remediation.started"' in json_str
        assert '"remediation_id": "rem-123"' in json_str


class TestKafkaEventProducer:
    """Testes para EventProducer."""

    @pytest.mark.asyncio()
    async def test_start(self, event_producer):
        """Testa inicialização do produtor."""
        await event_producer.start()
        assert event_producer._producer is not None

    @pytest.mark.asyncio()
    async def test_publish_event_success(self, event_producer, mock_kafka_producer):
        """Testa publicação de evento com sucesso."""
        event = SelfHealingEvent(
            event_type=EventType.ANOMALY_DETECTED,
            source="test",
            data={"test": "data"},
        )

        result = await event_producer.publish_event(event)

        assert result is True
        mock_kafka_producer.send_and_wait.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_anomaly_detected(self, event_producer, mock_kafka_producer):
        """Testa publicação de anomalia detectada."""
        result = await event_producer.publish_anomaly_detected(
            anomaly_type="memory_leak",
            entity_id="pod-123",
            details={"usage_percent": 95},
            severity="warning",
        )

        assert result is True
        mock_kafka_producer.send_and_wait.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_remediation_started(self, event_producer, mock_kafka_producer):
        """Testa publicação de remediação iniciada."""
        result = await event_producer.publish_remediation_started(
            remediation_id="rem-123",
            incident_type="memory_leak",
            playbook_name="memory_leak_recovery",
            context={"pod": "worker-1"},
        )

        assert result is True
        mock_kafka_producer.send_and_wait.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_remediation_completed(self, event_producer, mock_kafka_producer):
        """Testa publicação de remediação completada."""
        result = await event_producer.publish_remediation_completed(
            remediation_id="rem-123",
            result={"success": True, "actions": ["restart_pod"]},
            duration_seconds=45.5,
        )

        assert result is True

    @pytest.mark.asyncio()
    async def test_publish_remediation_failed(self, event_producer, mock_kafka_producer):
        """Testa publicação de falha na remediação."""
        result = await event_producer.publish_remediation_failed(
            remediation_id="rem-123",
            error="Timeout ao executar playbook",
            context={"playbook": "test"},
        )

        assert result is True

    @pytest.mark.asyncio()
    async def test_publish_health_check_failed(self, event_producer, mock_kafka_producer):
        """Testa publicação de health check falhando."""
        result = await event_producer.publish_health_check_failed(
            service_name="worker-agents",
            check_type="http_health",
            error="Connection refused",
            details={"url": "http://worker-agents:8080/health"},
        )

        assert result is True

    @pytest.mark.asyncio()
    async def test_publish_playbook_executed(self, event_producer, mock_kafka_producer):
        """Testa publicação de playbook executado."""
        result = await event_producer.publish_playbook_executed(
            playbook_name="test_playbook",
            action_count=3,
            duration_seconds=15.0,
            success=True,
        )

        assert result is True

    @pytest.mark.asyncio()
    async def test_publish_circuit_breaker_opened(self, event_producer, mock_kafka_producer):
        """Testa publicação de circuit breaker abrindo."""
        result = await event_producer.publish_circuit_breaker_opened(
            service_name="orchestrator",
            failure_count=5,
            last_error="Connection timeout",
        )

        assert result is True

    @pytest.mark.asyncio()
    async def test_publish_memory_leak_detected(self, event_producer, mock_kafka_producer):
        """Testa publicação de memory leak detectado."""
        result = await event_producer.publish_memory_leak_detected(
            pod_name="worker-1",
            namespace="default",
            usage_percent=95.0,
            duration_above_threshold=300,
        )

        assert result is True

    @pytest.mark.asyncio()
    async def test_publish_batch_events(self, event_producer, mock_kafka_producer):
        """Testa publicação em lote de múltiplos eventos."""
        events = [
            SelfHealingEvent(
                event_type=EventType.ANOMALY_DETECTED,
                source="test",
                data={"id": i},
            )
            for i in range(3)
        ]

        results = await event_producer.publish_batch_events(events)

        assert results["success"] == 3
        assert results["failed"] == 0
        assert mock_kafka_producer.send_and_wait.call_count == 3

    @pytest.mark.asyncio()
    async def test_publish_disabled(self, event_producer):
        """Testa que eventos são ignorados quando desabilitado."""
        event_producer.enabled = False

        event = SelfHealingEvent(
            event_type=EventType.ANOMALY_DETECTED,
            source="test",
            data={"test": "data"},
        )

        result = await event_producer.publish_event(event)

        assert result is False  # Não publicado

    @pytest.mark.asyncio()
    async def test_stop(self, event_producer, mock_kafka_producer):
        """Testa parada do produtor."""
        await event_producer.stop()

        mock_kafka_producer.stop.assert_called_once()
        assert event_producer._producer is None


class TestEventType:
    """Testes para EventType enum."""

    def test_all_event_types_defined(self):
        """Testa que todos os tipos de evento esperados estão definidos."""
        expected_types = {
            "anomaly.detected",
            "deadlock.detected",
            "memory_leak.detected",
            "kafka_lag.detected",
            "pod_crash_loop.detected",
            "database_connection.issue",
            "remediation.started",
            "remediation.completed",
            "remediation.failed",
            "remediation.cancelled",
            "playbook.executed",
            "playbook.validated",
            "playbook.validation_failed",
            "health_check.passed",
            "health_check.failed",
            "service.recovered",
            "service.degraded",
            "circuit_breaker.opened",
            "circuit_breaker.closed",
            "circuit_breaker.half_open",
        }

        actual_types = {t.value for t in EventType}

        assert expected_types.issubset(actual_types)
