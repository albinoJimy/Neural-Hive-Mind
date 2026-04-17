"""Main application for Doc Ingestion service."""

import asyncio
import signal
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from src.api.routers.documents import router as documents_router
from src.api.routers.parsing import router as parsing_router

# Service Registry client
from src.clients.service_registry_client import DocIngestionServiceRegistryClient
from src.config.settings import get_settings
from src.db.mongodb import get_mongodb_client
from src.producers.doc_producer import DocProducer

logger = structlog.get_logger(__name__)

settings = get_settings()

# Global instances
_mongodb_client = None
_registry_client = None
_shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager para iniciar/parar componentes."""
    global _mongodb_client, _registry_client

    # Startup
    logger.info("starting_doc_ingestion_service")

    # Inicializar MongoDB Client
    try:
        _mongodb_client = await get_mongodb_client()
        if await _mongodb_client.ping():
            logger.info("mongodb_connected_successfully")
        else:
            logger.warning("mongodb_ping_failed")
    except Exception as e:
        logger.error("mongodb_init_error", error=str(e))
        # Continue sem MongoDB para desenvolvimento

    # Inicializar Kafka Producer
    try:
        from src.dependencies import set_doc_producer

        kafka_producer = DocProducer()
        await kafka_producer.start()
        set_doc_producer(kafka_producer)
        logger.info("kafka_producer_started")
    except Exception as e:
        logger.error("kafka_producer_init_error", error=str(e))
        # Continue sem Kafka para desenvolvimento

    # Registrar no Service Registry
    try:
        _registry_client = DocIngestionServiceRegistryClient()
        if await _registry_client.initialize():
            agent_id = await _registry_client.register(
                capabilities=[
                    "pdf_parsing",
                    "word_parsing",
                    "visio_parsing",
                    "postman_parsing",
                    "entity_extraction",
                    "document_upload",
                    "document_storage",
                ],
                metadata={
                    "kafka_producer": "doc_producer",
                    "api_version": settings.api_version,
                    "max_file_size_mb": str(settings.max_file_size_mb),
                },
            )
            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="doc-ingestion",
                    agent_id=agent_id,
                    port=settings.port,
                )
                await _registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = _registry_client
    except Exception as e:
        logger.warning(
            "service_registry_registration_failed",
            error=str(e),
            message="Service continuing without Service Registry",
        )

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        _shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    # Shutdown
    logger.info("shutting_down_doc_ingestion_service")

    # Fechar Service Registry
    if _registry_client:
        try:
            await _registry_client.close()
        except Exception as e:
            logger.error("service_registry_shutdown_error", error=str(e))

    # Fechar Kafka Producer
    from src.dependencies import clear_doc_producer, get_doc_producer

    kafka_producer = get_doc_producer()
    if kafka_producer:
        try:
            await kafka_producer.stop()
        except Exception as e:
            logger.error("kafka_producer_shutdown_error", error=str(e))
        finally:
            clear_doc_producer()

    # Fechar MongoDB Client
    if _mongodb_client:
        try:
            await _mongodb_client.disconnect()
        except Exception as e:
            logger.error("mongodb_shutdown_error", error=str(e))

    logger.info("doc_ingestion_service_stopped")


# Criar aplicação FastAPI com lifespan
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Doc Ingestion API for Neural Hive-Mind - Parse legacy documentation",
    lifespan=lifespan,
)


# Incluir routers
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(parsing_router, prefix=settings.api_prefix)


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
    from src.dependencies import get_doc_producer

    mongodb_connected = False
    if _mongodb_client:
        try:
            mongodb_connected = await _mongodb_client.ping()
        except Exception:
            pass

    kafka_producer = get_doc_producer()

    return {
        "service": settings.service_name,
        "status": "healthy",
        "version": settings.service_version,
        "kafka_connected": kafka_producer is not None,
        "mongodb_connected": mongodb_connected,
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

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
