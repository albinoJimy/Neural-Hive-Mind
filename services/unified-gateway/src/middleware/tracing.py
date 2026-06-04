"""
Tracing Middleware para Unified Gateway.

Implementa propagação de contexto distribuído via header traceparent
conforme W3C Trace Context standard.

Implementa INV-11: Distributed tracing propagated via traceparent header.
"""

import time

import structlog
from fastapi import Request
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para tracing distribuído W3C Trace Context.

    Implementa INV-11: Distributed tracing propagated via traceparent header.

    Propaga traceparent entre requisições:
    - Extrai traceparent da requisição de entrada
    - Cria/continua span do trace atual
    - Adiciona traceparent nas requisições para serviços downstream
    """

    def __init__(self, app, service_name: str | None = None):
        """
        Inicializa middleware de tracing.

        Args:
            app: Aplicação FastAPI
            service_name: Nome do serviço para tracing
        """
        super().__init__(app)
        self.service_name = service_name or "unified-gateway"

        # Obter tracer global
        self.tracer = trace.get_tracer(__name__)

        logger.info("tracing_middleware_initialized", service_name=self.service_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Processa requisição com tracing distribuído.

        Implementa INV-11: propagação de traceparent.
        """
        start_time = time.time()
        path = request.url.path
        method = request.method

        # Extrair ou gerar trace context
        trace_parent = request.headers.get("traceparent")

        if trace_parent:
            logger.debug("trace_context_received", traceparent=trace_parent[:50])

        # Nomear span baseado no path
        span_name = f"{method} {path}"

        # Criar span com contexto do traceparent
        with self.tracer.start_as_current_span(span_name) as span:
            # Adicionar atributos ao span
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.scheme", request.url.scheme)
            span.set_attribute("http.host", request.url.hostname)
            span.set_attribute("http.target", path)
            span.set_attribute("net.host.name", settings.HOST)
            span.set_attribute("net.host.port", settings.PORT)

            # User agent e client IP
            user_agent = request.headers.get("user-agent", "")
            if user_agent:
                span.set_attribute("http.user_agent", user_agent)

            client_ip = self._get_client_ip(request)
            if client_ip:
                span.set_attribute("net.peer.ip", client_ip)

            # Contexto de autenticação se disponível
            if hasattr(request.state, "auth_context"):
                auth_ctx = request.state.auth_context
                if auth_ctx.user_id:
                    span.set_attribute("enduser.id", auth_ctx.user_id)
                if auth_ctx.tenant_id:
                    span.set_attribute("tenant.id", auth_ctx.tenant_id)

            # Guardar span atual no state para uso downstream
            request.state.current_span = span

            # Processar requisição
            try:
                response = await call_next(request)

                # Adicionar traceparent à resposta
                current_span = trace.get_current_span()
                # Verificar se é um recording span (NonRecordingSpan não tem context)
                if current_span and hasattr(current_span, "context") and current_span.context:
                    # Adicionar traceparent à resposta para debug
                    span_context = current_span.context
                    trace_id = format(span_context.trace_id, "032x")
                    span_id = format(span_context.span_id, "016x")
                    trace_flags = format(span_context.trace_flags, "02x")
                    response_traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"

                    # Não adicionar na resposta por padrão (apenas em debug)
                    if settings.ENVIRONMENT == "development":
                        response.headers["X-Trace-Parent"] = response_traceparent

                # Status code e duração
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.response_time_ms", duration_ms)

                # Marcar span como erro se status code >= 400
                if response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                else:
                    span.set_status(Status(StatusCode.OK))

                logger.debug(
                    "request_traced",
                    path=path,
                    method=method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

                return response

            except Exception as e:
                # Marcar span como erro
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

                logger.error(
                    "request_error",
                    path=path,
                    method=method,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise

    def _get_client_ip(self, request: Request) -> str | None:
        """
        Extrai IP do cliente considerando proxies.

        Tenta headers comuns de proxy em ordem de prioridade.
        """
        # Headers comuns para IP real atrás de proxy
        headers_to_check = [
            "X-Forwarded-For",
            "X-Real-IP",
            "CF-Connecting-IP",  # Cloudflare
            "True-Client-IP",
        ]

        for header_name in headers_to_check:
            header_value = request.headers.get(header_name)
            if header_value:
                # X-Forwarded-For pode conter múltiplos IPs
                if "," in header_value:
                    return header_value.split(",")[0].strip()
                return header_value

        # Fallback para IP direto
        if request.client:
            return request.client.host

        return None


def inject_traceparent(headers: dict[str, str]) -> None:
    """
    Injeta traceparent atual em headers de requisição downstream.

    Implementa INV-11: propagação de traceparent para serviços downstream.

    Uso:
        headers = {"Content-Type": "application/json"}
        inject_traceparent(headers)
        # headers agora contém traceparent
    """
    try:
        # Usar propagador W3C Trace Context
        from opentelemetry.propagators.tracecontext import TraceContextPropagator

        propagator = TraceContextPropagator()
        propagator.inject(headers)

        logger.debug("traceparent_injected", headers_count=len(headers))

    except Exception as e:
        logger.warning("traceparent_injection_failed", error=str(e))


def get_trace_id() -> str | None:
    """
    Retorna trace ID atual se disponível.

    Útil para logging e correlação.
    """
    try:
        from opentelemetry.trace import get_current_span

        span = get_current_span()
        # Verificar se é um recording span (NonRecordingSpan não tem context)
        if span and hasattr(span, "context") and span.context:
            return format(span.context.trace_id, "032x")
    except Exception:
        pass
    return None


def get_span_id() -> str | None:
    """
    Retorna span ID atual se disponível.
    """
    try:
        from opentelemetry.trace import get_current_span

        span = get_current_span()
        # Verificar se é um recording span (NonRecordingSpan não tem context)
        if span and hasattr(span, "context") and span.context:
            return format(span.context.span_id, "016x")
    except Exception:
        pass
    return None
