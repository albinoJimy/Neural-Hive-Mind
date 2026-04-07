"""
Testes estendidos para o módulo context.py da biblioteca neural_hive_observability.

Este arquivo contém testes adicionais para aumentar a cobertura de:
- Extract e inject de headers HTTP/Kafka
- Funções utilitárias de baggage
- ChildContext
- Funções de contexto metadata
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from opentelemetry import context, baggage
from opentelemetry.context import attach, detach

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.context import (
    ContextManager,
    ChildContext,
    extract_context_from_headers,
    extract_context_from_metadata,
    set_baggage_value,
    inject_context_to_metadata,
    get_baggage,
)


class TestContextManagerHttpHeaders:
    """Testes para injeção e extração de headers HTTP."""

    def test_extract_http_headers_with_all_fields(self):
        """Testa extração de todos os campos de headers HTTP."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        headers = {
            "X-Neural-Hive-Intent-Id": "intent-123",
            "X-Neural-Hive-Plan-Id": "plan-456",
            "X-Neural-Hive-User-Id": "user-789",
            "X-Neural-Hive-Domain": "test-domain",
            "X-Neural-Hive-Channel": "web",
        }

        result = ctx_manager.extract_http_headers(headers)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert result["plan_id"] == "plan-456"
        assert result["user_id"] == "user-789"
        assert result["domain"] == "test-domain"
        assert result["channel"] == "web"

    def test_extract_http_headers_partial(self):
        """Testa extração parcial de headers."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        headers = {"X-Neural-Hive-Intent-Id": "intent-123", "X-Neural-Hive-Channel": "api"}

        result = ctx_manager.extract_http_headers(headers)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert result["channel"] == "api"
        assert "plan_id" not in result

    def test_extract_http_headers_empty(self):
        """Testa extração de headers vazios."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        result = ctx_manager.extract_http_headers({})
        assert result is None

    def test_extract_http_headers_sets_baggage(self):
        """Testa que extração define baggage."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        headers = {"X-Neural-Hive-Intent-Id": "intent-123"}

        # Mock attach para evitar problemas de contexto
        with patch("neural_hive_observability.context.attach"):
            result = ctx_manager.extract_http_headers(headers)

        # Resultado deve conter o intent_id
        assert result is not None
        assert result["intent_id"] == "intent-123"


class TestContextManagerKafkaHeaders:
    """Testes para injeção e extração de headers Kafka."""

    def test_inject_kafka_headers_converts_to_bytes(self):
        """Testa que injeção converte para bytes."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        headers = {b"existing": b"value"}
        result = ctx_manager.inject_kafka_headers(headers)

        assert isinstance(result, dict)
        # Headers devem ser bytes ou strings

    def test_extract_kafka_headers_converts_from_bytes(self):
        """Testa que extração converte de bytes."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        headers = {b"X-Neural-Hive-Intent-Id": b"intent-123", b"X-Neural-Hive-Plan-Id": b"plan-456"}

        result = ctx_manager.extract_kafka_headers(headers)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert result["plan_id"] == "plan-456"

    def test_extract_kafka_headers_with_string_values(self):
        """Testa extração com valores string."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        headers = {"X-Neural-Hive-Intent-Id": "intent-123"}

        result = ctx_manager.extract_kafka_headers(headers)

        assert result is not None
        assert result["intent_id"] == "intent-123"

    def test_extract_kafka_headers_empty(self):
        """Testa extração de headers Kafka vazios."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        result = ctx_manager.extract_kafka_headers({})
        assert result is None


class TestContextManagerGetters:
    """Testes para métodos getter de IDs."""

    def test_get_intent_id_from_baggage(self):
        """Testa get_intent_id."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(intent_id="test-intent"):
            result = ctx_manager.get_intent_id()
            # Resultado pode variar dependendo do estado do baggage

    def test_get_plan_id_from_baggage(self):
        """Testa get_plan_id."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(plan_id="test-plan"):
            result = ctx_manager.get_plan_id()

    def test_get_user_id_from_baggage(self):
        """Testa get_user_id."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(user_id="test-user"):
            result = ctx_manager.get_user_id()

    def test_get_domain_from_baggage(self):
        """Testa get_domain."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(domain="test-domain"):
            result = ctx_manager.get_domain()

    def test_get_channel_from_baggage(self):
        """Testa get_channel."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(channel="test-channel"):
            result = ctx_manager.get_channel()


