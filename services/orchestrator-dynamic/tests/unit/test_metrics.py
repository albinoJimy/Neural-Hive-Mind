"""
Testes unitários para métricas do Orchestrator Dynamic.

Testa os métodos de registro de métricas de compensação e segurança.
"""

from unittest.mock import MagicMock, patch


class TestCompensationMetrics:
    """Testes de métricas de compensação."""

    def test_record_compensation_duration(self):
        """Testa registro de duração de compensação."""
        with (
            patch("observability.metrics.Histogram") as mock_histogram,
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            # Mock do histogram
            mock_labels = MagicMock()
            metrics.compensation_duration_seconds.labels = MagicMock(return_value=mock_labels)

            # Registra compensação
            metrics.record_compensation_duration(
                reason="task_failed", status="success", duration_seconds=5.5
            )

            # Verifica
            metrics.compensation_duration_seconds.labels.assert_called_once_with(
                reason="task_failed", status="success"
            )
            mock_labels.observe.assert_called_once_with(5.5)

    def test_record_compensation_duration_failed(self):
        """Testa registro de compensação que falhou."""
        with (
            patch("observability.metrics.Histogram") as mock_histogram,
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.compensation_duration_seconds.labels = MagicMock(return_value=mock_labels)

            metrics.record_compensation_duration(
                reason="workflow_inconsistent", status="failed", duration_seconds=10.2
            )

            metrics.compensation_duration_seconds.labels.assert_called_once_with(
                reason="workflow_inconsistent", status="failed"
            )
            mock_labels.observe.assert_called_once_with(10.2)


class TestSecurityMetrics:
    """Testes de métricas de segurança."""

    def test_record_jwt_validation_failure(self):
        """Testa registro de falha de validação JWT."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.jwt_validation_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_jwt_validation_failure(tenant_id="tenant-123", reason="expired")

            metrics.jwt_validation_failures_total.labels.assert_called_once_with(
                tenant_id="tenant-123", reason="expired"
            )
            mock_labels.inc.assert_called_once()

    def test_record_jwt_validation_failure_invalid_signature(self):
        """Testa registro de JWT com assinatura inválida."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.jwt_validation_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_jwt_validation_failure(
                tenant_id="tenant-456", reason="invalid_signature"
            )

            metrics.jwt_validation_failures_total.labels.assert_called_once_with(
                tenant_id="tenant-456", reason="invalid_signature"
            )
            mock_labels.inc.assert_called_once()

    def test_record_mtls_handshake_failure(self):
        """Testa registro de falha de handshake mTLS."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.mtls_handshake_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_mtls_handshake_failure(service="service-registry", reason="invalid_cert")

            metrics.mtls_handshake_failures_total.labels.assert_called_once_with(
                service="service-registry", reason="invalid_cert"
            )
            mock_labels.inc.assert_called_once()

    def test_record_mtls_handshake_failure_expired_cert(self):
        """Testa registro de mTLS com certificado expirado."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.mtls_handshake_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_mtls_handshake_failure(
                service="execution-ticket-service", reason="expired_cert"
            )

            metrics.mtls_handshake_failures_total.labels.assert_called_once_with(
                service="execution-ticket-service", reason="expired_cert"
            )
            mock_labels.inc.assert_called_once()

    def test_record_mtls_handshake_failure_ca_mismatch(self):
        """Testa registro de mTLS com CA não confiável."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.mtls_handshake_failures_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_mtls_handshake_failure(service="worker-agents", reason="ca_mismatch")

            metrics.mtls_handshake_failures_total.labels.assert_called_once_with(
                service="worker-agents", reason="ca_mismatch"
            )
            mock_labels.inc.assert_called_once()


class TestMetricsInitialization:
    """Testes de inicialização de métricas."""

    def test_compensation_duration_histogram_initialized(self):
        """Verifica que histogram de compensação foi inicializado."""
        with (
            patch("observability.metrics.Histogram") as mock_histogram,
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            # Verifica que Histogram foi chamado com os parâmetros corretos
            calls = [
                call
                for call in mock_histogram.call_args_list
                if "orchestration_compensation_duration_seconds" in str(call)
            ]
            assert len(calls) == 1

    def test_jwt_failures_counter_initialized(self):
        """Verifica que counter de JWT foi inicializado."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter") as mock_counter,
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            calls = [
                call
                for call in mock_counter.call_args_list
                if "orchestration_jwt_validation_failures_total" in str(call)
            ]
            assert len(calls) == 1

    def test_mtls_failures_counter_initialized(self):
        """Verifica que counter de mTLS foi inicializado."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter") as mock_counter,
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            calls = [
                call
                for call in mock_counter.call_args_list
                if "orchestration_mtls_handshake_failures_total" in str(call)
            ]
            assert len(calls) == 1


class TestDriftMetrics:
    """Testes de métricas de drift ML."""

    def test_record_drift_detected_feature_warning(self):
        """Testa registro de drift detectado com severity warning."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.ml_drift_detected_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_drift_detected(
                model_version="v7",
                drift_type="feature",
                feature="complexity",
                severity="warning",
            )

            metrics.ml_drift_detected_total.labels.assert_called_once_with(
                model_version="v7", drift_type="feature", feature="complexity", severity="warning"
            )
            mock_labels.inc.assert_called_once()

    def test_record_drift_detected_prediction_critical(self):
        """Testa registro de drift detectado com severity critical."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.ml_drift_detected_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_drift_detected(
                model_version="v7",
                drift_type="prediction",
                feature="duration_ms",
                severity="critical",
            )

            metrics.ml_drift_detected_total.labels.assert_called_once_with(
                model_version="v7",
                drift_type="prediction",
                feature="duration_ms",
                severity="critical",
            )
            mock_labels.inc.assert_called_once()

    def test_drift_detected_counter_initialized(self):
        """Verifica que Counter de drift detectado foi inicializado."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter") as mock_counter,
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            calls = [
                call
                for call in mock_counter.call_args_list
                if "ml_drift_detected_total" in str(call)
            ]
            assert len(calls) == 1


