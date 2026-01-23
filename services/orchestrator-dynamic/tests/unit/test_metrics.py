"""
Testes unitários para métricas do Orchestrator Dynamic.

Testa os métodos de registro de métricas de compensação e segurança.
"""
import pytest
from unittest.mock import MagicMock, patch, call


class TestCompensationMetrics:
    """Testes de métricas de compensação."""

    def test_record_compensation_duration(self):
        """Testa registro de duração de compensação."""
        with patch('observability.metrics.Histogram') as mock_histogram, \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            # Mock do histogram
            mock_labels = MagicMock()
            metrics.compensation_duration_seconds.labels = MagicMock(return_value=mock_labels)

            # Registra compensação
            metrics.record_compensation_duration(
                reason='task_failed',
                status='success',
                duration_seconds=5.5
            )

            # Verifica
            metrics.compensation_duration_seconds.labels.assert_called_once_with(
                reason='task_failed',
                status='success'
            )
            mock_labels.observe.assert_called_once_with(5.5)

    def test_record_compensation_duration_failed(self):
        """Testa registro de compensação que falhou."""
        with patch('observability.metrics.Histogram') as mock_histogram, \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            mock_labels = MagicMock()
            metrics.compensation_duration_seconds.labels = MagicMock(return_value=mock_labels)

            metrics.record_compensation_duration(
                reason='workflow_inconsistent',
                status='failed',
                duration_seconds=10.2
            )

            metrics.compensation_duration_seconds.labels.assert_called_once_with(
                reason='workflow_inconsistent',
                status='failed'
            )
            mock_labels.observe.assert_called_once_with(10.2)


class TestSecurityMetrics:
    """Testes de métricas de segurança."""

    def test_record_jwt_validation_failure(self):
        """Testa registro de falha de validação JWT."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            mock_labels = MagicMock()
            metrics.jwt_validation_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_jwt_validation_failure(
                tenant_id='tenant-123',
                reason='expired'
            )

            metrics.jwt_validation_failures_total.labels.assert_called_once_with(
                tenant_id='tenant-123',
                reason='expired'
            )
            mock_labels.inc.assert_called_once()

    def test_record_jwt_validation_failure_invalid_signature(self):
        """Testa registro de JWT com assinatura inválida."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            mock_labels = MagicMock()
            metrics.jwt_validation_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_jwt_validation_failure(
                tenant_id='tenant-456',
                reason='invalid_signature'
            )

            metrics.jwt_validation_failures_total.labels.assert_called_once_with(
                tenant_id='tenant-456',
                reason='invalid_signature'
            )
            mock_labels.inc.assert_called_once()

    def test_record_mtls_handshake_failure(self):
        """Testa registro de falha de handshake mTLS."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            mock_labels = MagicMock()
            metrics.mtls_handshake_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_mtls_handshake_failure(
                service='service-registry',
                reason='invalid_cert'
            )

            metrics.mtls_handshake_failures_total.labels.assert_called_once_with(
                service='service-registry',
                reason='invalid_cert'
            )
            mock_labels.inc.assert_called_once()

    def test_record_mtls_handshake_failure_expired_cert(self):
        """Testa registro de mTLS com certificado expirado."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            mock_labels = MagicMock()
            metrics.mtls_handshake_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_mtls_handshake_failure(
                service='execution-ticket-service',
                reason='expired_cert'
            )

            metrics.mtls_handshake_failures_total.labels.assert_called_once_with(
                service='execution-ticket-service',
                reason='expired_cert'
            )
            mock_labels.inc.assert_called_once()

    def test_record_mtls_handshake_failure_ca_mismatch(self):
        """Testa registro de mTLS com CA não confiável."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            mock_labels = MagicMock()
            metrics.mtls_handshake_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_mtls_handshake_failure(
                service='worker-agents',
                reason='ca_mismatch'
            )

            metrics.mtls_handshake_failures_total.labels.assert_called_once_with(
                service='worker-agents',
                reason='ca_mismatch'
            )
            mock_labels.inc.assert_called_once()


class TestMetricsInitialization:
    """Testes de inicialização de métricas."""

    def test_compensation_duration_histogram_initialized(self):
        """Verifica que histogram de compensação foi inicializado."""
        with patch('observability.metrics.Histogram') as mock_histogram, \
             patch('observability.metrics.Counter'), \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            # Verifica que Histogram foi chamado com os parâmetros corretos
            calls = [call for call in mock_histogram.call_args_list
                     if 'orchestration_compensation_duration_seconds' in str(call)]
            assert len(calls) == 1

    def test_jwt_failures_counter_initialized(self):
        """Verifica que counter de JWT foi inicializado."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter') as mock_counter, \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            calls = [call for call in mock_counter.call_args_list
                     if 'orchestration_jwt_validation_failures_total' in str(call)]
            assert len(calls) == 1

    def test_mtls_failures_counter_initialized(self):
        """Verifica que counter de mTLS foi inicializado."""
        with patch('observability.metrics.Histogram'), \
             patch('observability.metrics.Counter') as mock_counter, \
             patch('observability.metrics.Gauge'):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name='test', component='test')

            calls = [call for call in mock_counter.call_args_list
                     if 'orchestration_mtls_handshake_failures_total' in str(call)]
            assert len(calls) == 1