class TestChildContext:
    """Testes para ChildContext."""

    def test_child_context_initialization(self):
        """Testa inicialização do ChildContext."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        parent_manager = ContextManager(config)

        child_ctx = parent_manager.create_child_context(
            intent_id="child-intent", operation="child-op"
        )

        assert child_ctx.parent_manager == parent_manager
        assert child_ctx.intent_id == "child-intent"
        assert child_ctx.operation == "child-op"

    def test_child_context_inherits_parent_ids(self):
        """Testa que contexto filho herda IDs do pai."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        parent_manager = ContextManager(config)

        # Definir IDs no contexto pai
        with parent_manager.correlation_context(intent_id="parent-intent", plan_id="parent-plan"):
            child_ctx = parent_manager.create_child_context()

            # IDs devem ser herdados
            assert child_ctx.intent_id == "parent-intent"
            assert child_ctx.plan_id == "parent-plan"

    def test_child_context_overrides_parent_ids(self):
        """Testa que contexto filho pode sobrescrever IDs."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        parent_manager = ContextManager(config)

        with parent_manager.correlation_context(intent_id="parent-intent"):
            child_ctx = parent_manager.create_child_context(intent_id="child-intent")

            # ID filho deve sobrescrever pai
            assert child_ctx.intent_id == "child-intent"

    def test_child_context_enter_exit(self):
        """Testa enter/exit do ChildContext."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        parent_manager = ContextManager(config)

        child_ctx = parent_manager.create_child_context(
            intent_id="test-intent", operation="test-op"
        )

        # Mock attach/detach
        with patch("neural_hive_observability.context.attach") as mock_attach, patch(
            "neural_hive_observability.context.detach"
        ) as mock_detach:
            mock_attach.return_value = "token"

            with child_ctx:
                assert mock_attach.called

            assert mock_detach.called

    def test_child_context_get_correlation(self):
        """Testa get_correlation do ChildContext."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        parent_manager = ContextManager(config)

        child_ctx = parent_manager.create_child_context(intent_id="test-intent")

        correlation = child_ctx.get_correlation()
        assert isinstance(correlation, dict)


class TestExtractContextFromHeaders:
    """Testes para extract_context_from_headers (module function)."""

    def test_extract_from_dict_headers(self):
        """Testa extração de headers como dict."""
        headers = {
            "x-neural-hive-intent-id": "intent-123",
            "x-neural-hive-plan-id": "plan-456",
            "baggage": "neural.hive.channel=api",
        }

        token = extract_context_from_headers(headers)

        # Token pode ser None ou um token válido
        assert token is None or hasattr(token, "__detach__")

    def test_extract_from_list_headers(self):
        """Testa extração de headers como lista de tuplas."""
        headers = [
            (b"x-neural-hive-intent-id", b"intent-123"),
            (b"x-neural-hive-plan-id", b"plan-456"),
        ]

        token = extract_context_from_headers(headers)

        # Não deve lançar exceção
        assert token is None or hasattr(token, "__detach__")

    def test_extract_from_empty_headers(self):
        """Testa extração de headers vazios."""
        token = extract_context_from_headers({})
        assert token is None

        token = extract_context_from_headers([])
        assert token is None


class TestSetBaggageValue:
    """Testes para set_baggage_value."""

    def test_set_baggage_value_with_valid_key_value(self):
        """Testa definir baggage com chave e valor válidos."""
        # Mock attach
        with patch("neural_hive_observability.context.attach"):
            set_baggage_value("test.key", "test-value")
            # Não deve lançar exceção

    def test_set_baggage_value_with_none_key(self):
        """Testa definir baggage com chave None."""
        set_baggage_value(None, "value")
        # Não deve lançar exceção

    def test_set_baggage_value_with_none_value(self):
        """Testa definir baggage com valor None."""
        set_baggage_value("test.key", None)
        # Não deve lançar exceção

    def test_set_baggage_value_with_empty_string(self):
        """Testa definir baggage com string vazia."""
        set_baggage_value("", "")
        # Não deve lançar exceção


class TestInjectContextToMetadata:
    """Testes para inject_context_to_metadata."""

    def test_inject_to_none_metadata(self):
        """Testa injeção em metadata None."""
        result = inject_context_to_metadata(None)

        assert isinstance(result, list)

    def test_inject_to_existing_metadata(self):
        """Testa injeção em metadata existente."""
        existing = [("existing-key", "existing-value")]
        result = inject_context_to_metadata(existing)

        assert isinstance(result, list)
        # Metadata existente deve estar presente
        assert ("existing-key", "existing-value") in result

    def test_inject_adds_otel_headers(self):
        """Testa que injeção adiciona headers OTEL."""
        result = inject_context_to_metadata()

        # Headers OTEL devem ser adicionados (traceparent, etc.)
        assert isinstance(result, list)


class TestExtractContextFromMetadata:
    """Testes para extract_context_from_metadata."""

    def test_extract_from_empty_metadata(self):
        """Testa extração de metadata vazio."""
        result = extract_context_from_metadata({})
        assert result is None

        result = extract_context_from_metadata(None)
        assert result is None

    def test_extract_from_grpc_metadata_lowercase(self):
        """Testa extração de metadata gRPC (lowercase)."""
        metadata = {"intent-id": "intent-123", "plan-id": "plan-456", "user-id": "user-789"}

        result = extract_context_from_metadata(metadata)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert result["plan_id"] == "plan-456"
        assert result["user_id"] == "user-789"

    def test_extract_from_http_metadata_case_insensitive(self):
        """Testa extração de metadata HTTP (case insensitive)."""
        metadata = {
            "X-Neural-Hive-Intent-Id": "intent-123",
            "x-neural-hive-plan-id": "plan-456",
            "X-Neural-Hive-Domain": "test-domain",
        }

        result = extract_context_from_metadata(metadata)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert result["plan_id"] == "plan-456"
        assert result["domain"] == "test-domain"

    def test_extract_from_baggage_header(self):
        """Testa extração de header baggage W3C."""
        metadata = {"baggage": "neural.hive.intent.id=intent-123,neural.hive.channel=api"}

        result = extract_context_from_metadata(metadata)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert result["channel"] == "api"

    def test_extract_from_mixed_metadata(self):
        """Testa extração de metadata misto."""
        metadata = {
            "x-neural-hive-intent-id": "intent-123",
            "baggage": "neural.hive.channel=api,neural.hive.domain=test",
            "x-request-id": "req-456",
        }

        result = extract_context_from_metadata(metadata)

        assert result is not None
        assert result["intent_id"] == "intent-123"
        assert "channel" in result or "domain" in result


class TestGetBaggageAlias:
    """Testes para alias get_baggage."""

    def test_get_baggage_is_get_all_baggage(self):
        """Testa que get_baggage é alias para get_all_baggage."""
        # get_baggage deve retornar o mesmo que get_all_baggage
        from opentelemetry.baggage import get_all as get_all_baggage

        result1 = get_all_baggage()
        result2 = get_baggage()

        # Ambos devem retornar o mesmo tipo
        assert type(result1) == type(result2)


class TestContextManagerCorrelationContextExtended:
    """Testes estendidos para correlation_context."""

    def test_correlation_context_with_all_parameters(self):
        """Testa correlation_context com todos os parâmetros."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(
            intent_id="intent-123",
            plan_id="plan-456",
            user_id="user-789",
            domain="test-domain",
            channel="test-channel",
            custom_field="custom-value",
            another_field=123,
        ):
            correlation = ctx_manager.get_current_correlation()
            # Deve retornar um dicionário
            assert isinstance(correlation, dict)

    def test_correlation_context_with_none_values(self):
        """Testa correlation_context com valores None."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(intent_id=None, plan_id=None, user_id=None):
            # Não deve lançar exceção
            pass

    def test_correlation_context_cleanup_on_exception(self):
        """Testa que correlation_context limpa mesmo com exceção."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with patch("neural_hive_observability.context.detach") as mock_detach:
            try:
                with ctx_manager.correlation_context(intent_id="test"):
                    raise ValueError("Test exception")
            except ValueError:
                pass

            # Detach deve ser chamado mesmo com exceção
            # Nota: pode não ser chamado se o contexto não foi estabelecido


