"""
Correlation Support for Neural Hive-Mind

Implementa correlação distribuída usando headers HTTP e OpenTelemetry baggage
para rastreamento de intenções, planos e contexto através dos componentes.
"""

import logging
import threading
from typing import Dict, Optional, Any, Callable, TypeVar, Union
from functools import wraps
from contextlib import contextmanager
from dataclasses import dataclass, field

from .config import get_config


logger = logging.getLogger(__name__)

T = TypeVar('T')

# Thread-local storage para contexto de correlação
_correlation_context = threading.local()


@dataclass
class CorrelationContext:
    """Contexto de correlação Neural Hive-Mind."""

    intent_id: Optional[str] = None
    plan_id: Optional[str] = None
    domain: Optional[str] = None
    user_id: Optional[str] = None

    # Metadados adicionais
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validação pós-inicialização."""
        # Validar formato dos IDs se fornecidos
        self._validate_id("intent_id", self.intent_id)
        self._validate_id("plan_id", self.plan_id)
        self._validate_id("user_id", self.user_id)

    def _validate_id(self, field_name: str, value: Optional[str]):
        """Valida formato de ID."""
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                logger.warning(f"ID inválido para {field_name}: {value}")

    def to_dict(self) -> Dict[str, str]:
        """Converte contexto para dicionário, removendo valores None."""
        result = {}

        if self.intent_id:
            result["intent_id"] = self.intent_id
        if self.plan_id:
            result["plan_id"] = self.plan_id
        if self.domain:
            result["domain"] = self.domain
        if self.user_id:
            result["user_id"] = self.user_id

        # Adicionar metadados como strings
        for key, value in self.metadata.items():
            if value is not None:
                result[f"metadata_{key}"] = str(value)

        return result

    def to_headers(self) -> Dict[str, str]:
        """Converte contexto para headers HTTP."""
        config = get_config()
        headers = {}

        if self.intent_id and config.get_correlation_header("intent_id"):
            headers[config.get_correlation_header("intent_id")] = self.intent_id

        if self.plan_id and config.get_correlation_header("plan_id"):
            headers[config.get_correlation_header("plan_id")] = self.plan_id

        if self.domain and config.get_correlation_header("domain"):
            headers[config.get_correlation_header("domain")] = self.domain

        if self.user_id and config.get_correlation_header("user_id"):
            headers[config.get_correlation_header("user_id")] = self.user_id

        return headers

    def to_baggage(self) -> Dict[str, str]:
        """Converte contexto para baggage OpenTelemetry."""
        config = get_config()
        baggage = {}

        if self.intent_id and config.get_baggage_key("intent_id"):
            baggage[config.get_baggage_key("intent_id")] = self.intent_id

        if self.plan_id and config.get_baggage_key("plan_id"):
            baggage[config.get_baggage_key("plan_id")] = self.plan_id

        if self.domain and config.get_baggage_key("domain"):
            baggage[config.get_baggage_key("domain")] = self.domain

        if self.user_id and config.get_baggage_key("user_id"):
            baggage[config.get_baggage_key("user_id")] = self.user_id

        return baggage

    def merge_with(self, other: "CorrelationContext") -> "CorrelationContext":
        """Merge com outro contexto, priorizando valores não-nulos."""
        return CorrelationContext(
            intent_id=self.intent_id or other.intent_id,
            plan_id=self.plan_id or other.plan_id,
            domain=self.domain or other.domain,
            user_id=self.user_id or other.user_id,
            metadata={**other.metadata, **self.metadata},
        )

    def is_empty(self) -> bool:
        """Verifica se contexto está vazio."""
        return not any([self.intent_id, self.plan_id, self.domain, self.user_id])

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "CorrelationContext":
        """Cria contexto a partir de dicionário."""
        metadata = {}

        # Extrair metadados
        for key, value in data.items():
            if key.startswith("metadata_"):
                metadata[key[9:]] = value  # Remove 'metadata_' prefix

        return cls(
            intent_id=data.get("intent_id"),
            plan_id=data.get("plan_id"),
            domain=data.get("domain"),
            user_id=data.get("user_id"),
            metadata=metadata,
        )

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> "CorrelationContext":
        """Cria contexto a partir de headers HTTP."""
        config = get_config()
        correlation_data = {}

        # Mapear headers para campos
        header_mapping = {
            config.get_correlation_header("intent_id"): "intent_id",
            config.get_correlation_header("plan_id"): "plan_id",
            config.get_correlation_header("domain"): "domain",
            config.get_correlation_header("user_id"): "user_id",
        }

        for header_name, field_name in header_mapping.items():
            if header_name and header_name in headers:
                correlation_data[field_name] = headers[header_name]

        return cls(**correlation_data)

    @classmethod
    def from_baggage(cls, baggage: Dict[str, str]) -> "CorrelationContext":
        """Cria contexto a partir de baggage OpenTelemetry."""
        config = get_config()
        correlation_data = {}

        # Mapear baggage keys para campos
        baggage_mapping = {
            config.get_baggage_key("intent_id"): "intent_id",
            config.get_baggage_key("plan_id"): "plan_id",
            config.get_baggage_key("domain"): "domain",
            config.get_baggage_key("user_id"): "user_id",
        }

        for baggage_key, field_name in baggage_mapping.items():
            if baggage_key and baggage_key in baggage:
                correlation_data[field_name] = baggage[baggage_key]

        return cls(**correlation_data)


def set_correlation_context(context: CorrelationContext):
    """Define contexto de correlação para thread atual."""
    _correlation_context.context = context
    logger.debug(f"Contexto de correlação definido: {context.to_dict()}")

    # Propagar para OpenTelemetry baggage se disponível
    _propagate_to_otel_baggage(context)


def get_correlation_context() -> Optional[CorrelationContext]:
    """Obtém contexto de correlação da thread atual."""
    return getattr(_correlation_context, 'context', None)


def get_current_correlation_context() -> Dict[str, str]:
    """Obtém contexto atual como dicionário."""
    context = get_correlation_context()
    return context.to_dict() if context else {}


def clear_correlation_context():
    """Limpa contexto de correlação da thread atual."""
    if hasattr(_correlation_context, 'context'):
        delattr(_correlation_context, 'context')
    logger.debug("Contexto de correlação limpo")


@contextmanager
def with_correlation(context: CorrelationContext):
    """
    Context manager para definir contexto de correlação temporariamente.

    Args:
        context: Contexto de correlação a ser usado

    Example:
        ```python
        context = CorrelationContext(intent_id="intent-123", domain="experiencia")
        with with_correlation(context):
            # Código executado com contexto de correlação
            process_request()
        ```
    """
    previous_context = get_correlation_context()

    try:
        set_correlation_context(context)
        yield context
    finally:
        if previous_context:
            set_correlation_context(previous_context)
        else:
            clear_correlation_context()


def trace_correlation(
    intent_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    domain: Optional[str] = None,
    user_id: Optional[str] = None,
    merge_with_existing: bool = True,
):
    """
    Decorator para adicionar correlação a funções.

    Args:
        intent_id: ID da intenção
        plan_id: ID do plano
        domain: Domínio Neural Hive-Mind
        user_id: ID do usuário
        merge_with_existing: Se deve fazer merge com contexto existente

    Example:
        ```python
        @trace_correlation(domain="cognicao", intent_id="intent-456")
        def process_cognitive_task():
            # Função executada com contexto de correlação
            pass
        ```
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            new_context = CorrelationContext(
                intent_id=intent_id,
                plan_id=plan_id,
                domain=domain,
                user_id=user_id,
            )

            if merge_with_existing:
                existing_context = get_correlation_context()
                if existing_context:
                    new_context = existing_context.merge_with(new_context)

            with with_correlation(new_context):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def extract_correlation_from_request(request: Any) -> CorrelationContext:
    """
    Extrai correlação de request HTTP.

    Args:
        request: Objeto de request (Flask, FastAPI, etc.)

    Returns:
        Contexto de correlação extraído
    """
    headers = {}

    # Tentar extrair headers de diferentes frameworks
    if hasattr(request, 'headers'):
        # Flask/FastAPI style
        headers = dict(request.headers)
    elif hasattr(request, 'META'):
        # Django style
        headers = {
            key.replace('HTTP_', '').replace('_', '-').lower(): value
            for key, value in request.META.items()
            if key.startswith('HTTP_')
        }

    # Normalizar nomes dos headers (case-insensitive)
    normalized_headers = {key.lower(): value for key, value in headers.items()}

    # Extrair correlação
    context = CorrelationContext.from_headers(normalized_headers)

    # Tentar extrair também do OpenTelemetry baggage
    otel_context = _extract_from_otel_baggage()
    if otel_context:
        context = context.merge_with(otel_context)

    return context


