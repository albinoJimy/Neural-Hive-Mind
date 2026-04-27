"""Módulo de observabilidade para clientes LLM.

Integra OpenTelemetry tracing, Prometheus metrics e structlog
para observabilidade completa de operações LLM.
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from enum import Enum
from typing import Any, Final, Optional

import structlog
from prometheus_client import CollectorRegistry, Counter, Histogram

logger = structlog.get_logger()

# Registry dedicado para métricas LLM
_llm_metrics_registry = CollectorRegistry()

# Métricas Prometheus específicas para LLM
LLM_GENERATION_DURATION = Histogram(
    "llm_generation_duration_seconds",
    "Duração de gerações LLM",
    ["service", "provider", "model", "operation_type"],  # operation_type: generate, stream, batch
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
    registry=_llm_metrics_registry,
)

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total de requisições LLM",
    ["service", "provider", "model", "status", "operation_type"],
    registry=_llm_metrics_registry,
)

LLM_ERRORS_TOTAL = Counter(
    "llm_errors_total",
    "Total de erros LLM",
    ["service", "provider", "model", "error_type"],
    registry=_llm_metrics_registry,
)


class OperationType(str, Enum):
    """Tipos de operação LLM."""

    GENERATE = "generate"
    STREAM = "stream"
    BATCH = "batch"


class LLMTracer:
    """Gerencia tracing e métricas para operações LLM.

    Integra com OpenTelemetry para tracing distribuído e
    Prometheus para métricas.

    Attributes:
        service_name: Nome do serviço para labels
    """

    def __init__(self, service_name: str = "neural_hive_llm"):
        """Inicializa tracer LLM.

        Args:
            service_name: Nome do serviço para métricas e traces
        """
        self.service_name = service_name
        self.logger = structlog.get_logger().bind(service=service_name)

        # Tentar importar OpenTelemetry (opcional)
        self._tracer = None
        self._otel_available = False
        try:
            from opentelemetry import trace

            self._tracer = trace.get_tracer(__name__)
            self._otel_available = True
        except ImportError:
            self.logger.debug("opentelemetry_not_available", message="Tracing será desabilitado")

    @property
    def otel_available(self) -> bool:
        """Verifica se OpenTelemetry está disponível."""
        return self._otel_available

    @asynccontextmanager
    async def trace_generation(
        self,
        provider: str,
        model: str,
        operation_type: OperationType = OperationType.GENERATE,
        prompt: str | None = None,
        **attributes: Any,
    ):
        """Context manager para tracing de geração LLM.

        Cria span OpenTelemetry e registra métricas Prometheus.

        Args:
            provider: Nome do provedor (openai, anthropic, local)
            model: Nome do modelo
            operation_type: Tipo de operação
            prompt: Prompt usado (opcional, truncado no log)
            **attributes: Atributos adicionais para o span

        Yields:
            Objeto LLMSpanContext com métodos para gravar resultado
        """
        span = None
        start_time = time.time()
        status = "success"

        # Iniciar span OpenTelemetry se disponível
        if self._otel_available and self._tracer:
            from opentelemetry import trace
            from opentelemetry.trace import Status, StatusCode

            span = self._tracer.start_span(
                name=f"llm.{operation_type.value}",
                attributes={
                    "llm.provider": provider,
                    "llm.model": model,
                    "llm.operation_type": operation_type.value,
                    "llm.service": self.service_name,
                    **attributes,
                },
            )

            # Adicionar prompt como atributo (truncado)
            if prompt:
                prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                if span.is_recording():
                    span.set_attribute("llm.prompt", prompt_preview)

            # Configurar contexto de log com trace info
            ctx = span.get_span_context()
            self.logger = self.logger.bind(
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
            )

        try:
            span_context = LLMSpanContext(
                tracer=self,
                span=span,
                provider=provider,
                model=model,
                operation_type=operation_type,
                start_time=start_time,
            )
            yield span_context

            # Status baseado no resultado
            status = span_context.status

        except Exception as e:
            status = "error"
            if span and span.is_recording():
                from opentelemetry.trace import Status, StatusCode

                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
            raise

        finally:
            # Finalizar span
            duration = time.time() - start_time

            if span and span.is_recording():
                from opentelemetry.trace import StatusCode

                if status == "success":
                    span.set_status(StatusCode.OK)
                span.end()

            # Registrar métricas
            LLM_GENERATION_DURATION.labels(
                service=self.service_name,
                provider=provider,
                model=model,
                operation_type=operation_type.value,
            ).observe(duration)

            LLM_REQUESTS_TOTAL.labels(
                service=self.service_name,
                provider=provider,
                model=model,
                status=status,
                operation_type=operation_type.value,
            ).inc()

            self.logger.debug(
                "llm_generation_completed",
                provider=provider,
                model=model,
                operation_type=operation_type.value,
                duration_seconds=duration,
                status=status,
            )

    @contextmanager
    def trace_generation_sync(
        self,
        provider: str,
        model: str,
        operation_type: OperationType = OperationType.GENERATE,
        prompt: str | None = None,
        **attributes: Any,
    ):
        """Versão síncrona do context manager de tracing."""
        span = None
        start_time = time.time()
        status = "success"

        if self._otel_available and self._tracer:
            from opentelemetry import trace
            from opentelemetry.trace import Status, StatusCode

            span = self._tracer.start_span(
                name=f"llm.{operation_type.value}",
                attributes={
                    "llm.provider": provider,
                    "llm.model": model,
                    "llm.operation_type": operation_type.value,
                    "llm.service": self.service_name,
                    **attributes,
                },
            )

            if prompt:
                prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                if span.is_recording():
                    span.set_attribute("llm.prompt", prompt_preview)

            ctx = span.get_span_context()
            self.logger = self.logger.bind(
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
            )

        try:
            span_context = LLMSpanContext(
                tracer=self,
                span=span,
                provider=provider,
                model=model,
                operation_type=operation_type,
                start_time=start_time,
            )
            yield span_context
            status = span_context.status

        except Exception as e:
            status = "error"
            if span and span.is_recording():
                from opentelemetry.trace import Status, StatusCode

                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
            raise

        finally:
            duration = time.time() - start_time

            if span and span.is_recording():
                from opentelemetry.trace import StatusCode

                if status == "success":
                    span.set_status(StatusCode.OK)
                span.end()

            LLM_GENERATION_DURATION.labels(
                service=self.service_name,
                provider=provider,
                model=model,
                operation_type=operation_type.value,
            ).observe(duration)

            LLM_REQUESTS_TOTAL.labels(
                service=self.service_name,
                provider=provider,
                model=model,
                status=status,
                operation_type=operation_type.value,
            ).inc()

            self.logger.debug(
                "llm_generation_completed",
                provider=provider,
                model=model,
                operation_type=operation_type.value,
                duration_seconds=duration,
                status=status,
            )

    def record_error(self, provider: str, model: str, error_type: str, error: Exception):
        """Registra erro nas métricas.

        Args:
            provider: Nome do provedor
            model: Nome do modelo
            error_type: Tipo de erro (rate_limit, timeout, etc)
            error: Exceção ocorrida
        """
        LLM_ERRORS_TOTAL.labels(
            service=self.service_name,
            provider=provider,
            model=model,
            error_type=error_type,
        ).inc()

        self.logger.warning(
            "llm_error_recorded",
            provider=provider,
            model=model,
            error_type=error_type,
            error=str(error),
        )


class LLMSpanContext:
    """Contexto para registrar informações em um span de geração LLM."""

    def __init__(
        self,
        tracer: LLMTracer,
        span: Any,
        provider: str,
        model: str,
        operation_type: OperationType,
        start_time: float,
    ):
        """Inicializa contexto de span."""
        self._tracer = tracer
        self._span = span
        self.provider = provider
        self.model = model
        self.operation_type = operation_type
        self._start_time = start_time
        self._status = "success"
        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._response_text: str | None = None

    def set_result(
        self,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        response_text: str | None = None,
    ):
        """Define resultado da geração.

        Args:
            input_tokens: Tokens de entrada
            output_tokens: Tokens de saída
            response_text: Texto da resposta
        """
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._response_text = response_text

        # Atualizar span se disponível
        if self._span and self._span.is_recording():
            if input_tokens is not None:
                self._span.set_attribute("llm.input_tokens", input_tokens)
            if output_tokens is not None:
                self._span.set_attribute("llm.output_tokens", output_tokens)
            if response_text:
                preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
                self._span.set_attribute("llm.response", preview)

    def set_error(self, error_type: str, message: str):
        """Define erro na geração.

        Args:
            error_type: Tipo de erro
            message: Mensagem de erro
        """
        self._status = "error"

        if self._span and self._span.is_recording():
            self._span.set_attribute("llm.error_type", error_type)
            self._span.set_attribute("llm.error_message", message)

    @property
    def status(self) -> str:
        """Retorna status da operação."""
        return self._status


# Instância global
_global_tracer: Optional[LLMTracer] = None


def get_llm_tracer(service_name: str = "neural_hive_llm") -> LLMTracer:
    """Retorna instância global de LLMTracer.

    Args:
        service_name: Nome do serviço (usado apenas na primeira chamada)

    Returns:
        Instância de LLMTracer
    """
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = LLMTracer(service_name=service_name)
    return _global_tracer


__all__ = [
    "OperationType",
    "LLMTracer",
    "LLMSpanContext",
    "get_llm_tracer",
    "LLM_GENERATION_DURATION",
    "LLM_REQUESTS_TOTAL",
    "LLM_ERRORS_TOTAL",
]
