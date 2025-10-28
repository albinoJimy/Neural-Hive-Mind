"""
Módulo de tracing distribuído para Neural Hive-Mind.

Implementa decorators @trace_intent, @trace_plan, context managers e utilities
para span enrichment. Integra com OpenTelemetry SDK para correlação automática
por intent_id e plan_id conforme Fluxo D.
"""

import functools
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any, Callable, Union
import inspect

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.auto_instrumentation import sitecustomize
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import Status, StatusCode, Span
from opentelemetry.baggage import get_baggage, set_baggage
from opentelemetry.context import attach, detach

from .config import ObservabilityConfig
from .context import ContextManager

logger = logging.getLogger(__name__)

# Tracer global
_tracer: Optional[trace.Tracer] = None
_config: Optional[ObservabilityConfig] = None

def init_tracing(config: ObservabilityConfig) -> None:
    """
    Inicializa o tracing com OpenTelemetry.

    Args:
        config: Configuração de observabilidade
    """
    global _tracer, _config
    _config = config

    # Criar resource com metadados do serviço
    resource = Resource.create({
        "service.name": config.service_name,
        "service.version": config.service_version,
        "service.instance.id": config.service_instance_id,
        "neural.hive.component": config.neural_hive_component,
        "neural.hive.layer": config.neural_hive_layer,
        "neural.hive.domain": config.neural_hive_domain or "unknown",
        "deployment.environment": config.environment,
        "telemetry.sdk.name": "neural_hive_observability",
        "telemetry.sdk.version": "1.0.0",
    })

    # Configurar tracer provider
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    # Configurar exporter OTLP
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=config.otel_endpoint,
            insecure=True,  # TODO: Configurar TLS em produção
            headers={
                "X-Neural-Hive-Source": config.service_name,
                "X-Neural-Hive-Component": config.neural_hive_component,
            }
        )

        # Adicionar batch processor
        span_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=config.trace_batch_size,
            export_timeout_millis=config.trace_export_timeout_ms,
            schedule_delay_millis=config.trace_schedule_delay_ms
        )
        tracer_provider.add_span_processor(span_processor)

        logger.info(f"Tracing inicializado para {config.service_name}")
    except Exception as e:
        logger.warning(f"Erro ao configurar OTLP exporter: {e}")

    # Criar tracer
    _tracer = trace.get_tracer(
        __name__,
        version="1.0.0",
        tracer_provider=tracer_provider
    )

def get_tracer() -> Optional[trace.Tracer]:
    """Retorna o tracer configurado."""
    return _tracer

@contextmanager
def correlation_context(
    intent_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    user_id: Optional[str] = None,
    domain: Optional[str] = None,
    **additional_context
):
    """
    Context manager para correlação distribuída.

    Args:
        intent_id: ID da intenção
        plan_id: ID do plano
        user_id: ID do usuário
        domain: Domínio específico
        **additional_context: Contexto adicional
    """
    if not _tracer:
        yield
        return

    # Preparar baggage
    baggage_items = {}
    if intent_id:
        baggage_items["neural.hive.intent.id"] = intent_id
    if plan_id:
        baggage_items["neural.hive.plan.id"] = plan_id
    if user_id:
        baggage_items["neural.hive.user.id"] = user_id
    if domain:
        baggage_items["neural.hive.domain"] = domain

    # Adicionar contexto adicional
    for key, value in additional_context.items():
        if value is not None:
            baggage_items[f"neural.hive.{key}"] = str(value)

    # Definir baggage
    tokens = []
    for key, value in baggage_items.items():
        token = set_baggage(key, value)
        tokens.append(token)

    try:
        yield
    finally:
        # Limpar baggage
        for token in tokens:
            if token:
                detach(token)

