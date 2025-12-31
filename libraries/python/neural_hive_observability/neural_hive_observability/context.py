"""
Context management para Neural Hive-Mind.

Gerencia propagação de contexto distribuído incluindo intent_id, plan_id,
user_id e outros identificadores através de chamadas HTTP, Kafka e RPC.
"""

import logging
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple, Union
import threading

from opentelemetry import trace, baggage, context
from opentelemetry.propagate import inject, extract
from opentelemetry.baggage import set_baggage, get_baggage
from opentelemetry.context import attach, detach

from .config import ObservabilityConfig

logger = logging.getLogger(__name__)


def extract_context_from_headers(headers: Dict[str, str]):
    """
    Extrai contexto OpenTelemetry de headers e define no contexto atual.

    Função duplicada de tracing.py para evitar import circular.

    Args:
        headers: Headers com contexto

    Returns:
        Token de contexto para ser usado em detach() pelo chamador, ou None
    """
    from opentelemetry.propagate import extract as otel_extract

    token = None
    try:
        ctx = otel_extract(headers)
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


class ContextManager:
    """Gerenciador de contexto distribuído."""

    def __init__(self, config: ObservabilityConfig):
        """
        Inicializa context manager.

        Args:
            config: Configuração de observabilidade
        """
        self.config = config
        self._local = threading.local()

    @contextmanager
    def correlation_context(
        self,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        user_id: Optional[str] = None,
        domain: Optional[str] = None,
        channel: Optional[str] = None,
        **additional_context
    ):
        """
        Context manager para correlação distribuída.

        Args:
            intent_id: ID da intenção
            plan_id: ID do plano
            user_id: ID do usuário
            domain: Domínio específico
            channel: Canal de origem
            **additional_context: Contexto adicional
        """
        # Preparar baggage items
        baggage_items = {}
        if intent_id:
            baggage_items["neural.hive.intent.id"] = intent_id
        if plan_id:
            baggage_items["neural.hive.plan.id"] = plan_id
        if user_id:
            baggage_items["neural.hive.user.id"] = user_id
        if domain:
            baggage_items["neural.hive.domain"] = domain
        if channel:
            baggage_items["neural.hive.channel"] = channel

        # Adicionar contexto adicional
        for key, value in additional_context.items():
            if value is not None:
                baggage_items[f"neural.hive.{key}"] = str(value)

        # Salvar contexto atual
        current_context = context.get_current()
        tokens = []

        try:
            # Definir baggage items
            for key, value in baggage_items.items():
                ctx = set_baggage(key, value, current_context)
                token = attach(ctx)
                tokens.append(token)

            yield self
        finally:
            # Restaurar contexto
            for token in reversed(tokens):
                detach(token)

    def get_current_correlation(self) -> Dict[str, Any]:
        """
        Retorna contexto de correlação atual.

        Returns:
            Dicionário com contexto atual
        """
        correlation = {}

        # Extrair de baggage
        current_baggage = get_baggage()
        if current_baggage:
            for key, value in current_baggage.items():
                if key.startswith("neural.hive."):
                    context_key = key.replace("neural.hive.", "").replace(".", "_")
                    correlation[context_key] = value

        # Adicionar trace/span IDs
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            correlation["trace_id"] = format(span.get_span_context().trace_id, "032x")
            correlation["span_id"] = format(span.get_span_context().span_id, "016x")

        return correlation

    def inject_http_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Injeta contexto em headers HTTP.

        Args:
            headers: Headers HTTP existentes

        Returns:
            Headers com contexto injetado
        """
        # Copiar headers existentes
        new_headers = headers.copy()

        # Injetar contexto OpenTelemetry
        inject(new_headers)

        # Adicionar headers customizados Neural Hive
        correlation = self.get_current_correlation()
        if "intent_id" in correlation:
            new_headers["X-Neural-Hive-Intent-Id"] = correlation["intent_id"]
        if "plan_id" in correlation:
            new_headers["X-Neural-Hive-Plan-Id"] = correlation["plan_id"]
        if "user_id" in correlation:
            new_headers["X-Neural-Hive-User-Id"] = correlation["user_id"]
        if "domain" in correlation:
            new_headers["X-Neural-Hive-Domain"] = correlation["domain"]
        if "channel" in correlation:
            new_headers["X-Neural-Hive-Channel"] = correlation["channel"]

        # Adicionar identificação do serviço
        new_headers["X-Neural-Hive-Source"] = self.config.service_name
        new_headers["X-Neural-Hive-Component"] = self.config.neural_hive_component

        return new_headers

    def extract_http_headers(self, headers: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        Extrai contexto de headers HTTP.

        Args:
            headers: Headers HTTP

        Returns:
            Contexto extraído ou None
        """
        try:
            # Extrair contexto OpenTelemetry
            ctx = extract(headers)
            token = attach(ctx)

            # Extrair headers customizados
            extracted_context = {}

            header_mappings = {
                "X-Neural-Hive-Intent-Id": "intent_id",
                "X-Neural-Hive-Plan-Id": "plan_id",
                "X-Neural-Hive-User-Id": "user_id",
                "X-Neural-Hive-Domain": "domain",
                "X-Neural-Hive-Channel": "channel",
            }

            for header_name, context_key in header_mappings.items():
                if header_name in headers:
                    extracted_context[context_key] = headers[header_name]
                    # Também definir no baggage
                    set_baggage(f"neural.hive.{context_key}", headers[header_name])

            return extracted_context if extracted_context else None

        except Exception as e:
            logger.warning(f"Erro ao extrair contexto de headers HTTP: {e}")
            return None

    def inject_kafka_headers(self, headers: Dict[str, bytes]) -> Dict[str, bytes]:
        """
        Injeta contexto em headers Kafka.

        Args:
            headers: Headers Kafka existentes

        Returns:
            Headers com contexto injetado
        """
        # Converter para formato string temporariamente
        str_headers = {k: v.decode() if isinstance(v, bytes) else str(v) for k, v in headers.items()}

        # Injetar contexto
        injected_headers = self.inject_http_headers(str_headers)

        # Converter de volta para bytes
        kafka_headers = {}
        for k, v in injected_headers.items():
            kafka_headers[k] = v.encode() if isinstance(v, str) else v

        return kafka_headers

    def extract_kafka_headers(self, headers: Dict[str, bytes]) -> Optional[Dict[str, str]]:
        """
        Extrai contexto de headers Kafka.

        Args:
            headers: Headers Kafka

        Returns:
            Contexto extraído ou None
        """
        try:
            # Converter bytes para string
            str_headers = {}
            for k, v in headers.items():
                if isinstance(v, bytes):
                    str_headers[k] = v.decode()
                else:
                    str_headers[k] = str(v)

            return self.extract_http_headers(str_headers)

        except Exception as e:
            logger.warning(f"Erro ao extrair contexto de headers Kafka: {e}")
            return None

    def create_child_context(
        self,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        operation: Optional[str] = None,
        **additional_context
    ) -> "ChildContext":
        """
        Cria contexto filho para operação específica.

        Args:
            intent_id: ID da intenção
            plan_id: ID do plano
            operation: Nome da operação
            **additional_context: Contexto adicional

        Returns:
            Context manager para operação filho
        """
        return ChildContext(
            parent_manager=self,
            intent_id=intent_id,
            plan_id=plan_id,
            operation=operation,
            additional_context=additional_context
        )

    def get_intent_id(self) -> Optional[str]:
        """Retorna intent_id do contexto atual."""
        baggage_data = get_baggage()
        return baggage_data.get("neural.hive.intent.id") if baggage_data else None

    def get_plan_id(self) -> Optional[str]:
        """Retorna plan_id do contexto atual."""
        baggage_data = get_baggage()
        return baggage_data.get("neural.hive.plan.id") if baggage_data else None

    def get_user_id(self) -> Optional[str]:
        """Retorna user_id do contexto atual."""
        baggage_data = get_baggage()
        return baggage_data.get("neural.hive.user.id") if baggage_data else None

    def get_domain(self) -> Optional[str]:
        """Retorna domain do contexto atual."""
        baggage_data = get_baggage()
        return baggage_data.get("neural.hive.domain") if baggage_data else None

    def get_channel(self) -> Optional[str]:
        """Retorna channel do contexto atual."""
        baggage_data = get_baggage()
        return baggage_data.get("neural.hive.channel") if baggage_data else None


