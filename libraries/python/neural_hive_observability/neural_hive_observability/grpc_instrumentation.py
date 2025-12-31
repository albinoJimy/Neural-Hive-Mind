"""
Instrumentação gRPC para Neural Hive Observability.

Fornece interceptors para enriquecimento de spans, inicialização de instrumentação
automática e helpers para criação de servidores gRPC com contexto propagado.
"""

import logging
from concurrent import futures
from typing import Any, Dict, List, Optional, Tuple

import grpc
from opentelemetry import baggage, context, trace
from opentelemetry.baggage import set_baggage
from opentelemetry.context import attach, detach
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.propagate import extract
from opentelemetry.trace import Status, StatusCode

from .config import ObservabilityConfig

logger = logging.getLogger(__name__)


class NeuralHiveGrpcServerInterceptor(grpc.ServerInterceptor):
    """Interceptor gRPC para enriquecer spans com metadados Neural Hive."""

    def __init__(self, config: ObservabilityConfig):
        self.config = config

    def intercept_service(self, continuation, handler_call_details):
        metadata = self._metadata_to_dict(handler_call_details.invocation_metadata)
        otel_context = self._build_context_from_metadata(metadata)
        handler = continuation(handler_call_details)

        if handler is None:
            return None

        method_path = handler_call_details.method or ""

        if handler.unary_unary:
            return grpc.unary_unary_rpc_method_handler(
                self._wrap_unary_unary(handler, otel_context, metadata, method_path),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.unary_stream:
            return grpc.unary_stream_rpc_method_handler(
                self._wrap_unary_stream(handler, otel_context, metadata, method_path),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.stream_unary:
            return grpc.stream_unary_rpc_method_handler(
                self._wrap_stream_unary(handler, otel_context, metadata, method_path),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.stream_stream:
            return grpc.stream_stream_rpc_method_handler(
                self._wrap_stream_stream(handler, otel_context, metadata, method_path),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler

    def _wrap_unary_unary(self, handler, otel_context, metadata: Dict[str, str], method_path: str):
        def wrapper(request, servicer_context):
            token = attach(otel_context)
            span = trace.get_current_span()
            baggage_values = self._extract_baggage_values(metadata)

            try:
                self._apply_baggage(baggage_values)
                self._enrich_span(span, method_path, baggage_values)
                return handler.unary_unary(request, servicer_context)
            except Exception as exc:  # pragma: no cover - defensive
                if span:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                detach(token)

        return wrapper

    def _wrap_unary_stream(self, handler, otel_context, metadata: Dict[str, str], method_path: str):
        def wrapper(request, servicer_context):
            token = attach(otel_context)
            span = trace.get_current_span()
            baggage_values = self._extract_baggage_values(metadata)

            try:
                self._apply_baggage(baggage_values)
                self._enrich_span(span, method_path, baggage_values)
                return handler.unary_stream(request, servicer_context)
            except Exception as exc:  # pragma: no cover - defensive
                if span:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                detach(token)

        return wrapper

    def _wrap_stream_unary(self, handler, otel_context, metadata: Dict[str, str], method_path: str):
        def wrapper(request_iterator, servicer_context):
            token = attach(otel_context)
            span = trace.get_current_span()
            baggage_values = self._extract_baggage_values(metadata)

            try:
                self._apply_baggage(baggage_values)
                self._enrich_span(span, method_path, baggage_values)
                return handler.stream_unary(request_iterator, servicer_context)
            except Exception as exc:  # pragma: no cover - defensive
                if span:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                detach(token)

        return wrapper

    def _wrap_stream_stream(self, handler, otel_context, metadata: Dict[str, str], method_path: str):
        def wrapper(request_iterator, servicer_context):
            token = attach(otel_context)
            span = trace.get_current_span()
            baggage_values = self._extract_baggage_values(metadata)

            try:
                self._apply_baggage(baggage_values)
                self._enrich_span(span, method_path, baggage_values)
                return handler.stream_stream(request_iterator, servicer_context)
            except Exception as exc:  # pragma: no cover - defensive
                if span:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                detach(token)

        return wrapper

    def _metadata_to_dict(self, metadata: Optional[Tuple[Tuple[str, str], ...]]) -> Dict[str, str]:
        converted = {}
        if metadata:
            for key, value in metadata:
                if key and value:
                    converted[key.lower()] = value
        return converted

    def _build_context_from_metadata(self, metadata: Dict[str, str]):
        ctx = extract(metadata)
        baggage_ctx = ctx

        for header, attr in self._header_mapping().items():
            if header in metadata:
                baggage_ctx = set_baggage(f"neural.hive.{attr.replace('_', '.')}", metadata[header], baggage_ctx)

        return baggage_ctx

    def _extract_baggage_values(self, metadata: Dict[str, str]) -> Dict[str, str]:
        values = {}
        for header, attr in self._header_mapping().items():
            if header in metadata:
                values[attr] = metadata[header]
        return values

    def _apply_baggage(self, baggage_values: Dict[str, str]) -> None:
        for key, value in baggage_values.items():
            set_baggage(f"neural.hive.{key.replace('_', '.')}", value)

    def _parse_method(self, method_path: str) -> Tuple[str, str]:
        parts = method_path.lstrip("/").split("/")
        service = parts[0] if parts else "unknown"
        method = parts[1] if len(parts) > 1 else "unknown"
        return service, method

    def _enrich_span(self, span, method_path: str, baggage_values: Dict[str, str]) -> None:
        if not span or not span.get_span_context().is_valid:
            return

        service, method = self._parse_method(method_path)

        span.set_attribute("neural.hive.component", self.config.neural_hive_component)
        span.set_attribute("neural.hive.layer", self.config.neural_hive_layer)
        span.set_attribute("neural.hive.grpc.service", service)
        span.set_attribute("neural.hive.grpc.method", method)

        if self.config.neural_hive_domain:
            span.set_attribute("neural.hive.domain", self.config.neural_hive_domain)

        for key, value in baggage_values.items():
            span.set_attribute(f"neural.hive.{key.replace('_', '.')}", value)

    @staticmethod
    def _header_mapping() -> Dict[str, str]:
        return {
            "x-neural-hive-intent-id": "intent.id",
            "x-neural-hive-plan-id": "plan.id",
            "x-neural-hive-user-id": "user.id",
            "x-neural-hive-correlation-id": "correlation.id",
        }


def init_grpc_instrumentation(config: ObservabilityConfig) -> NeuralHiveGrpcServerInterceptor:
    """
    Inicializa instrumentação gRPC para clientes e servidores.

    Args:
        config: Configuração de observabilidade

    Returns:
        Interceptor customizado configurado
    """
    GrpcInstrumentorServer().instrument()
    GrpcInstrumentorClient().instrument()

    logger.info("OpenTelemetry gRPC instrumentors enabled")
    return NeuralHiveGrpcServerInterceptor(config)


def create_instrumented_grpc_server(
    config: ObservabilityConfig,
    max_workers: int = 10,
    interceptors: Optional[List[grpc.ServerInterceptor]] = None
) -> grpc.Server:
    """
    Cria servidor gRPC com interceptors padrão Neural Hive.

    Args:
        config: Configuração de observabilidade
        max_workers: Número máximo de workers
        interceptors: Lista adicional de interceptors

    Returns:
        Instância configurada de servidor gRPC
    """
    base_interceptors = interceptors or []
    base_interceptors.insert(0, NeuralHiveGrpcServerInterceptor(config))

    options = [
        ("grpc.max_receive_message_length", 50 * 1024 * 1024),
        ("grpc.max_send_message_length", 50 * 1024 * 1024),
        ("grpc.keepalive_time_ms", 30000),
        ("grpc.keepalive_timeout_ms", 10000),
    ]

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        interceptors=base_interceptors,
        options=options
    )

    return server


def create_instrumented_async_grpc_server(
    config: ObservabilityConfig,
    interceptors: Optional[List[grpc.aio.ServerInterceptor]] = None
) -> grpc.aio.Server:
    """
    Cria servidor gRPC assíncrono com interceptors padrão Neural Hive.

    Args:
        config: Configuração de observabilidade
        interceptors: Lista adicional de interceptors

    Returns:
        Instância configurada de servidor gRPC assíncrono
    """
    options = [
        ("grpc.max_receive_message_length", 50 * 1024 * 1024),
        ("grpc.max_send_message_length", 50 * 1024 * 1024),
        ("grpc.keepalive_time_ms", 30000),
        ("grpc.keepalive_timeout_ms", 10000),
    ]

    all_interceptors = list(interceptors) if interceptors else []

    server = grpc.aio.server(
        interceptors=all_interceptors,
        options=options
    )

    return server


def instrument_grpc_channel(
    channel: grpc.Channel,
    service_name: str = "",
    target_service: str = ""
) -> grpc.Channel:
    """
    Instrumenta um canal gRPC cliente com tracing OpenTelemetry.

    Esta função é um wrapper que garante que o canal está instrumentado
    para propagação de contexto. A instrumentação real é feita pelo
    GrpcInstrumentorClient inicializado em init_grpc_instrumentation.

    Args:
        channel: Canal gRPC a ser instrumentado
        service_name: Nome do serviço de origem (deprecated, mantido para compatibilidade)
        target_service: Nome do serviço de destino (para logging/debugging)

    Returns:
        O mesmo canal (já instrumentado globalmente pelo GrpcInstrumentorClient)
    """
    logger.debug(
        f"instrument_grpc_channel: {service_name or 'unknown'} -> {target_service or 'unknown'}"
    )
    # O canal já está instrumentado globalmente pelo GrpcInstrumentorClient
    # Esta função serve como ponto de extensão para customizações futuras
    return channel


def extract_grpc_context(servicer_context: grpc.ServicerContext) -> Tuple[Dict[str, str], Optional[Any]]:
    """
    Extrai contexto e baggage de metadados gRPC.

    Args:
        servicer_context: Contexto do serviço gRPC

    Returns:
        Tuple contendo:
            - Dicionário com valores extraídos dos headers Neural Hive
            - Token genérico para detach do contexto (pode ser de qualquer tipo
              retornado por context.attach, ou None se o attach falhar)
    """
    metadata = {}
    for key, value in servicer_context.invocation_metadata() or []:
        if key and value:
            metadata[key.lower()] = value

    ctx = extract(metadata)
    token = None
    try:
        token = attach(ctx)
    except Exception:
        token = None

    extracted = {}
    header_mapping = {
        "x-neural-hive-intent-id": "intent_id",
        "x-neural-hive-plan-id": "plan_id",
        "x-neural-hive-user-id": "user_id",
        "x-neural-hive-correlation-id": "correlation_id",
    }

    for header_name, baggage_key in header_mapping.items():
        if header_name in metadata:
            extracted[baggage_key] = metadata[header_name]
            set_baggage(f"neural.hive.{baggage_key.replace('_', '.')}", metadata[header_name])

    return extracted, token
