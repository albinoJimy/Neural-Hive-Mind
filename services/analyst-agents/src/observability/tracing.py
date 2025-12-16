"""DEPRECATED: substituído por neural_hive_observability==1.1.0."""
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer

logger = structlog.get_logger()


def setup_tracing(settings):
    """Configurar OpenTelemetry tracing"""
    try:
        # Criar resource
        resource = Resource.create({
            'service.name': settings.OTEL_SERVICE_NAME,
            'service.version': settings.SERVICE_VERSION,
            'deployment.environment': settings.ENVIRONMENT
        })

        # Configurar tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Configurar OTLP exporter
        otlp_exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Registrar tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Instrumentar FastAPI
        FastAPIInstrumentor().instrument()

        # Instrumentar gRPC
        GrpcInstrumentorClient().instrument()
        GrpcInstrumentorServer().instrument()

        logger.info('opentelemetry_tracing_configured', endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)

    except Exception as e:
        logger.error('tracing_setup_failed', error=str(e))


def get_tracer():
    """Obter tracer global"""
    return trace.get_tracer(__name__)


def create_span(name: str, attributes: dict = None):
    """Criar span customizado"""
    tracer = get_tracer()
    span = tracer.start_span(name)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span