class TestJourneyExecutionResultMetric:
    """Label `journey` na métrica de resultados de execução — Fase 4 / Task 5.2.

    A métrica orchestration_execution_results_processed_total é o ponto natural
    de segmentação por jornada no fecho do loop (C6/LEARN): o ExecutionFeedback
    já carrega journey_id, logo o consumer tem o journey disponível.
    """

    def test_execution_results_processed_declares_journey_label(self):
        """O Counter é inicializado com os labels status e journey."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter") as mock_counter,
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            OrchestratorMetrics(service_name="test", component="test")

            matching = [
                c
                for c in mock_counter.call_args_list
                if "orchestration_execution_results_processed_total" in str(c)
            ]
            assert len(matching) == 1
            # O 3º argumento posicional é a lista de labels.
            labels_arg = matching[0].args[2]
            assert "status" in labels_arg
            assert "journey" in labels_arg

    def test_record_execution_result_processed_passes_journey(self):
        """O helper regista status + journey no Counter."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.execution_results_processed_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_execution_result_processed(status="COMPLETED", journey="J4_MIGRATE")

            metrics.execution_results_processed_total.labels.assert_called_once_with(
                status="COMPLETED", journey="J4_MIGRATE"
            )
            mock_labels.inc.assert_called_once()

    def test_record_execution_result_processed_journey_defaults_unknown(self):
        """Sem journey explícito, o helper usa 'unknown' (retrocompat)."""
        with (
            patch("observability.metrics.Histogram"),
            patch("observability.metrics.Counter"),
            patch("observability.metrics.Gauge"),
        ):
            from observability.metrics import OrchestratorMetrics

            metrics = OrchestratorMetrics(service_name="test", component="test")

            mock_labels = MagicMock()
            metrics.execution_results_processed_total.labels = MagicMock(return_value=mock_labels)

            metrics.record_execution_result_processed(status="FAILED")

            metrics.execution_results_processed_total.labels.assert_called_once_with(
                status="FAILED", journey="unknown"
            )
            mock_labels.inc.assert_called_once()
