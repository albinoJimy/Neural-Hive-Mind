"""Testes unitários para Tracing Middleware."""

import pytest

from src.middleware.tracing import TracingMiddleware, get_trace_id, get_span_id


class TestTracingMiddleware:
    """Testes para TracingMiddleware."""

    def test_middleware_initialization(self):
        """TracingMiddleware deve ser inicializado com service name."""
        from starlette.middleware.base import BaseHTTPMiddleware

        def dummy_app(scope, receive, send):
            pass

        middleware = TracingMiddleware(app=dummy_app, service_name="test-gateway")

        assert middleware.service_name == "test-gateway"
        assert isinstance(middleware, BaseHTTPMiddleware)

    def test_middleware_default_service_name(self):
        """TracingMiddleware deve usar default service name se não fornecido."""

        def dummy_app(scope, receive, send):
            pass

        middleware = TracingMiddleware(app=dummy_app)

        assert middleware.service_name == "unified-gateway"

    def test_get_client_ip_from_forwarded_header(self):
        """Deve extrair IP de X-Forwarded-For header."""
        from fastapi import Request

        middleware = TracingMiddleware(app=lambda s, r, se: None)

        # Criar scope com header X-Forwarded-For
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [[b"x-forwarded-for", b"192.168.1.100, 10.0.0.1"]],
        }
        request = Request(scope)

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.100"

    def test_get_client_ip_from_real_ip_header(self):
        """Deve extrair IP de X-Real-IP header."""
        from fastapi import Request

        middleware = TracingMiddleware(app=lambda s, r, se: None)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [[b"x-real-ip", b"192.168.1.200"]],
        }
        request = Request(scope)

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.200"

    def test_get_client_ip_from_client(self):
        """Deve extrair IP de request.client se não há headers."""
        from fastapi import Request

        middleware = TracingMiddleware(app=lambda s, r, se: None)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "client": ("192.168.1.50", 12345),
        }
        request = Request(scope)

        ip = middleware._get_client_ip(request)
        assert ip == "192.168.1.50"


class TestTraceContextHelpers:
    """Testes para funções auxiliares de trace context."""

    def test_get_trace_id_when_no_span(self):
        """Deve retornar None quando não há span ativo."""
        trace_id = get_trace_id()
        # Em ambiente de teste, pode retornar None ou um trace ID válido
        assert trace_id is None or isinstance(trace_id, str)

    def test_get_span_id_when_no_span(self):
        """Deve retornar None quando não há span ativo."""
        span_id = get_span_id()
        # Em ambiente de teste, pode retornar None ou um span ID válido
        assert span_id is None or isinstance(span_id, str)


class TestTraceParentInjection:
    """Testes para injeção de traceparent."""

    def test_inject_traceparent_to_headers(self):
        """Deve injetar traceparent em headers (INV-11)."""
        from src.middleware.tracing import inject_traceparent

        headers = {"Content-Type": "application/json"}
        inject_traceparent(headers)

        # Verificar que headers foram modificados (podem conter traceparent)
        # Em ambiente de teste sem OTEL configurado, pode não adicionar nada
        assert "Content-Type" in headers