def trace_intent(
    operation_name: Optional[str] = None,
    extract_intent_id_from: Optional[str] = None,
    extract_plan_id_from: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False
):
    """
    Decorator para tracing automático de operações com intent_id.

    Args:
        operation_name: Nome da operação (padrão: nome da função)
        extract_intent_id_from: Nome do parâmetro que contém intent_id
        extract_plan_id_from: Nome do parâmetro que contém plan_id
        include_args: Incluir argumentos no span
        include_result: Incluir resultado no span
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not _tracer:
                return func(*args, **kwargs)

            # Determinar nome da operação
            op_name = operation_name or f"{_config.neural_hive_component}.{func.__name__}"

            # Extrair IDs dos parâmetros
            intent_id = None
            plan_id = None

            # Usar inspect para mapear args para parâmetros
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            if extract_intent_id_from and extract_intent_id_from in bound_args.arguments:
                intent_id = bound_args.arguments[extract_intent_id_from]

            if extract_plan_id_from and extract_plan_id_from in bound_args.arguments:
                plan_id = bound_args.arguments[extract_plan_id_from]

            # Tentar extrair de kwargs comuns
            if not intent_id:
                intent_id = kwargs.get("intent_id") or kwargs.get("intention_id")

            if not plan_id:
                plan_id = kwargs.get("plan_id")

            with _tracer.start_as_current_span(op_name) as span:
                try:
                    # Enricher span com metadados
                    span.set_attribute("neural.hive.component", _config.neural_hive_component)
                    span.set_attribute("neural.hive.layer", _config.neural_hive_layer)
                    span.set_attribute("neural.hive.operation", func.__name__)

                    if intent_id:
                        span.set_attribute("neural.hive.intent.id", intent_id)
                        set_baggage("neural.hive.intent.id", intent_id)

                    if plan_id:
                        span.set_attribute("neural.hive.plan.id", plan_id)
                        set_baggage("neural.hive.plan.id", plan_id)

                    if _config.neural_hive_domain:
                        span.set_attribute("neural.hive.domain", _config.neural_hive_domain)

                    # Incluir argumentos se solicitado
                    if include_args:
                        for param_name, value in bound_args.arguments.items():
                            # Evitar logar dados sensíveis
                            if not _is_sensitive_param(param_name):
                                span.set_attribute(f"args.{param_name}", str(value)[:100])

                    # Executar função
                    result = func(*args, **kwargs)

                    # Incluir resultado se solicitado
                    if include_result and result is not None:
                        if hasattr(result, "__dict__"):
                            span.set_attribute("result.type", type(result).__name__)
                        else:
                            span.set_attribute("result", str(result)[:100])

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator

def trace_plan(
    operation_name: Optional[str] = None,
    extract_plan_id_from: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False
):
    """
    Decorator específico para tracing de operações de planos.

    Args:
        operation_name: Nome da operação
        extract_plan_id_from: Nome do parâmetro que contém plan_id
        include_args: Incluir argumentos no span
        include_result: Incluir resultado no span
    """
    return trace_intent(
        operation_name=operation_name,
        extract_plan_id_from=extract_plan_id_from,
        include_args=include_args,
        include_result=include_result
    )

def enrich_span(
    span: Span,
    intent_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    user_id: Optional[str] = None,
    operation_type: Optional[str] = None,
    **additional_attributes
) -> None:
    """
    Enriche span com atributos específicos do Neural Hive-Mind.

    Args:
        span: Span OpenTelemetry
        intent_id: ID da intenção
        plan_id: ID do plano
        user_id: ID do usuário
        operation_type: Tipo da operação
        **additional_attributes: Atributos adicionais
    """
    if intent_id:
        span.set_attribute("neural.hive.intent.id", intent_id)

    if plan_id:
        span.set_attribute("neural.hive.plan.id", plan_id)

    if user_id:
        span.set_attribute("neural.hive.user.id", user_id)

    if operation_type:
        span.set_attribute("neural.hive.operation.type", operation_type)

    # Adicionar atributos adicionais
    for key, value in additional_attributes.items():
        if value is not None:
            span.set_attribute(f"neural.hive.{key}", str(value))

def get_current_trace_id() -> Optional[str]:
    """Retorna o trace ID atual."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return None

def get_current_span_id() -> Optional[str]:
    """Retorna o span ID atual."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, "016x")
    return None

def get_correlation_context() -> Dict[str, Any]:
    """
    Retorna o contexto de correlação atual.

    Returns:
        Dicionário com intent_id, plan_id e outros identificadores
    """
    context = {}

    # Extrair de baggage
    baggage_items = get_baggage() or {}
    for key, value in baggage_items.items():
        if key.startswith("neural.hive."):
            context_key = key.replace("neural.hive.", "").replace(".", "_")
            context[context_key] = value

    # Adicionar trace/span IDs
    trace_id = get_current_trace_id()
    if trace_id:
        context["trace_id"] = trace_id

    span_id = get_current_span_id()
    if span_id:
        context["span_id"] = span_id

    return context

def _is_sensitive_param(param_name: str) -> bool:
    """
    Verifica se um parâmetro contém dados sensíveis.

    Args:
        param_name: Nome do parâmetro

    Returns:
        True se o parâmetro for sensível
    """
    sensitive_patterns = [
        "password", "passwd", "pwd", "secret", "token", "key",
        "credential", "auth", "session", "cookie", "pii",
        "ssn", "cpf", "email", "phone", "address"
    ]

    param_lower = param_name.lower()
    return any(pattern in param_lower for pattern in sensitive_patterns)

def create_child_span(
    name: str,
    parent_span: Optional[Span] = None,
    **attributes
) -> Span:
    """
    Cria um span filho com atributos padrão do Neural Hive-Mind.

    Args:
        name: Nome do span
        parent_span: Span pai (opcional)
        **attributes: Atributos adicionais

    Returns:
        Span criado
    """
    if not _tracer:
        raise RuntimeError("Tracer não inicializado")

    # Usar span atual como pai se não especificado
    if parent_span is None:
        parent_span = trace.get_current_span()

    # Criar contexto com span pai
    ctx = trace.set_span_in_context(parent_span) if parent_span else None

    span = _tracer.start_span(name, context=ctx)

    # Adicionar atributos padrão
    if _config:
        span.set_attribute("neural.hive.component", _config.neural_hive_component)
        span.set_attribute("neural.hive.layer", _config.neural_hive_layer)

    # Adicionar atributos customizados
    for key, value in attributes.items():
        span.set_attribute(key, str(value))

    return span