def inject_correlation_into_request(headers: Dict[str, str], context: Optional[CorrelationContext] = None) -> Dict[str, str]:
    """
    Injeta correlação em headers de request.

    Args:
        headers: Headers existentes
        context: Contexto de correlação (usa atual se None)

    Returns:
        Headers com correlação injetada
    """
    if context is None:
        context = get_correlation_context()

    if context is None:
        return headers

    # Adicionar headers de correlação
    correlation_headers = context.to_headers()
    updated_headers = {**headers, **correlation_headers}

    logger.debug(f"Headers de correlação injetados: {correlation_headers}")
    return updated_headers


def _propagate_to_otel_baggage(context: CorrelationContext):
    """Propaga contexto para OpenTelemetry baggage."""
    try:
        from opentelemetry import baggage

        baggage_dict = context.to_baggage()
        for key, value in baggage_dict.items():
            baggage.set_baggage(key, value)

        logger.debug(f"Contexto propagado para OpenTelemetry baggage: {baggage_dict}")

    except ImportError:
        logger.debug("OpenTelemetry não disponível para propagação de baggage")
    except Exception as e:
        logger.warning(f"Erro ao propagar para OpenTelemetry baggage: {e}")


def _extract_from_otel_baggage() -> Optional[CorrelationContext]:
    """Extrai contexto do OpenTelemetry baggage."""
    try:
        from opentelemetry import baggage

        config = get_config()
        baggage_data = {}

        # Extrair valores do baggage
        for correlation_type in ["intent_id", "plan_id", "domain", "user_id"]:
            baggage_key = config.get_baggage_key(correlation_type)
            if baggage_key:
                value = baggage.get_baggage(baggage_key)
                if value:
                    baggage_data[baggage_key] = value

        if baggage_data:
            return CorrelationContext.from_baggage(baggage_data)

    except ImportError:
        logger.debug("OpenTelemetry não disponível para extração de baggage")
    except Exception as e:
        logger.warning(f"Erro ao extrair do OpenTelemetry baggage: {e}")

    return None


