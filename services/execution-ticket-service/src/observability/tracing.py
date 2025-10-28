"""Configuração OpenTelemetry tracing."""
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

logger = logging.getLogger(__name__)


def setup_tracing(app, settings):
    """
    Configura OpenTelemetry tracing para o serviço.

    Args:
        app: FastAPI application
        settings: TicketServiceSettings
    """
    # Criar resource
    resource = Resource.create({
        'service.name': settings.service_name,
        'service.version': settings.service_version,
        'deployment.environment': settings.environment
    })

    # Configurar provider
    provider = TracerProvider(resource=resource)

    # Configurar exporter OTLP
    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=True  # Usar TLS em produção
    )

    # Adicionar processor
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Registrar provider global
    trace.set_tracer_provider(provider)

    # Instrumentar FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Instrumentar SQLAlchemy
    SQLAlchemyInstrumentor().instrument()

    # Instrumentar aiohttp (webhooks)
    AioHttpClientInstrumentor().instrument()

    logger.info(f'OpenTelemetry tracing configured', endpoint=settings.otel_exporter_endpoint)
