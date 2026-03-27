import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from prometheus_client import make_asgi_app

from src.config.settings import settings
from src.api import api_router
from src.observability.middleware import MetricsMiddleware
from src.observability.metrics import get_metrics_text


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_tracing() -> None:
    if not settings.otel_exporter_otlp_endpoint:
        return
    provider = TracerProvider()
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware de métricas
    app.add_middleware(MetricsMiddleware)

    app.include_router(api_router, prefix="/api/v1")

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


configure_logging()
configure_tracing()

app = create_app()
logger = structlog.get_logger()


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("software_engineering_pipeline_starting", port=settings.api_port)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("software_engineering_pipeline_shutting_down")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": settings.app_name}


@app.get("/metrics")
async def metrics() -> Response:
    """Endpoint de métricas Prometheus customizadas."""
    metrics_text = get_metrics_text()
    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
