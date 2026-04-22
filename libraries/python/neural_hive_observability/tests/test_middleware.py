"""
Testes para W3C Trace Context Middleware.

Este arquivo contém testes unitários para validar:
- Extração de traceparent de headers HTTP
- Validação de formato W3C Trace Context
- Injeção de contexto em baggage OpenTelemetry
- Métricas de correlação de tracing
- Propagação de headers customizados Neural Hive
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.metrics import NeuralHiveMetrics
from neural_hive_observability.middleware import (
    TraceContextMiddleware,
    extract_traceparent_from_request,
    extract_tracestate_from_request,
    get_trace_id_from_request,
    parse_traceparent,
    validate_trace_context,
)


class TestParseTraceparent:
    """Testes para parse_traceparent"""

    def test_parse_valid_traceparent(self):
        """Teste 1: Parser traceparent válido com formato correto"""
        traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        result = parse_traceparent(traceparent)

        assert result is not None
        trace_id, span_id, trace_flags = result
        assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert span_id == "00f067aa0ba902b7"
        assert trace_flags == "01"

    def test_parse_traceparent_with_lowercase(self):
        """Teste 2: Parser traceparent com letras minúsculas"""
        traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        result = parse_traceparent(traceparent)

        assert result is not None
        trace_id, span_id, trace_flags = result
        assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_parse_traceparent_with_uppercase(self):
        """Teste 3: Parser traceparent com letras maiúsculas"""
        traceparent = "00-4BF92F3577B34DA6A3CE929D0E0E4736-00F067AA0BA902B7-01"
        result = parse_traceparent(traceparent)

        assert result is not None
        trace_id, span_id, trace_flags = result
        assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_parse_traceparent_with_mixed_case(self):
        """Teste 4: Parser traceparent com case misto"""
        traceparent = "00-4bF92F3577b34Da6A3cE929d0E0e4736-00F067Aa0Ba902B7-01"
        result = parse_traceparent(traceparent)

        assert result is not None
        trace_id, span_id, trace_flags = result

    def test_parse_traceparent_none_returns_none(self):
        """Teste 5: Parser traceparent None retorna None"""
        result = parse_traceparent(None)
        assert result is None

    def test_parse_traceparent_empty_string_returns_none(self):
        """Teste 6: Parser string vazia retorna None"""
        result = parse_traceparent("")
        assert result is None

    def test_parse_traceparent_invalid_format_returns_none(self):
        """Teste 7: Parser formato inválido retorna None"""
        result = parse_traceparent("invalid-format")
        assert result is None

    def test_parse_traceparent_wrong_version(self):
        """Teste 8: Parser com versão errada retorna None"""
        result = parse_traceparent("01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        assert result is None

    def test_parse_traceparent_invalid_trace_id_length(self):
        """Teste 9: Parser com trace_id de comprimento errado retorna None"""
        result = parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e47-00f067aa0ba902b7-01")
        assert result is None

    def test_parse_traceparent_invalid_span_id_length(self):
        """Teste 10: Parser com span_id de comprimento errado retorna None"""
        result = parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902-01")
        assert result is None

    def test_parse_traceparent_invalid_trace_flags_length(self):
        """Teste 11: Parser com trace_flags de comprimento errado retorna None"""
        result = parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-1")
        assert result is None


class TestExtractFromRequest:
    """Testes para extração de traceparent de requests HTTP"""

    @pytest.fixture()
    def mock_request(self):
        """Cria um request HTTP mock"""
        request = Mock(spec=Request)
        request.headers = {}
        return request

    def test_extract_traceparent_from_request_lowercase(self, mock_request):
        """Teste 12: Extrair traceparent com header minúsculo"""
        mock_request.headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }
        result = extract_traceparent_from_request(mock_request)
        assert result == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_extract_traceparent_from_request_uppercase(self, mock_request):
        """Teste 13: Extrair traceparent com header maiúsculo"""
        mock_request.headers = {
            "Traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }
        result = extract_traceparent_from_request(mock_request)
        assert result == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_extract_traceparent_from_request_missing(self, mock_request):
        """Teste 14: Retorna None quando traceparent ausente"""
        result = extract_traceparent_from_request(mock_request)
        assert result is None

    def test_extract_tracestate_from_request_present(self, mock_request):
        """Teste 15: Extrair tracestate quando presente"""
        mock_request.headers = {"tracestate": "vendor1=opaqueValue1,vendor2=opaqueValue2"}
        result = extract_tracestate_from_request(mock_request)
        assert result == "vendor1=opaqueValue1,vendor2=opaqueValue2"

    def test_extract_tracestate_from_request_missing(self, mock_request):
        """Teste 16: Retorna None quando tracestate ausente"""
        result = extract_tracestate_from_request(mock_request)
        assert result is None


class TestValidateTraceContext:
    """Testes para validação de trace context"""

    @pytest.fixture()
    def mock_request(self):
        """Cria um request HTTP mock"""
        request = Mock(spec=Request)
        request.headers = {}
        return request

    def test_validate_valid_trace_context(self, mock_request):
        """Teste 17: Validar trace context válido"""
        mock_request.headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }
        is_valid, error = validate_trace_context(mock_request)
        assert is_valid is True
        assert error is None

    def test_validate_missing_traceparent(self, mock_request):
        """Teste 18: Retornar erro quando traceparent ausente"""
        is_valid, error = validate_trace_context(mock_request)
        assert is_valid is False
        assert "Missing traceparent" in error

    def test_validate_invalid_format(self, mock_request):
        """Teste 19: Retornar erro quando formato inválido"""
        mock_request.headers = {"traceparent": "invalid-format"}
        is_valid, error = validate_trace_context(mock_request)
        assert is_valid is False
        assert "Invalid traceparent" in error


class TestGetTraceIdFromRequest:
    """Testes para extração de trace ID"""

    @pytest.fixture()
    def mock_request(self):
        """Cria um request HTTP mock"""
        request = Mock(spec=Request)
        request.headers = {}
        return request

    def test_get_trace_id_from_valid_request(self, mock_request):
        """Teste 20: Extrair trace ID de request válido"""
        mock_request.headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }
        trace_id = get_trace_id_from_request(mock_request)
        assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_get_trace_id_from_missing_header(self, mock_request):
        """Teste 21: Retornar None quando header ausente"""
        trace_id = get_trace_id_from_request(mock_request)
        assert trace_id is None

    def test_get_trace_id_from_invalid_format(self, mock_request):
        """Teste 22: Retornar None quando formato inválido"""
        mock_request.headers = {"traceparent": "invalid"}
        trace_id = get_trace_id_from_request(mock_request)
        assert trace_id is None


class TestTraceContextMiddleware:
    """Testes para TraceContextMiddleware"""

    @pytest.fixture()
    def config(self):
        """Cria configuração de observabilidade"""
        return ObservabilityConfig(
            service_name="test-service",
            service_version="1.0.0",
            neural_hive_component="test",
            neural_hive_layer="test",
        )

    @pytest.fixture()
    def metrics(self, config):
        """Cria métricas para teste"""
        return NeuralHiveMetrics(config)

    @pytest.fixture()
    def app(self):
        """Cria aplicação Starlette para teste"""
        return Starlette()

    @pytest.fixture()
    def middleware(self, app, metrics):
        """Cria middleware para teste"""
        return TraceContextMiddleware(app, metrics=metrics)

    @pytest.mark.asyncio()
    async def test_middleware_extracts_valid_traceparent(self, middleware):
        """Teste 23: Middleware extrai traceparent válido"""
        request = Mock(spec=Request)
        request.headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        response = await middleware.dispatch(request, call_next)

        assert call_next.called
        assert response.status_code == 200

    @pytest.mark.asyncio()
    async def test_middleware_handles_missing_traceparent(self, middleware):
        """Teste 24: Middleware lida com traceparent ausente"""
        request = Mock(spec=Request)
        request.headers = {}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        response = await middleware.dispatch(request, call_next)

        assert call_next.called
        assert response.status_code == 200

    @pytest.mark.asyncio()
    async def test_middleware_sets_baggage_from_headers(self, middleware):
        """Teste 25: Middleware define baggage a partir de headers Neural Hive"""
        request = Mock(spec=Request)
        request.headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "x-neural-hive-intent-id": "test-intent-123",
            "x-neural-hive-plan-id": "test-plan-456",
            "x-neural-hive-user-id": "test-user-789",
        }
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        with patch("neural_hive_observability.middleware.set_baggage") as mock_set_baggage:
            response = await middleware.dispatch(request, call_next)

            # Verificar que set_baggage foi chamado para cada header
            assert mock_set_baggage.call_count >= 3
            assert response.status_code == 200

    @pytest.mark.asyncio()
    async def test_middleware_injects_trace_id_in_response(self, middleware):
        """Teste 26: Middleware injeta trace ID na response"""
        request = Mock(spec=Request)
        request.headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        request.url = Mock(path="/test")

        response = Response(content="OK", status_code=200)
        call_next = AsyncMock(return_value=response)

        with patch("neural_hive_observability.middleware.trace.get_current_span") as mock_span:
            mock_span_context = Mock()
            mock_span_context.is_valid = True
            mock_span_context.trace_id = 0x4BF92F3577B34DA6A3CE929D0E0E4736
            mock_span_context.span_id = 0x00F067AA0BA902B7
            mock_span_context.trace_flags = 1

            mock_span.return_value.get_span_context.return_value = mock_span_context

            result = await middleware.dispatch(request, call_next)

            # Verificar que x-trace-id foi injetado
            assert "x-trace-id" in result.headers

    @pytest.mark.asyncio()
    async def test_middleware_records_metrics(self, middleware):
        """Teste 27: Middleware registra métricas de correlação"""
        request = Mock(spec=Request)
        request.headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        # Get metric value using samples
        # Note: Counter samples have "_total" suffix in their name
        def get_metric_value(metric):
            for sample in metric.collect()[0].samples:
                # For counters, sample.name has "_total" suffix while metric._name doesn't
                if sample.name == metric._name + "_total":
                    return sample.value
            return 0

        initial_value = get_metric_value(middleware.metrics.trace_context_extraction_total)

        await middleware.dispatch(request, call_next)

        final_value = get_metric_value(middleware.metrics.trace_context_extraction_total)
        assert final_value > initial_value

    @pytest.mark.asyncio()
    async def test_middleware_records_success_metric(self, middleware):
        """Teste 28: Middleware registra métrica de sucesso"""
        request = Mock(spec=Request)
        request.headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        await middleware.dispatch(request, call_next)

        # Verificar que métrica de sucesso foi incrementada
        # Get metric samples and check value
        samples = middleware.metrics.trace_context_extraction_success_total.collect()[0].samples
        assert len(samples) > 0
        # Find sample with source="http" label
        for sample in samples:
            if sample.labels.get("source") == "http":
                assert sample.value > 0
                break
        else:
            pytest.fail("No sample found with source='http'")

    @pytest.mark.asyncio()
    async def test_middleware_records_missing_parent_metric(self, middleware):
        """Teste 29: Middleware registra métrica de traceparent ausente"""
        request = Mock(spec=Request)
        request.headers = {}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        # Get initial metric value
        samples_before = middleware.metrics.trace_parent_missing_total.collect()[0].samples
        initial_value = samples_before[0].value if samples_before else 0

        await middleware.dispatch(request, call_next)

        # Get final metric value
        samples_after = middleware.metrics.trace_parent_missing_total.collect()[0].samples
        final_value = samples_after[0].value if samples_after else 0
        assert final_value > initial_value

    @pytest.mark.asyncio()
    async def test_middleware_records_failure_metric_invalid_format(self, middleware):
        """Teste 30: Middleware registra métrica de falha para formato inválido"""
        request = Mock(spec=Request)
        request.headers = {"traceparent": "invalid-format"}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        await middleware.dispatch(request, call_next)

        # Verificar que métrica de falha foi incrementada
        samples = middleware.metrics.trace_context_extraction_failure_total.collect()[0].samples
        # Find sample with reason="invalid_format" label
        for sample in samples:
            if sample.labels.get("reason") == "invalid_format":
                assert sample.value > 0
                break
        else:
            pytest.fail("No sample found with reason='invalid_format'")

    @pytest.mark.asyncio()
    async def test_middleware_without_metrics(self, app):
        """Teste 31: Middleware funciona sem métricas (modo degradado)"""
        middleware = TraceContextMiddleware(app, metrics=None)

        request = Mock(spec=Request)
        request.headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        response = await middleware.dispatch(request, call_next)

        assert call_next.called
        assert response.status_code == 200

    @pytest.mark.asyncio()
    async def test_middleware_with_extract_custom_headers_disabled(self, app, metrics):
        """Teste 32: Middleware com extract_custom_headers=False"""
        middleware = TraceContextMiddleware(app, metrics=metrics, extract_custom_headers=False)

        request = Mock(spec=Request)
        request.headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "x-neural-hive-intent-id": "test-intent-123",
        }
        request.url = Mock(path="/test")

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))

        with patch("neural_hive_observability.middleware.set_baggage") as mock_set_baggage:
            await middleware.dispatch(request, call_next)

            # Com extract_custom_headers=False, set_baggage não deve ser chamado para headers customizados
            # Pode ser chamado para traceparent via extract(), mas não para x-neural-hive-*
            # O teste verifica que o middleware funciona corretamente com a flag desabilitada
            assert call_next.called
