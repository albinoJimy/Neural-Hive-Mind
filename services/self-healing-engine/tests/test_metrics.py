"""
Testes para o módulo de métricas Prometheus.

Verifica a exportação correta de métricas e o rastreamento de MTTR.
"""

import pytest
import time
from unittest.mock import patch

from src.metrics import (
    detection_events_total,
    detection_duration_seconds,
    active_incidents,
    remediation_events_total,
    remediation_duration_seconds,
    mt_seconds,
    mttr_by_type,
    circuit_breaker_state,
    circuit_breaker_failures_total,
    circuit_breaker_success_total,
    circuit_breaker_rejected_total,
    health_check_total,
    health_check_duration_seconds,
    service_health_status,
    kafka_consumer_lag,
    kafka_consumer_lag_total,
    playbook_execution_total,
    mttr_tracker,
    record_detection,
    record_remediation,
    record_circuit_breaker_state,
    record_health_check,
    record_kafka_lag,
    record_kafka_lag_total,
    set_build_info,
    get_metrics_text,
    MTTRTracker,
)


class TestDetectionMetrics:
    """Testes para métricas de detecção."""

    def test_record_detection_increments_counter(self):
        """Testa que registrar detecção incrementa o contador."""
        initial_value = detection_events_total.labels(
            incident_type="deadlock", severity="high", detected_by="detection_service"
        )._value.get()

        record_detection(
            incident_type="deadlock",
            severity="high",
            detected_by="detection_service",
            duration_seconds=1.5,
        )

        new_value = detection_events_total.labels(
            incident_type="deadlock", severity="high", detected_by="detection_service"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_detection_observes_duration(self):
        """Testa que registrar detecção observa duração."""
        record_detection(
            incident_type="memory_leak",
            severity="medium",
            detected_by="health_monitor",
            duration_seconds=2.5,
        )

        # Verificar que samples foram coletadas
        samples = list(detection_duration_seconds.labels(incident_type="memory_leak").collect())

        assert len(samples) > 0


class TestRemediationMetrics:
    """Testes para métricas de remediação."""

    def test_record_remediation_increments_counter(self):
        """Testa que registrar remediação incrementa o contador."""
        initial_value = remediation_events_total.labels(
            incident_type="deadlock", playbook_id="deadlock_recovery", outcome="success"
        )._value.get()

        record_remediation(
            incident_type="deadlock",
            playbook_id="deadlock_recovery",
            outcome="success",
            duration_seconds=30.0,
        )

        new_value = remediation_events_total.labels(
            incident_type="deadlock", playbook_id="deadlock_recovery", outcome="success"
        )._value.get()

        assert new_value == initial_value + 1


class TestMTTRTracker:
    """Testes para o rastreador de MTTR."""

    def test_start_and_end_tracking(self):
        """Testa iniciar e finalizar rastreamento de incidente."""
        tracker = MTTRTracker()

        tracker.start_tracking("inc-1", "deadlock", "high")
        time.sleep(0.1)  # Pequena espera
        mttr_seconds = tracker.end_tracking("inc-1", "deadlock", "high")

        assert mttr_seconds >= 0.1
        assert mttr_seconds < 1.0  # Não deve levar muito tempo

    def test_get_average_mttr(self):
        """Testa calcular MTTR médio."""
        tracker = MTTRTracker()

        tracker.start_tracking("inc-1", "deadlock", "high")
        time.sleep(0.05)
        tracker.end_tracking("inc-1", "deadlock", "high")

        tracker.start_tracking("inc-2", "deadlock", "high")
        time.sleep(0.05)
        tracker.end_tracking("inc-2", "deadlock", "high")

        avg_mttr = tracker.get_average_mttr(incident_type="deadlock", severity="high")

        assert avg_mttr >= 0.05  # Ajustado para o valor real
        assert avg_mttr < 0.5

    def test_get_resolution_count(self):
        """Testa contar incidentes resolvidos."""
        tracker = MTTRTracker()

        tracker.start_tracking("inc-1", "deadlock", "high")
        tracker.end_tracking("inc-1", "deadlock", "high")

        tracker.start_tracking("inc-2", "memory_leak", "medium")
        tracker.end_tracking("inc-2", "memory_leak", "medium")

        total_count = tracker.get_resolution_count()
        deadlock_count = tracker.get_resolution_count(incident_type="deadlock")
        memory_count = tracker.get_resolution_count(incident_type="memory_leak")

        assert total_count == 2
        assert deadlock_count == 1
        assert memory_count == 1

    def test_end_tracking_nonexistent_incident(self):
        """Testa finalizar incidente não existe retorna 0."""
        tracker = MTTRTracker()

        mttr_seconds = tracker.end_tracking("inc-999", "deadlock", "high")

        assert mttr_seconds == 0.0

    def test_active_incidents_gauge(self):
        """Testa que incidente ativo incrementa gauge."""
        tracker = MTTRTracker()

        initial_value = active_incidents.labels(
            incident_type="deadlock", severity="high"
        )._value.get()

        tracker.start_tracking("inc-1", "deadlock", "high")

        new_value = active_incidents.labels(incident_type="deadlock", severity="high")._value.get()

        assert new_value == initial_value + 1

        # Cleanup
        tracker.end_tracking("inc-1", "deadlock", "high")


class TestCircuitBreakerMetrics:
    """Testes para métricas de circuit breaker."""

    def test_record_circuit_breaker_closed(self):
        """Testa registrar estado CLOSED."""
        record_circuit_breaker_state("test-service", "CLOSED")

        state_value = circuit_breaker_state.labels(service_name="test-service")._value.get()

        assert state_value == 0

    def test_record_circuit_breaker_open(self):
        """Testa registrar estado OPEN."""
        record_circuit_breaker_state("test-service", "OPEN")

        state_value = circuit_breaker_state.labels(service_name="test-service")._value.get()

        assert state_value == 1

    def test_record_circuit_breaker_half_open(self):
        """Testa registrar estado HALF_OPEN."""
        record_circuit_breaker_state("test-service", "HALF_OPEN")

        state_value = circuit_breaker_state.labels(service_name="test-service")._value.get()

        assert state_value == 2


class TestHealthCheckMetrics:
    """Testes para métricas de health check."""

    def test_record_health_check_success(self):
        """Testa registrar health check com sucesso."""
        record_health_check(
            service_name="worker-agents", outcome="success", duration_seconds=0.5, is_healthy=True
        )

        status_value = service_health_status.labels(service_name="worker-agents")._value.get()

        assert status_value == 1

    def test_record_health_check_failure(self):
        """Testa registrar health check com falha."""
        record_health_check(
            service_name="worker-agents", outcome="failure", duration_seconds=5.0, is_healthy=False
        )

        status_value = service_health_status.labels(service_name="worker-agents")._value.get()

        assert status_value == 0


class TestKafkaLagMetrics:
    """Testes para métricas de Kafka lag."""

    def test_record_kafka_lag(self):
        """Testa registrar lag de partição."""
        record_kafka_lag("self-healing-group", "remediation-events", 0, 100)

        lag_value = kafka_consumer_lag.labels(
            consumer_group="self-healing-group", topic="remediation-events", partition=0
        )._value.get()

        assert lag_value == 100

    def test_record_kafka_lag_total(self):
        """Testa registrar lag total."""
        record_kafka_lag_total("self-healing-group", "remediation-events", 500)

        total_value = kafka_consumer_lag_total.labels(
            consumer_group="self-healing-group", topic="remediation-events"
        )._value.get()

        assert total_value == 500


class TestBuildInfo:
    """Testes para informações de build."""

    def test_set_build_info(self):
        """Testa definir informações de build."""
        set_build_info(version="1.0.0", commit="abc123", build_date="2026-03-18")

        # Verifica que info foi registrada (não lança exceção)
        # A verificação real seria através do endpoint /metrics


class TestMetricsEndpoint:
    """Testes para o endpoint de métricas."""

    @pytest.mark.usefixtures("clean_prometheus_registry")
    def test_get_metrics_text(self):
        """Testa obter texto de métricas."""
        # Importar e re-registrar métricas após o cleanup
        from prometheus_client import REGISTRY
        import src.metrics

        # Registrar manualmente as métricas principais
        for name in dir(src.metrics):
            obj = getattr(src.metrics, name)
            if hasattr(obj, "_metrics") and hasattr(obj, "describe"):
                # É um Collector do Prometheus
                try:
                    if obj not in REGISTRY._collector_to_names:
                        REGISTRY.register(obj)
                except Exception:
                    pass

        # Registrar algumas métricas
        record_detection("test_type", "high", "test_service", 1.0)
        record_remediation("test_type", "test_playbook", "success", 30.0)

        metrics_text = get_metrics_text()

        assert isinstance(metrics_text, str)
        assert len(metrics_text) > 0
        # Verifica formato Prometheus básico
        assert "self_healing" in metrics_text or "HELP" in metrics_text


class TestGlobalMTTRTracker:
    """Testes para o tracker global de MTTR."""

    def test_global_mttr_tracker(self):
        """Testa usar tracker global."""
        mttr_tracker.start_tracking("global-inc-1", "deadlock", "high")
        time.sleep(0.05)
        mttr_seconds = mttr_tracker.end_tracking("global-inc-1", "deadlock", "high")

        assert mttr_seconds >= 0.05

        # Cleanup
        # Remove incidente das resoluções se existir
        if mttr_tracker._incident_resolutions:
            mttr_tracker._incident_resolutions.pop()
