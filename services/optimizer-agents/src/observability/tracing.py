"""DEPRECATED: substituted by neural_hive_observability==1.1.0; keep only for temporary compatibility."""
from typing import Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased


def setup_tracing(settings):
    """Configure OpenTelemetry tracing."""
    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "service.namespace": "neural-hive-mind",
            "deployment.environment": settings.environment,
        }
    )

    # Create tracer provider with sampling
    sampler = TraceIdRatioBased(settings.jaeger_sampling_rate)
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)

    # Configure OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)

    # Add batch span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Set as global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument()

    # Instrument gRPC
    GrpcInstrumentorClient().instrument()
    GrpcInstrumentorServer().instrument()

    # Instrument httpx
    HTTPXClientInstrumentor().instrument()

    # Return tracer for manual instrumentation
    return trace.get_tracer(__name__)


def create_span(tracer, name: str, attributes: Optional[Dict[str, any]] = None):
    """Create a span with custom attributes."""
    span = tracer.start_span(name)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span


def add_span_attributes(span, attributes: Dict[str, any]):
    """Add attributes to an existing span."""
    for key, value in attributes.items():
        span.set_attribute(key, value)
