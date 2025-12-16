import grpc
import pytest
from types import SimpleNamespace
from typing import List, Tuple

from opentelemetry import trace
from opentelemetry.context import detach
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.grpc_instrumentation import (
    NeuralHiveGrpcServerInterceptor,
    create_instrumented_grpc_server,
    extract_grpc_context,
)
from neural_hive_observability.tracing import trace_grpc_method


class DummyContext:
    def __init__(self, metadata: List[Tuple[str, str]]):
        self._metadata = metadata

    def invocation_metadata(self):
        return self._metadata


class DummyDetails:
    def __init__(self, metadata, method="/package.Service/Method"):
        self.invocation_metadata = metadata
        self.method = method


def _setup_tracer():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)
    return tracer, exporter


def test_interceptor_enriches_span():
    config = ObservabilityConfig(
        service_name="grpc-service",
        neural_hive_component="specialist",
        neural_hive_layer="cognicao",
    )
    interceptor = NeuralHiveGrpcServerInterceptor(config)

    metadata = (
        ("x-neural-hive-intent-id", "intent-1"),
        ("x-neural-hive-plan-id", "plan-9"),
    )
    call_details = DummyDetails(metadata)

    handler = grpc.unary_unary_rpc_method_handler(lambda req, ctx: "ok")
    wrapped = interceptor.intercept_service(lambda details: handler, call_details)

    tracer, exporter = _setup_tracer()
    with tracer.start_as_current_span("server-span") as span:
        wrapped.unary_unary(None, DummyContext(metadata))

    span_data = span.to_span_data()
    assert span_data.attributes["neural.hive.intent.id"] == "intent-1"
    assert span_data.attributes["neural.hive.plan.id"] == "plan-9"
    assert span_data.attributes["neural.hive.grpc.method"] == "Method"
    assert span_data.attributes["neural.hive.grpc.service"] == "package.Service"


def test_create_instrumented_grpc_server_adds_interceptor():
    config = ObservabilityConfig(
        service_name="grpc-service",
        neural_hive_component="specialist",
        neural_hive_layer="cognicao",
    )
    server = create_instrumented_grpc_server(config)
    assert isinstance(server, grpc.Server)
    assert any(isinstance(i, NeuralHiveGrpcServerInterceptor) for i in server._interceptors)


def test_extract_grpc_context_sets_baggage():
    metadata = [
        ("x-neural-hive-intent-id", "intent-ctx"),
        ("x-neural-hive-plan-id", "plan-ctx"),
        ("x-neural-hive-user-id", "user-ctx"),
    ]
    ctx = DummyContext(metadata)

    extracted, token = extract_grpc_context(ctx)

    try:
        assert extracted["intent_id"] == "intent-ctx"
        assert extracted["plan_id"] == "plan-ctx"
        assert extracted["user_id"] == "user-ctx"
    finally:
        if token:
            detach(token)


def test_trace_grpc_method_creates_span_with_metadata(monkeypatch):
    tracer, exporter = _setup_tracer()

    # patch tracer global in tracing module
    import neural_hive_observability.tracing as tracing

    tracing._tracer = tracer
    tracing._config = ObservabilityConfig(
        service_name="grpc-service",
        neural_hive_component="specialist",
        neural_hive_layer="cognicao",
    )

    class Servicer:
        @trace_grpc_method(include_request=True, include_response=True)
        def Ping(self, request, context):
            return {"message": "pong"}

    metadata = [("x-neural-hive-intent-id", "intent-meta")]
    servicer = Servicer()
    servicer.Ping(SimpleNamespace(), DummyContext(metadata))

    spans = exporter.get_finished_spans()
    assert spans
    span = spans[-1]
    assert span.name == "specialist.grpc.Ping"
    assert span.attributes["neural.hive.intent.id"] == "intent-meta"
    assert span.attributes["neural.hive.grpc.method"] == "Ping"
