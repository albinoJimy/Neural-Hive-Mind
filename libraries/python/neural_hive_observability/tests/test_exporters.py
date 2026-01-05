"""Testes para o módulo exporters do neural_hive_observability."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time

from neural_hive_observability.exporters import (
    ResilientOTLPSpanExporter,
    _sanitize_header_value,
    create_sanitized_headers,
)


class TestSanitizeHeaderValue:
    """Testes para função _sanitize_header_value."""

    def test_sanitize_normal_value(self):
        """Testa sanitização de valor normal."""
        result = _sanitize_header_value("service-name")
        assert result == "service-name"

    def test_sanitize_percent_character(self):
        """Testa remoção de caractere % que causa bug no OTEL 1.39.1."""
        result = _sanitize_header_value("value%with%percent")
        assert result == "valuewithpercent"
        assert "%" not in result

    def test_sanitize_curly_braces(self):
        """Testa remoção de chaves que podem causar problemas de formatação."""
        result = _sanitize_header_value("value{with}braces")
        assert result == "valuewithbraces"
        assert "{" not in result
        assert "}" not in result

    def test_sanitize_newlines(self):
        """Testa remoção de quebras de linha."""
        result = _sanitize_header_value("value\nwith\rnewlines")
        assert result == "valuewithnewlines"
        assert "\n" not in result
        assert "\r" not in result

    def test_sanitize_tabs(self):
        """Testa remoção de tabs."""
        result = _sanitize_header_value("value\twith\ttabs")
        assert result == "valuewithtabs"
        assert "\t" not in result

    def test_sanitize_null_character(self):
        """Testa remoção de caractere nulo."""
        result = _sanitize_header_value("value\x00with\x00null")
        assert result == "valuewithnull"
        assert "\x00" not in result

    def test_sanitize_truncates_long_value(self):
        """Testa truncamento de valores muito longos."""
        long_value = "a" * 200
        result = _sanitize_header_value(long_value, max_length=100)
        assert len(result) == 100

    def test_sanitize_none_value(self):
        """Testa sanitização de valor None."""
        result = _sanitize_header_value(None)
        assert result == ""

    def test_sanitize_non_string_value(self):
        """Testa sanitização de valor não-string."""
        result = _sanitize_header_value(12345)
        assert result == "12345"

    def test_sanitize_empty_string(self):
        """Testa sanitização de string vazia."""
        result = _sanitize_header_value("")
        assert result == ""

    def test_sanitize_complex_problematic_value(self):
        """Testa sanitização de valor com múltiplos caracteres problemáticos."""
        result = _sanitize_header_value("test%value{with}many\nproblems\r\x00")
        assert result == "testvaluewithmanyproblems"


class TestCreateSanitizedHeaders:
    """Testes para função create_sanitized_headers."""

    def test_sanitize_empty_headers(self):
        """Testa sanitização de headers vazios."""
        result = create_sanitized_headers({})
        assert result == {}

    def test_sanitize_none_headers(self):
        """Testa sanitização de None."""
        result = create_sanitized_headers(None)
        assert result == {}

    def test_sanitize_normal_headers(self):
        """Testa sanitização de headers normais."""
        headers = {
            "X-Service-Name": "my-service",
            "X-Component": "gateway"
        }
        result = create_sanitized_headers(headers)
        assert result == headers

    def test_sanitize_problematic_headers(self):
        """Testa sanitização de headers problemáticos."""
        headers = {
            "X-Service-Name": "my%service",
            "X-Component": "gateway{test}"
        }
        result = create_sanitized_headers(headers)
        assert result["X-Service-Name"] == "myservice"
        assert result["X-Component"] == "gatewaytest"


class TestResilientOTLPSpanExporter:
    """Testes para ResilientOTLPSpanExporter."""

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_initialization(self, mock_otlp_class):
        """Testa inicialização do exporter resiliente."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            headers={"X-Test": "value"}
        )

        assert exporter._service_name == "test-service"
        assert exporter._endpoint == "http://localhost:4317"
        assert exporter._failure_count == 0
        assert exporter._success_count == 0
        mock_otlp_class.assert_called_once()

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_export_success(self, mock_otlp_class):
        """Testa export bem-sucedido."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        mock_inner.export.return_value = SpanExportResult.SUCCESS
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock(), Mock()]
        result = exporter.export(mock_spans)

        assert result == SpanExportResult.SUCCESS
        assert exporter.success_count == 1
        assert exporter.failure_count == 0
        mock_inner.export.assert_called_once_with(mock_spans)

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_export_catches_typeerror(self, mock_otlp_class):
        """Testa que TypeError é capturado e não propagado."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        mock_inner.export.side_effect = TypeError("not all arguments converted during string formatting")
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock()]
        result = exporter.export(mock_spans)

        # Deve retornar FAILURE, não propagar exceção
        assert result == SpanExportResult.FAILURE
        assert exporter.failure_count == 1
        assert exporter.success_count == 0

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_export_catches_generic_exception(self, mock_otlp_class):
        """Testa que exceções genéricas são capturadas."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        mock_inner.export.side_effect = RuntimeError("Connection failed")
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock()]
        result = exporter.export(mock_spans)

        assert result == SpanExportResult.FAILURE
        assert exporter.failure_count == 1

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_export_empty_spans(self, mock_otlp_class):
        """Testa export com lista vazia de spans."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        result = exporter.export([])

        # Deve retornar SUCCESS sem chamar inner exporter
        assert result == SpanExportResult.SUCCESS
        mock_inner.export.assert_not_called()

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_export_without_inner_exporter(self, mock_otlp_class):
        """Testa export quando inner exporter não está disponível."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_otlp_class.side_effect = RuntimeError("Failed to create exporter")

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock()]
        result = exporter.export(mock_spans)

        assert result == SpanExportResult.FAILURE

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_shutdown(self, mock_otlp_class):
        """Testa shutdown do exporter."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        exporter.shutdown()

        mock_inner.shutdown.assert_called_once()

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_shutdown_handles_exception(self, mock_otlp_class):
        """Testa que shutdown trata exceções graciosamente."""
        mock_inner = Mock()
        mock_inner.shutdown.side_effect = RuntimeError("Shutdown failed")
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        # Não deve propagar exceção
        exporter.shutdown()

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_force_flush(self, mock_otlp_class):
        """Testa force_flush do exporter."""
        mock_inner = Mock()
        mock_inner.force_flush.return_value = True
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        result = exporter.force_flush(timeout_millis=5000)

        assert result is True
        mock_inner.force_flush.assert_called_once_with(5000)

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_force_flush_handles_exception(self, mock_otlp_class):
        """Testa que force_flush trata exceções."""
        mock_inner = Mock()
        mock_inner.force_flush.side_effect = RuntimeError("Flush failed")
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        result = exporter.force_flush()

        assert result is False

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_header_sanitization_on_init(self, mock_otlp_class):
        """Testa que headers são sanitizados durante inicialização."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        headers_with_problems = {
            "X-Service": "my%service",
            "X-Component": "test{component}"
        }

        ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            headers=headers_with_problems
        )

        # Verificar que OTLP foi criado com headers sanitizados
        call_kwargs = mock_otlp_class.call_args[1]
        assert call_kwargs['headers']['X-Service'] == "myservice"
        assert call_kwargs['headers']['X-Component'] == "testcomponent"

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_multiple_export_failures_counted(self, mock_otlp_class):
        """Testa que múltiplas falhas são contabilizadas."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        mock_inner.export.side_effect = TypeError("Error")
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock()]

        # Executar 3 exports que vão falhar
        for _ in range(3):
            exporter.export(mock_spans)

        assert exporter.failure_count == 3
        assert exporter.success_count == 0

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_mixed_success_and_failure(self, mock_otlp_class):
        """Testa contagem mista de sucesso e falha."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        # Primeiro sucesso, depois falha, depois sucesso
        mock_inner.export.side_effect = [
            SpanExportResult.SUCCESS,
            TypeError("Error"),
            SpanExportResult.SUCCESS
        ]
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock()]

        exporter.export(mock_spans)  # Sucesso
        exporter.export(mock_spans)  # Falha
        exporter.export(mock_spans)  # Sucesso

        assert exporter.success_count == 2
        assert exporter.failure_count == 1


class TestExporterMetrics:
    """Testes para métricas do exporter."""

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    @patch('neural_hive_observability.exporters._export_failure_counter')
    @patch('neural_hive_observability.exporters._export_duration_histogram')
    def test_metrics_recorded_on_failure(self, mock_histogram, mock_counter, mock_otlp_class):
        """Testa que métricas são registradas em caso de falha."""
        from opentelemetry.sdk.trace.export import SpanExportResult

        mock_inner = Mock()
        mock_inner.export.side_effect = TypeError("Error")
        mock_otlp_class.return_value = mock_inner

        # Configurar mocks de métricas
        mock_counter_labels = Mock()
        mock_counter.labels.return_value = mock_counter_labels

        mock_histogram_labels = Mock()
        mock_histogram.labels.return_value = mock_histogram_labels

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        mock_spans = [Mock()]
        exporter.export(mock_spans)

        # Verificar que contador foi incrementado
        if mock_counter is not None:
            mock_counter.labels.assert_called()
            mock_counter_labels.inc.assert_called()


class TestTLSConfiguration:
    """Testes para configuração TLS do ResilientOTLPSpanExporter."""

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_tls_disabled_by_default(self, mock_otlp_class):
        """Testa que TLS está desabilitado por padrão."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service"
        )

        # Verificar que insecure=True foi passado
        call_kwargs = mock_otlp_class.call_args[1]
        assert call_kwargs.get('insecure') is True
        assert 'credentials' not in call_kwargs

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_tls_enabled_without_certs_does_not_fallback_to_insecure(self, mock_otlp_class):
        """Testa que TLS sem certificados NÃO faz fallback para insecure."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            tls_enabled=True,
            tls_cert_path="/nonexistent/cert.pem"
        )

        # Exporter should NOT be initialized (no silent fallback to insecure)
        assert exporter._inner_exporter is None
        assert exporter._tls_enabled is False

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    @patch('neural_hive_observability.exporters.grpc.ssl_channel_credentials')
    @patch('builtins.open', create=True)
    @patch('os.path.exists')
    def test_tls_enabled_with_valid_certs(self, mock_exists, mock_open, mock_ssl_creds, mock_otlp_class):
        """Testa TLS com certificados válidos."""
        import io

        # Simular arquivos de certificado existentes
        mock_exists.return_value = True

        # Simular leitura de arquivos
        cert_content = b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
        key_content = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        ca_content = b"-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----"

        def open_side_effect(path, *args, **kwargs):
            if 'cert' in path and 'ca' not in path:
                return io.BytesIO(cert_content)
            elif 'key' in path:
                return io.BytesIO(key_content)
            elif 'ca' in path:
                return io.BytesIO(ca_content)
            return io.BytesIO(b"")

        mock_open.side_effect = open_side_effect

        mock_credentials = Mock()
        mock_ssl_creds.return_value = mock_credentials

        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="https://localhost:4317",
            service_name="test-service",
            tls_enabled=True,
            tls_cert_path="/etc/tls/cert.pem",
            tls_key_path="/etc/tls/key.pem",
            tls_ca_cert_path="/etc/tls/ca.crt"
        )

        # Verificar que credentials foi passado
        call_kwargs = mock_otlp_class.call_args[1]
        assert 'credentials' in call_kwargs or 'insecure' not in call_kwargs or call_kwargs.get('insecure') is False

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    @patch('neural_hive_observability.exporters.grpc.ssl_channel_credentials')
    def test_tls_insecure_skip_verify(self, mock_ssl_creds, mock_otlp_class):
        """Testa parâmetro insecure_skip_verify."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        mock_credentials = Mock()
        mock_ssl_creds.return_value = mock_credentials

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            tls_enabled=True,
            tls_insecure_skip_verify=True
        )

        # Exporter should be created with TLS credentials (even without CA)
        assert exporter._inner_exporter is not None
        # ssl_channel_credentials should be called (with None root_certificates when skipping verify)
        mock_ssl_creds.assert_called_once()

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_tls_status_logged(self, mock_otlp_class):
        """Testa que status TLS é logado corretamente."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        # Com TLS desabilitado
        exporter_insecure = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            tls_enabled=False
        )
        assert exporter_insecure._tls_enabled is False
        assert exporter_insecure._inner_exporter is not None

        # Com TLS habilitado sem certificados - exporter não deve ser inicializado
        exporter_tls = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            tls_enabled=True
        )
        # Sem certificados válidos, exporter não é inicializado (não faz fallback silencioso)
        assert exporter_tls._tls_enabled is False
        assert exporter_tls._inner_exporter is None

    @patch('neural_hive_observability.exporters.OTLPSpanExporter')
    def test_tls_enabled_without_certs_logs_error(self, mock_otlp_class):
        """Testa que TLS sem certificados loga erro e não inicializa exporter."""
        mock_inner = Mock()
        mock_otlp_class.return_value = mock_inner

        exporter = ResilientOTLPSpanExporter(
            endpoint="http://localhost:4317",
            service_name="test-service",
            tls_enabled=True,
            tls_ca_cert_path="/nonexistent/ca.crt"
        )

        # Exporter não deve ser inicializado
        assert exporter._inner_exporter is None
        # TLS deve estar desabilitado
        assert exporter._tls_enabled is False
        # OTLPSpanExporter não deve ter sido chamado
        mock_otlp_class.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