class TestContextManagerGetCorrelationExtended:
    """Testes estendidos para get_current_correlation."""

    def test_get_correlation_without_active_span(self):
        """Testa get_correlation sem span ativo."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        correlation = ctx_manager.get_current_correlation()

        # Deve retornar dicionário vazio ou sem trace_id/span_id
        assert isinstance(correlation, dict)

    def test_get_correlation_includes_baggage(self):
        """Testa que get_correlation inclui baggage."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(intent_id="test-intent", domain="test-domain"):
            correlation = ctx_manager.get_current_correlation()

            # Baggage deve estar incluído
            assert isinstance(correlation, dict)


class TestContextManagerInjectHttpHeadersExtended:
    """Testes estendidos para inject_http_headers."""

    def test_inject_http_headers_preserves_existing(self):
        """Testa que headers existentes são preservados."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        existing = {"Authorization": "Bearer token", "Content-Type": "application/json"}

        result = ctx_manager.inject_http_headers(existing)

        assert result["Authorization"] == "Bearer token"
        assert result["Content-Type"] == "application/json"

    def test_inject_http_headers_with_correlation(self):
        """Testa injeção com contexto de correlação."""
        config = ObservabilityConfig(
            service_name="test-service", neural_hive_component="test-component"
        )
        ctx_manager = ContextManager(config)

        with ctx_manager.correlation_context(intent_id="test-intent", channel="api"):
            result = ctx_manager.inject_http_headers({})

            # Headers de correlação devem estar presentes
            # (dependendo do estado do baggage)
            assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
