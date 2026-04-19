"""
W3C Trace Context Middleware para FastAPI.

Implementa middleware para propagação de contexto de tracing distribuído
seguindo o padrão W3C Trace Context (traceparent e tracestate).

W3C Trace Context specification:
- traceparent: version-trace_id-span_id-trace_flags
- tracestate: vendor-specific key-value pairs

Exemplo de uso:
```python
from fastapi import FastAPI
from neural_hive_observability.middleware import TraceContextMiddleware

app = FastAPI()
app.add_middleware(TraceContextMiddleware)
```
"""

import logging
import re
from typing import Callable, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from opentelemetry import trace, context
from opentelemetry.propagate import extract
from opentelemetry.context import attach
from opentelemetry.baggage import set_baggage

from .metrics import NeuralHiveMetrics

logger = logging.getLogger(__name__)

# Regex para validar formato W3C traceparent
# version (2 hex digits) - trace_id (32 hex digits) - span_id (16 hex digits) - trace_flags (2 hex digits)
TRACEPARENT_PATTERN = re.compile(
    r'^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$',
    re.IGNORECASE
)


def parse_traceparent(traceparent: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse W3C traceparent header.

    Args:
        traceparent: Valor do header traceparent

    Returns:
        Tuple de (trace_id, span_id, trace_flags) ou None se inválido
    """
    if not traceparent:
        return None

    match = TRACEPARENT_PATTERN.match(traceparent.strip())
    if not match:
        logger.warning(f"Invalid traceparent format: {traceparent}")
        return None

    trace_id, span_id, trace_flags = match.groups()
    # W3C spec requires lowercase hex digits
    return trace_id.lower(), span_id.lower(), trace_flags.lower()


def extract_traceparent_from_request(request: Request) -> Optional[str]:
    """
    Extrai traceparent do request HTTP.

    Args:
        request: Request FastAPI

    Returns:
        Valor do header traceparent ou None
    """
    # Tria diferentes variações de case (HTTP headers são case-insensitive)
    traceparent = request.headers.get("traceparent")
    if not traceparent:
        traceparent = request.headers.get("Traceparent")
    return traceparent


def extract_tracestate_from_request(request: Request) -> Optional[str]:
    """
    Extrai tracestate do request HTTP.

    Args:
        request: Request FastAPI

    Returns:
        Valor do header tracestate ou None
    """
    tracestate = request.headers.get("tracestate")
    if not tracestate:
        tracestate = request.headers.get("Tracestate")
    return tracestate


class TraceContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI para propagação W3C Trace Context.

    Extrai traceparent/tracestate de requests HTTP entrantes e injeta
    no contexto OpenTelemetry para correlação distribuída.

    Features:
    - Extração de W3C traceparent header
    - Extração de Neural Hive custom headers (x-neural-hive-*)
    - Injeção automática em baggage OpenTelemetry
    - Métricas de correlação (sucesso/falha)
    - Suporte a tracestate para vendor-specific data

    Métricas registradas:
    - trace_context_extraction_total: Total de extrações
    - trace_context_extraction_success_total: Extrações bem-sucedidas
    - trace_context_extraction_failure_total: Extrações falhadas
    - trace_parent_missing_total: Requests sem traceparent
    """

    def __init__(
        self,
        app: ASGIApp,
        metrics: Optional[NeuralHiveMetrics] = None,
        extract_custom_headers: bool = True,
    ):
        """
        Inicializa middleware de trace context.

        Args:
            app: Aplicação ASGI
            metrics: Instância de métricas (opcional)
            extract_custom_headers: Extrair headers customizados Neural Hive
        """
        super().__init__(app)
        self.metrics = metrics
        self.extract_custom_headers = extract_custom_headers

        # Store default labels for metrics (from config if available)
        self._metric_labels = {}
        if metrics and hasattr(metrics, 'config') and hasattr(metrics.config, 'common_labels'):
            self._metric_labels = metrics.config.common_labels

        logger.info("TraceContextMiddleware initialized")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Processa request com extração de trace context.

        Args:
            request: Request HTTP
            call_next: Próximo middleware/rota

        Returns:
            Response com headers de tracing injetados
        """
        # Extrair traceparent do request
        traceparent = extract_traceparent_from_request(request)
        tracestate = extract_tracestate_from_request(request)

        # Métrica: total de extrações
        if self.metrics:
            try:
                self.metrics.trace_context_extraction_total.labels(**self._metric_labels).inc()
            except (ValueError, KeyError):
                # Fallback if metrics require labels not set
                pass

        # Token para contexto anexado
        context_token = None
        trace_valid = False

        if traceparent:
            # Validar formato do traceparent
            parsed = parse_traceparent(traceparent)
            if parsed:
                trace_id, span_id, trace_flags = parsed
                trace_valid = True

                logger.debug(
                    f"Valid traceparent extracted: trace_id={trace_id}, span_id={span_id}, path={request.url.path}"
                )

                # Extrair contexto OTEL dos headers HTTP
                headers_dict = dict(request.headers)
                try:
                    ctx = extract(headers_dict)
                    context_token = attach(ctx)

                    # Métrica: extração bem-sucedida
                    if self.metrics:
                        self.metrics.trace_context_extraction_success_total.labels(
                            **self._metric_labels,
                            source="http"
                        ).inc()

                except Exception as e:
                    logger.warning(f"Failed to extract OTEL context: {e}")
                    if self.metrics:
                        self.metrics.trace_context_extraction_failure_total.labels(
                            **self._metric_labels,
                            reason="otel_extract_error"
                        ).inc()

                # Definir baggage items
                self._set_baggage_from_headers(request)
            else:
                logger.warning(
                    f"Invalid traceparent format: {traceparent[:50]}, path: {request.url.path}"
                )
                if self.metrics:
                    self.metrics.trace_context_extraction_failure_total.labels(
                        **self._metric_labels,
                        reason="invalid_format"
                    ).inc()
        else:
            # Métrica: traceparent ausente
            logger.debug(f"No traceparent header in request, path: {request.url.path}")
            if self.metrics:
                self.metrics.trace_parent_missing_total.labels(
                    **self._metric_labels,
                    source="http"
                ).inc()

        # Processar request
        response = await call_next(request)

        # Injetar headers de tracing na response (opcional)
        response = self._inject_trace_headers(response, trace_valid)

        # Limpar contexto anexado
        if context_token is not None:
            context.detach(context_token)

        return response

    def _set_baggage_from_headers(self, request: Request):
        """
        Define baggage items a partir de headers Neural Hive customizados.

        Args:
            request: Request HTTP com headers
        """
        if not self.extract_custom_headers:
            return

        # Headers customizados Neural Hive para baggage
        header_mappings = {
            "x-neural-hive-intent-id": "neural.hive.intent.id",
            "x-neural-hive-plan-id": "neural.hive.plan.id",
            "x-neural-hive-user-id": "neural.hive.user.id",
            "x-neural-hive-domain": "neural.hive.domain",
            "x-neural-hive-channel": "neural.hive.channel",
            "x-neural-hive-correlation-id": "neural.hive.correlation.id",
        }

        for header_name, baggage_key in header_mappings.items():
            value = request.headers.get(header_name)
            if value:
                try:
                    set_baggage(baggage_key, value)
                    logger.debug(
                        f"Baggage item set: key={baggage_key}, value={value[:50]}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to set baggage {baggage_key}: {e}")

    def _inject_trace_headers(
        self, response: Response, trace_valid: bool
    ) -> Response:
        """
        Injeta headers de tracing na response HTTP.

        Args:
            response: Response HTTP
            trace_valid: Se trace context foi extraído/validado

        Returns:
            Response com headers de tracing
        """
        # Injetar trace ID atual se disponível
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_context = span.get_span_context()
            trace_id = format(span_context.trace_id, "032x")

            # Criar traceparent para response (opcional - server-generated)
            # Alguns sistemas preferem não ecoar traceparent na response
            # response.headers["traceparent"] = f"00-{trace_id}-{format(span_context.span_id, '016x')}-{span_context.trace_flags:02x}"

            # Injetar trace ID customizado para facilitar debugging
            response.headers["x-trace-id"] = trace_id

        return response


def validate_trace_context(request: Request) -> Tuple[bool, Optional[str]]:
    """
    Valida trace context em request HTTP.

    Args:
        request: Request HTTP

    Returns:
        Tuple de (is_valid, error_message)
    """
    traceparent = extract_traceparent_from_request(request)

    if not traceparent:
        return False, "Missing traceparent header"

    parsed = parse_traceparent(traceparent)
    if not parsed:
        return False, f"Invalid traceparent format: {traceparent[:50]}"

    return True, None


def get_trace_id_from_request(request: Request) -> Optional[str]:
    """
    Extrai trace ID do request HTTP.

    Args:
        request: Request HTTP

    Returns:
        Trace ID ou None
    """
    traceparent = extract_traceparent_from_request(request)

    if not traceparent:
        return None

    parsed = parse_traceparent(traceparent)
    if not parsed:
        return None

    trace_id, _, _ = parsed
    return trace_id


__all__ = [
    "TraceContextMiddleware",
    "parse_traceparent",
    "extract_traceparent_from_request",
    "extract_tracestate_from_request",
    "validate_trace_context",
    "get_trace_id_from_request",
]
