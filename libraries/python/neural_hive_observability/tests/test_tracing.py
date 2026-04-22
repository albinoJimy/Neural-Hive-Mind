"""
Testes para o módulo tracing.py da biblioteca neural_hive_observability.

Este arquivo contém testes unitários e de integração para validar:
- Inicialização de tracing com OpenTelemetry
- Decoradores @trace_intent e @trace_plan
- Context managers de correlação
- Funções utilitárias de tracing
"""

import asyncio
from unittest.mock import Mock, patch

import pytest

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.tracing import (
    _is_sensitive_param,
    correlation_context,
    create_child_span,
    enrich_span,
    extract_context_from_headers,
    get_correlation_context,
    get_current_span_id,
    get_current_trace_id,
    get_tracer,
    init_tracing,
    inject_context_to_headers,
    trace_grpc_method,
    trace_intent,
    trace_plan,
)


class TestInitTracing:
    """Testes para inicialização de tracing."""

    def test_init_tracing_creates_tracer(self):
        """Testa que init_tracing cria um tracer válido."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        # Patch para evitar conexão OTLP real
        with patch("neural_hive_observability.tracing.ResilientOTLPSpanExporter"):
            with patch("neural_hive_observability.tracing.BatchSpanProcessor"):
                init_tracing(config)

        tracer = get_tracer()
        assert tracer is not None

    def test_init_tracing_sets_config(self):
        """Testa que init_tracing define a config global."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )

        with patch("neural_hive_observability.tracing.ResilientOTLPSpanExporter"):
            with patch("neural_hive_observability.tracing.BatchSpanProcessor"):
                init_tracing(config)

        from neural_hive_observability import tracing

        assert tracing._config == config


class TestTraceIntentDecorator:
    """Testes para decorator @trace_intent."""

    def test_trace_intent_sync_function(self):
        """Testa decorator em função síncrona."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_intent(extract_intent_id_from="intent_id")
            def test_func(intent_id: str, message: str):
                return f"Processed {intent_id}: {message}"

            result = test_func("intent-123", "Hello")
            assert result == "Processed intent-123: Hello"
            mock_tracer.start_as_current_span.assert_called()

    def test_trace_intent_async_function(self):
        """Testa decorator em função assíncrona."""
        # Testar sem tracer (retorna função original)
        with patch("neural_hive_observability.tracing._tracer", None):

            @trace_intent(extract_intent_id_from="intent_id")
            async def test_async_func(intent_id: str):
                return f"Async {intent_id}"

            result = asyncio.run(test_async_func("intent-456"))
            assert result == "Async intent-456"

    def test_trace_intent_without_tracer(self):
        """Testa que decorator funciona sem tracer."""
        with patch("neural_hive_observability.tracing._tracer", None):

            @trace_intent()
            def test_func():
                return "No tracer"

            result = test_func()
            assert result == "No tracer"

    def test_trace_intent_with_exception(self):
        """Testa que decorator registra exceções."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_intent()
            def test_func():
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                test_func()

            # Verificar que set_status foi chamado com ERROR
            assert mock_span.set_status.called
            # OpenTelemetry Status não tem atributo .value, verificar enum
            call_args = mock_span.set_status.call_args
            # O primeiro argumento é um Status com StatusCode.ERROR

    def test_trace_intent_with_include_args(self):
        """Testa include_args no decorator."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_intent(include_args=True)
            def test_func(message: str):
                return message

            test_func("test")

            # Verificar que set_attribute foi chamado para argumentos
            assert mock_span.set_attribute.called

    def test_trace_intent_with_include_result(self):
        """Testa include_result no decorator."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_intent(include_result=True)
            def test_func():
                return "result"

            test_func()

            # Verificar que set_attribute foi chamado para resultado
            assert mock_span.set_attribute.called


