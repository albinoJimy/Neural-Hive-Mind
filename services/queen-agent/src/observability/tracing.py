import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from ..config import Settings


logger = structlog.get_logger()


def setup_tracing(settings: Settings):
    """
    Configurar OpenTelemetry tracing

    Returns:
        Tracer configurado
    """
    try:
        # Criar resource com atributos do serviço
        resource = Resource.create({
            "service.name": settings.SERVICE_NAME,
            "service.version": settings.SERVICE_VERSION,
            "deployment.environment": settings.ENVIRONMENT
        })

        # Configurar TracerProvider
        provider = TracerProvider(resource=resource)

        # Configurar exporter OTLP para Jaeger
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_ENDPOINT,
            insecure=True  # TODO: Usar TLS em produção
        )

        # Adicionar BatchSpanProcessor
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Definir como global
        trace.set_tracer_provider(provider)

        # Instrumentar FastAPI automaticamente
        FastAPIInstrumentor().instrument()

        # Instrumentar httpx (para chamadas HTTP)
        HTTPXClientInstrumentor().instrument()

        logger.info("opentelemetry_tracing_initialized")

        # Retornar tracer
        return trace.get_tracer(settings.SERVICE_NAME, settings.SERVICE_VERSION)

    except Exception as e:
        logger.error("setup_tracing_failed", error=str(e))
        # Retornar tracer noop para não bloquear a aplicação
        return trace.get_tracer("noop")
