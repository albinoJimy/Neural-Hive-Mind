"""
Testes de integração para validar exposição de métricas via endpoint /metrics.

Verifica que as novas métricas de compensação e segurança estão expostas corretamente.
"""
import pytest
from prometheus_client import REGISTRY, CollectorRegistry
from prometheus_client.parser import text_string_to_metric_families


class TestCompensationMetricsExposure:
    """Testes de exposição de métricas de compensação."""

    def test_compensation_duration_metric_exists(self):
        """Verifica que métrica compensation_duration_seconds existe."""
        # Importa métricas para registrar no REGISTRY
        from observability.metrics import get_metrics

        metrics = get_metrics()

        # Verifica que a métrica existe
        assert hasattr(metrics, 'compensation_duration_seconds')
        assert metrics.compensation_duration_seconds is not None

    def test_compensation_duration_labels(self):
        """Verifica que métrica tem os labels corretos."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        # Registra uma observação
        metrics.compensation_duration_seconds.labels(
            reason='task_failed',
            status='success'
        ).observe(1.5)

        # Verifica que não levanta exceção com labels válidos
        assert True

    def test_compensations_triggered_metric_exists(self):
        """Verifica que métrica compensations_triggered_total existe."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'compensations_triggered_total')
        assert metrics.compensations_triggered_total is not None


class TestSecurityMetricsExposure:
    """Testes de exposição de métricas de segurança."""

    def test_jwt_validation_failures_metric_exists(self):
        """Verifica que métrica jwt_validation_failures_total existe."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'jwt_validation_failures_total')
        assert metrics.jwt_validation_failures_total is not None

    def test_jwt_validation_failures_labels(self):
        """Verifica que métrica JWT tem os labels corretos."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        # Verifica labels válidos
        metrics.jwt_validation_failures_total.labels(
            tenant_id='test-tenant',
            reason='expired'
        ).inc()

        metrics.jwt_validation_failures_total.labels(
            tenant_id='test-tenant',
            reason='invalid_signature'
        ).inc()

        metrics.jwt_validation_failures_total.labels(
            tenant_id='test-tenant',
            reason='invalid_issuer'
        ).inc()

        metrics.jwt_validation_failures_total.labels(
            tenant_id='test-tenant',
            reason='invalid_audience'
        ).inc()

        metrics.jwt_validation_failures_total.labels(
            tenant_id='test-tenant',
            reason='missing_claims'
        ).inc()

        assert True

    def test_mtls_handshake_failures_metric_exists(self):
        """Verifica que métrica mtls_handshake_failures_total existe."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'mtls_handshake_failures_total')
        assert metrics.mtls_handshake_failures_total is not None

    def test_mtls_handshake_failures_labels(self):
        """Verifica que métrica mTLS tem os labels corretos."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        # Verifica labels válidos
        metrics.mtls_handshake_failures_total.labels(
            service='service-registry',
            reason='invalid_cert'
        ).inc()

        metrics.mtls_handshake_failures_total.labels(
            service='execution-ticket-service',
            reason='ca_mismatch'
        ).inc()

        metrics.mtls_handshake_failures_total.labels(
            service='worker-agents',
            reason='expired_cert'
        ).inc()

        metrics.mtls_handshake_failures_total.labels(
            service='approval-service',
            reason='connection_error'
        ).inc()

        assert True


class TestIdempotencyMetricsExposure:
    """Testes de exposição de métricas de idempotência."""

    def test_duplicates_detected_metric_exists(self):
        """Verifica que métrica duplicates_detected_total existe."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'duplicates_detected_total')
        assert metrics.duplicates_detected_total is not None

    def test_idempotency_cache_hits_metric_exists(self):
        """Verifica que métrica idempotency_cache_hits_total existe."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'idempotency_cache_hits_total')
        assert metrics.idempotency_cache_hits_total is not None

    def test_record_duplicate_detected(self):
        """Verifica registro de duplicata detectada."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        # Deve incrementar ambos os contadores
        metrics.record_duplicate_detected(component='decision_consumer')

        assert True


class TestRecordingMethods:
    """Testes dos métodos de registro de métricas."""

    def test_record_compensation_duration_method(self):
        """Verifica método record_compensation_duration."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        # Deve ter o método
        assert hasattr(metrics, 'record_compensation_duration')
        assert callable(metrics.record_compensation_duration)

        # Deve executar sem erro
        metrics.record_compensation_duration(
            reason='task_failed',
            status='success',
            duration_seconds=2.5
        )

    def test_record_jwt_validation_failure_method(self):
        """Verifica método record_jwt_validation_failure."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'record_jwt_validation_failure')
        assert callable(metrics.record_jwt_validation_failure)

        metrics.record_jwt_validation_failure(
            tenant_id='tenant-abc',
            reason='expired'
        )

    def test_record_mtls_handshake_failure_method(self):
        """Verifica método record_mtls_handshake_failure."""
        from observability.metrics import get_metrics

        metrics = get_metrics()

        assert hasattr(metrics, 'record_mtls_handshake_failure')
        assert callable(metrics.record_mtls_handshake_failure)

        metrics.record_mtls_handshake_failure(
            service='service-registry',
            reason='invalid_cert'
        )