class ChildContext:
    """Context manager para operação filho."""

    def __init__(
        self,
        parent_manager: ContextManager,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        operation: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ):
        """
        Inicializa contexto filho.

        Args:
            parent_manager: Gerenciador pai
            intent_id: ID da intenção
            plan_id: ID do plano
            operation: Nome da operação
            additional_context: Contexto adicional
        """
        self.parent_manager = parent_manager
        self.intent_id = intent_id or parent_manager.get_intent_id()
        self.plan_id = plan_id or parent_manager.get_plan_id()
        self.operation = operation
        self.additional_context = additional_context or {}
        self._context_token = None

    def __enter__(self):
        """Entra no contexto."""
        # Criar novo contexto baseado no atual
        current_context = context.get_current()

        # Definir baggage items para o contexto filho
        if self.intent_id:
            current_context = set_baggage("neural.hive.intent.id", self.intent_id, current_context)
        if self.plan_id:
            current_context = set_baggage("neural.hive.plan.id", self.plan_id, current_context)
        if self.operation:
            current_context = set_baggage("neural.hive.operation", self.operation, current_context)

        # Adicionar contexto adicional
        for key, value in self.additional_context.items():
            if value is not None:
                current_context = set_baggage(f"neural.hive.{key}", str(value), current_context)

        # Ativar contexto
        self._context_token = attach(current_context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sai do contexto."""
        if self._context_token:
            detach(self._context_token)

    def get_correlation(self) -> Dict[str, Any]:
        """Retorna correlação do contexto filho."""
        return self.parent_manager.get_current_correlation()


# Funções utilitárias para compatibilidade e uso direto

def extract_context_from_metadata(metadata: Dict[str, str]) -> Optional[Dict[str, str]]:
    """
    Extrai contexto Neural Hive de metadados gRPC ou HTTP.

    Args:
        metadata: Dicionário de metadados (gRPC invocation_metadata ou HTTP headers)

    Returns:
        Dicionário com intent_id, plan_id, user_id, etc. ou None se não encontrado
    """
    if not metadata:
        return None

    extracted = {}

    # Mapeamentos de headers/metadados para chaves de contexto
    mappings = {
        # Headers HTTP padrão Neural Hive
        "x-neural-hive-intent-id": "intent_id",
        "x-neural-hive-plan-id": "plan_id",
        "x-neural-hive-user-id": "user_id",
        "x-neural-hive-domain": "domain",
        "x-neural-hive-channel": "channel",
        "x-neural-hive-correlation-id": "correlation_id",
        # Versões alternativas (case-insensitive lookup)
        "X-Neural-Hive-Intent-Id": "intent_id",
        "X-Neural-Hive-Plan-Id": "plan_id",
        "X-Neural-Hive-User-Id": "user_id",
        "X-Neural-Hive-Domain": "domain",
        "X-Neural-Hive-Channel": "channel",
        "X-Neural-Hive-Correlation-Id": "correlation_id",
        # gRPC metadata keys (lowercase)
        "intent-id": "intent_id",
        "plan-id": "plan_id",
        "user-id": "user_id",
        "x-tenant-id": "tenant_id",
        "x-request-id": "request_id",
    }

    for meta_key, context_key in mappings.items():
        if meta_key in metadata and metadata[meta_key]:
            extracted[context_key] = metadata[meta_key]

    # Também verificar baggage W3C se disponível
    if "baggage" in metadata:
        try:
            baggage_str = metadata["baggage"]
            for item in baggage_str.split(","):
                if "=" in item:
                    key, value = item.strip().split("=", 1)
                    if key.startswith("neural.hive."):
                        context_key = key.replace("neural.hive.", "").replace(".", "_")
                        extracted[context_key] = value
        except Exception as e:
            logger.debug(f"Failed to parse baggage header: {e}")

    return extracted if extracted else None


def set_baggage_value(key: str, value: str) -> None:
    """
    Define um valor no baggage OpenTelemetry.

    Wrapper conveniente para set_baggage que automaticamente
    attach ao contexto atual.

    Args:
        key: Chave do baggage (ex: 'neural.hive.intent.id')
        value: Valor a ser definido
    """
    if not key or not value:
        return

    try:
        current_ctx = context.get_current()
        new_ctx = set_baggage(key, value, current_ctx)
        attach(new_ctx)
    except Exception as e:
        logger.debug(f"Failed to set baggage {key}: {e}")


def inject_context_to_metadata(
    metadata: Optional[List[Tuple[str, str]]] = None
) -> List[Tuple[str, str]]:
    """
    Injeta contexto Neural Hive em metadados gRPC.

    Esta função adiciona headers de contexto OpenTelemetry e Neural Hive
    aos metadados gRPC para propagação distribuída.

    Args:
        metadata: Lista de tuplas (key, value) com metadados existentes

    Returns:
        Lista de metadados com contexto injetado
    """
    result = list(metadata) if metadata else []

    # Converter para dicionário para injeção OpenTelemetry
    headers_dict: Dict[str, str] = {}
    inject(headers_dict)

    # Adicionar headers OpenTelemetry ao resultado
    for key, value in headers_dict.items():
        result.append((key, value))

    # Adicionar contexto Neural Hive do baggage atual
    current_baggage = get_baggage()
    if current_baggage:
        header_mapping = {
            "neural.hive.intent.id": "x-neural-hive-intent-id",
            "neural.hive.plan.id": "x-neural-hive-plan-id",
            "neural.hive.user.id": "x-neural-hive-user-id",
            "neural.hive.domain": "x-neural-hive-domain",
            "neural.hive.channel": "x-neural-hive-channel",
            "neural.hive.correlation.id": "x-neural-hive-correlation-id",
        }

        for baggage_key, header_name in header_mapping.items():
            value = current_baggage.get(baggage_key)
            if value:
                result.append((header_name, value))

    return result


# Alias para compatibilidade - extract_context_from_headers é o mesmo que extract_context_from_metadata
# Muitos serviços usam esse nome alternativo
extract_context_from_headers = extract_context_from_metadata


# Re-export set_baggage from opentelemetry for convenience
# This allows: from neural_hive_observability.context import set_baggage
__all__ = [
    "ContextManager",
    "ChildContext",
    "extract_context_from_metadata",
    "extract_context_from_headers",  # Alias para compatibilidade
    "set_baggage_value",
    "set_baggage",  # Re-exported from opentelemetry
    "inject_context_to_metadata",
]