def create_correlation_middleware(framework: str = "flask"):
    """
    Cria middleware de correlação para diferentes frameworks.

    Args:
        framework: Framework web ("flask", "fastapi", "django")

    Returns:
        Função de middleware
    """
    if framework.lower() == "flask":
        return _create_flask_middleware()
    elif framework.lower() == "fastapi":
        return _create_fastapi_middleware()
    elif framework.lower() == "django":
        return _create_django_middleware()
    else:
        raise ValueError(f"Framework não suportado: {framework}")


def _create_flask_middleware():
    """Cria middleware para Flask."""
    from flask import request, g

    def correlation_middleware():
        # Extrair correlação do request
        context = extract_correlation_from_request(request)
        if not context.is_empty():
            set_correlation_context(context)
            g.correlation_context = context

    return correlation_middleware


def _create_fastapi_middleware():
    """Cria middleware para FastAPI."""
    from fastapi import Request

    async def correlation_middleware(request: Request, call_next):
        # Extrair correlação do request
        context = extract_correlation_from_request(request)
        if not context.is_empty():
            set_correlation_context(context)

        response = await call_next(request)

        # Limpar contexto após processamento
        clear_correlation_context()

        return response

    return correlation_middleware


def _create_django_middleware():
    """Cria middleware para Django."""

    class CorrelationMiddleware:
        def __init__(self, get_response):
            self.get_response = get_response

        def __call__(self, request):
            # Extrair correlação do request
            context = extract_correlation_from_request(request)
            if not context.is_empty():
                set_correlation_context(context)

            response = self.get_response(request)

            # Limpar contexto após processamento
            clear_correlation_context()

            return response

    return CorrelationMiddleware