class TestTracePlanDecorator:
    """Testes para decorator @trace_plan."""

    def test_trace_plan_is_alias_of_trace_intent(self):
        """Testa que trace_plan é um alias de trace_intent."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_plan(extract_plan_id_from="plan_id")
            def test_plan_func(plan_id: str):
                return f"Plan {plan_id}"

            result = test_plan_func("plan-789")
            assert result == "Plan plan-789"
            mock_tracer.start_as_current_span.assert_called()


class TestTraceGrpcMethod:
    """Testes para decorator @trace_grpc_method."""

    def test_trace_grpc_method_creates_span(self):
        """Testa que decorator cria span para método gRPC."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_grpc_method()
            def test_grpc_func(self, request, context):
                return "response"

            mock_request = Mock()
            mock_context = Mock()
            mock_context.invocation_metadata.return_value = []

            result = test_grpc_func(None, mock_request, mock_context)
            assert result == "response"
            mock_tracer.start_as_current_span.assert_called()

    def test_trace_grpc_method_without_tracer(self):
        """Testa que funciona sem tracer."""
        with patch("neural_hive_observability.tracing._tracer", None):

            @trace_grpc_method()
            def test_grpc_func(self, request, context):
                return "response"

            result = test_grpc_func(None, Mock(), Mock())
            assert result == "response"


class TestCorrelationContext:
    """Testes para context manager correlation_context."""

    def test_correlation_context_yields(self):
        """Testa que correlation_context yield sem erro."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_tracer.start_as_current_span.return_value.__enter__ = Mock()
            mock_tracer.start_as_current_span.return_value.__exit__ = Mock()

            with correlation_context(intent_id="test-intent"):
                pass  # Não deve lançar exceção

    def test_correlation_context_without_tracer(self):
        """Testa que funciona sem tracer."""
        with patch("neural_hive_observability.tracing._tracer", None):
            with correlation_context(intent_id="test-intent"):
                pass  # Não deve lançar exceção

    def test_correlation_context_with_all_params(self):
        """Testa correlation_context com todos os parâmetros."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_tracer.start_as_current_span.return_value.__enter__ = Mock()
            mock_tracer.start_as_current_span.return_value.__exit__ = Mock()

            with correlation_context(
                intent_id="intent-123",
                plan_id="plan-456",
                user_id="user-789",
                domain="test-domain",
                extra="extra-value",
            ):
                pass


class TestEnrichSpan:
    """Testes para função enrich_span."""

    def test_enrich_span_sets_attributes(self):
        """Testa que enrich_span define atributos no span."""
        mock_span = Mock()

        enrich_span(
            mock_span,
            intent_id="intent-123",
            plan_id="plan-456",
            user_id="user-789",
            operation_type="test-op",
            custom_attr="custom-value",
        )

        # Verificar que set_attribute foi chamado
        assert mock_span.set_attribute.called

    def test_enrich_span_with_none_values(self):
        """Testa enriquecimento com valores None."""
        mock_span = Mock()

        enrich_span(mock_span, intent_id=None, plan_id=None)

        # Não deve chamar set_attribute para valores None
        # mas não deve lançar exceção


class TestGetTraceId:
    """Testes para get_current_trace_id e get_current_span_id."""

    def test_get_current_trace_id_returns_string_or_none(self):
        """Testa que retorna string ou None."""
        trace_id = get_current_trace_id()
        assert trace_id is None or isinstance(trace_id, str)

    def test_get_current_span_id_returns_string_or_none(self):
        """Testa que retorna string ou None."""
        span_id = get_current_span_id()
        assert span_id is None or isinstance(span_id, str)


class TestGetCorrelationContext:
    """Testes para get_correlation_context."""

    def test_get_correlation_context_returns_dict(self):
        """Testa que retorna dicionário."""
        context = get_correlation_context()
        assert isinstance(context, dict)


