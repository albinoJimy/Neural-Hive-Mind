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

from opentelemetry import trace, context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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
        instrumenting_library_version="1.0.0",
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

    tokens = []
    current_ctx = context.get_current()
    for key, value in baggage_items.items():
        current_ctx = set_baggage(key, value, current_ctx)
        token = attach(current_ctx)
        tokens.append(token)

    try:
        yield
    finally:
        for token in reversed(tokens):
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

def trace_grpc_method(
    operation_name: Optional[str] = None,
    extract_intent_id_from: Optional[str] = None,
    extract_plan_id_from: Optional[str] = None,
    include_request: bool = False,
    include_response: bool = False
):
    """
    Decorator para tracing de métodos gRPC com enriquecimento padrão.

    Args:
        operation_name: Nome customizado do span
        extract_intent_id_from: Campo do request para extrair intent_id
        extract_plan_id_from: Campo do request para extrair plan_id
        include_request: Registrar request no span
        include_response: Registrar response no span
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, request, context, *args, **kwargs):
            if not _tracer:
                return func(self, request, context, *args, **kwargs)

            # Extrair contexto gRPC e baggage
            metadata = {}
            grpc_token = None
            try:
                invocation_metadata = context.invocation_metadata() if context else []
                metadata = {k: v for k, v in invocation_metadata}
                from .grpc_instrumentation import extract_grpc_context
                extracted = extract_grpc_context(context)
                if isinstance(extracted, tuple):
                    grpc_context, grpc_token = extracted
                else:
                    grpc_context = extracted
            except Exception:
                grpc_context = {}

            intent_id = grpc_context.get("intent_id")
            plan_id = grpc_context.get("plan_id")

            # Tentar extrair do request
            if extract_intent_id_from and hasattr(request, extract_intent_id_from):
                intent_id = getattr(request, extract_intent_id_from, intent_id)
            if extract_plan_id_from and hasattr(request, extract_plan_id_from):
                plan_id = getattr(request, extract_plan_id_from, plan_id)

            span_name = operation_name or f"{_config.neural_hive_component}.grpc.{func.__name__}"

            with _tracer.start_as_current_span(span_name) as span:
                try:
                    span.set_attribute("neural.hive.component", _config.neural_hive_component)
                    span.set_attribute("neural.hive.layer", _config.neural_hive_layer)
                    span.set_attribute("neural.hive.grpc.method", func.__name__)
                    span.set_attribute("neural.hive.grpc.service", self.__class__.__name__)

                    if intent_id:
                        span.set_attribute("neural.hive.intent.id", intent_id)
                        set_baggage("neural.hive.intent.id", str(intent_id))

                    if plan_id:
                        span.set_attribute("neural.hive.plan.id", plan_id)
                        set_baggage("neural.hive.plan.id", str(plan_id))

                    for key, value in metadata.items():
                        span.set_attribute(f"grpc.metadata.{key}", str(value))

                    if include_request and request is not None:
                        span.set_attribute("grpc.request", str(request)[:500])

                    result = func(self, request, context, *args, **kwargs)

                    if include_response and result is not None:
                        span.set_attribute("grpc.response", str(result)[:500])

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as exc:
                    span.record_exception(exc)
                    status_code_attr = getattr(exc, "code", None)
                    try:
                        status_code_value = status_code_attr() if callable(status_code_attr) else status_code_attr
                    except Exception:
                        status_code_value = None

                    if status_code_value is not None:
                        span.set_attribute("grpc.status_code", str(status_code_value))
                        details_attr = getattr(exc, "details", None)
                        try:
                            details_value = details_attr() if callable(details_attr) else details_attr
                        except Exception:
                            details_value = None
                        if details_value:
                            span.set_attribute("grpc.status_details", str(details_value))

                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    raise
                finally:
                    if grpc_token:
                        detach(grpc_token)

        return wrapper
    return decorator

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

def inject_context_to_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Injeta contexto OpenTelemetry em headers.
    
    Args:
        headers: Headers existentes
        
    Returns:
        Headers com contexto injetado
    """
    from opentelemetry.propagate import inject
    
    new_headers = headers.copy()
    inject(new_headers)
    
    # Adicionar baggage items como headers customizados
    correlation = get_correlation_context()
    if "intent_id" in correlation:
        new_headers["x-neural-hive-intent-id"] = correlation["intent_id"]
    if "plan_id" in correlation:
        new_headers["x-neural-hive-plan-id"] = correlation["plan_id"]
    if "user_id" in correlation:
        new_headers["x-neural-hive-user-id"] = correlation["user_id"]
    
    return new_headers

def extract_context_from_headers(headers: Dict[str, str]):
    """
    Extrai contexto OpenTelemetry de headers e define no contexto atual.
    
    Args:
        headers: Headers com contexto

    Returns:
        Token de contexto para ser usado em detach() pelo chamador, ou None
    """
    from opentelemetry.propagate import extract
    
    token = None
    try:
        ctx = extract(headers)
        token = attach(ctx)
    except Exception:
        token = None
    
    # Extrair e definir baggage items
    if "x-neural-hive-intent-id" in headers:
        set_baggage("neural.hive.intent.id", headers["x-neural-hive-intent-id"])
    if "x-neural-hive-plan-id" in headers:
        set_baggage("neural.hive.plan.id", headers["x-neural-hive-plan-id"])
    if "x-neural-hive-user-id" in headers:
        set_baggage("neural.hive.user.id", headers["x-neural-hive-user-id"])

    return token
