"""Main application for Documentation Generation service."""

import asyncio
import signal
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from src.api.routers.documentation import router as docs_router
from src.config.settings import get_settings
from src.consumers.architecture_plan_consumer import ArchitecturePlanConsumer
from src.producers.docs_producer import DocumentationProducer
from src.services.code_doc_generator import CodeDocGenerator
from src.services.readme_generator import ReadmeGenerator

logger = structlog.get_logger(__name__)

settings = get_settings()

# Global instances
_readme_generator: ReadmeGenerator | None = None
_code_doc_generator: CodeDocGenerator | None = None
_kafka_consumer: ArchitecturePlanConsumer | None = None
_kafka_producer: DocumentationProducer | None = None
_consumer_task: asyncio.Task | None = None

shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager para iniciar/parar componentes."""
    global _readme_generator, _code_doc_generator, _kafka_consumer, _kafka_producer, _consumer_task

    # Startup
    logger.info("starting_documentation_generation_service")

    # Inicializar geradores
    _readme_generator = ReadmeGenerator()
    _code_doc_generator = CodeDocGenerator()

    # Inicializar Kafka Producer
    _kafka_producer = DocumentationProducer()
    await _kafka_producer.start()

    # Inicializar Kafka Consumer
    _kafka_consumer = ArchitecturePlanConsumer(
        readme_generator=_readme_generator,
        code_doc_generator=_code_doc_generator,
        producer=_kafka_producer,
    )
    await _kafka_consumer.start()

    # Iniciar consumer em background
    _consumer_task = asyncio.create_task(_kafka_consumer.consume())

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    # Shutdown
    logger.info("shutting_down_documentation_generation_service")
    if _kafka_consumer:
        await _kafka_consumer.stop()
    if _kafka_producer:
        await _kafka_producer.stop()
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
    logger.info("documentation_generation_service_stopped")


# Criar aplicação FastAPI com lifespan
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Documentation Generation API for Neural Hive-Mind",
    lifespan=lifespan,
)

# Incluir routers
app.include_router(docs_router, prefix=settings.api_prefix)


# Middleware
@app.middleware("http")
async def log_requests(request, call_next):
    """Middleware para logging de requests."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(
        "request_started", method=request.method, path=request.url.path, request_id=request_id
    )
    response = await call_next(request)
    logger.info("request_completed", status_code=response.status_code, request_id=request_id)
    return response


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": settings.service_name,
        "status": "healthy",
        "version": settings.service_version,
        "kafka_connected": _kafka_producer is not None,
    }


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global de exceções."""
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