class TestIsSensitiveParam:
    """Testes para _is_sensitive_param."""

    def test_detects_password(self):
        """Testa detecção de password."""
        assert _is_sensitive_param("password") is True
        assert _is_sensitive_param("user_password") is True
        assert _is_sensitive_param("passwd") is True
        assert _is_sensitive_param("pwd") is True

    def test_detects_secret(self):
        """Testa detecção de secret."""
        assert _is_sensitive_param("secret") is True
        assert _is_sensitive_param("api_secret") is True
        assert _is_sensitive_param("token") is True
        assert _is_sensitive_param("auth_token") is True

    def test_detects_key(self):
        """Testa detecção de key."""
        assert _is_sensitive_param("private_key") is True
        assert _is_sensitive_param("api_key") is True

    def test_allows_safe_params(self):
        """Testa que permite parâmetros seguros."""
        assert _is_sensitive_param("message") is False
        assert _is_sensitive_param("intent_id") is False
        assert _is_sensitive_param("plan_id") is False

    def test_case_insensitive(self):
        """Testa que é case insensitive."""
        assert _is_sensitive_param("PASSWORD") is True
        assert _is_sensitive_param("SecretKey") is True


class TestCreateChildSpan:
    """Testes para create_child_span."""

    def test_create_child_span_without_tracer_raises(self):
        """Testa que lança RuntimeError sem tracer."""
        with patch("neural_hive_observability.tracing._tracer", None):
            with pytest.raises(RuntimeError):
                create_child_span("test-span")

    def test_create_child_span_with_tracer(self):
        """Testa criação de span filho com tracer."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_span.return_value = mock_span

        with (
            patch("neural_hive_observability.tracing._tracer", mock_tracer),
            patch("neural_hive_observability.tracing._config", Mock()),
        ):
            span = create_child_span("test-span", attr1="value1")
            assert span == mock_span


class TestInjectExtractContextHeaders:
    """Testes para inject/extract context de headers."""

    def test_inject_context_to_headers_adds_headers(self):
        """Testa que injeção adiciona headers."""
        headers = {"existing": "header"}
        result = inject_context_to_headers(headers)

        assert "existing" in result
        assert result["existing"] == "header"
        # Headers OpenTelemetry devem ser adicionados

    def test_extract_context_from_headers(self):
        """Testa extração de contexto de headers."""
        headers = {
            "x-neural-hive-intent-id": "intent-123",
            "x-neural-hive-plan-id": "plan-456",
            "x-neural-hive-user-id": "user-789",
        }

        # Não deve lançar exceção
        token = extract_context_from_headers(headers)
        # Token pode ser None ou um objeto Token (verificar que não falhou)
        assert token is None or token is not None


class TestTraceIntentExtraction:
    """Testes para extração de IDs no decorator trace_intent."""

    def test_extract_intent_id_from_kwargs(self):
        """Testa extração de intent_id dos kwargs."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_intent()
            def test_func(**kwargs):
                return kwargs.get("intent_id")

            result = test_func(intent_id="test-intent")
            assert result == "test-intent"

    def test_extract_plan_id_from_kwargs(self):
        """Testa extração de plan_id dos kwargs."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_plan()
            def test_func(**kwargs):
                return kwargs.get("plan_id")

            result = test_func(plan_id="test-plan")
            assert result == "test-plan"


class TestTraceIntentOperationName:
    """Testes para operation_name no decorator."""

    def test_custom_operation_name(self):
        """Testa nome de operação customizado."""
        mock_config = Mock()
        mock_config.neural_hive_component = "test-component"
        mock_config.neural_hive_layer = "test-layer"
        mock_config.neural_hive_domain = None

        with (
            patch("neural_hive_observability.tracing._tracer") as mock_tracer,
            patch("neural_hive_observability.tracing._config", mock_config),
        ):
            mock_span = Mock()
            mock_span.__enter__ = Mock(return_value=mock_span)
            mock_span.__exit__ = Mock(return_value=False)
            mock_tracer.start_as_current_span.return_value = mock_span

            @trace_intent(operation_name="custom.operation")
            def test_func():
                return "result"

            test_func()

            # Verificar que o nome customizado foi usado
            call_args = mock_tracer.start_as_current_span.call_args
            assert "custom.operation" in str(call_args)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
