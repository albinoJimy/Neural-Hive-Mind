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
from src.config.settings import get_settings

# Service Registry client - placeholder for future implementation
# from src.clients.service_registry_client import DocIngestionServiceRegistryClient
# from neural_hive_integration.proto_stubs import service_registry_pb2

logger = structlog.get_logger(__name__)

settings = get_settings()

# Global instances
_mongodb_client = None
_kafka_producer = None
_registry_client = None
_shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager para iniciar/parar componentes."""
    global _mongodb_client, _kafka_producer, _registry_client

    # Startup
    logger.info("starting_doc_ingestion_service")

    # TODO: Inicializar MongoDB Client
    # from src.db.mongodb import MongoDBClient
    # _mongodb_client = MongoDBClient()
    # await _mongodb_client.connect()

    # TODO: Inicializar Kafka Producer
    # from src.producers.entity_producer import EntityProducer
    # _kafka_producer = EntityProducer()
    # await _kafka_producer.start()

    # TODO: Registrar no Service Registry
    # _registry_client = DocIngestionServiceRegistryClient(settings)
    # if await _registry_client.initialize():
    #     agent_id = await _registry_client.register(
    #         capabilities=[
    #             "pdf_parsing",
    #             "word_parsing",
    #             "visio_parsing",
    #             "postman_parsing",
    #             "entity_extraction",
    #         ],
    #         metadata={
    #             "kafka_producer": "entity_producer",
    #             "version": "1.0.0",
    #         },
    #     )
    #     if agent_id:
    #         logger.info(
    #             "service_registered_successfully",
    #             service="doc-ingestion",
    #             agent_id=agent_id,
    #             port=8018,
    #         )
    #         await _registry_client.start_heartbeat(interval_seconds=30)
    #         app.state.registry_client = _registry_client

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        _shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    # Shutdown
    logger.info("shutting_down_doc_ingestion_service")

    # TODO: Fechar Service Registry
    # if _registry_client:
    #     await _registry_client.close()

    # TODO: Fechar Kafka Producer
    # if _kafka_producer:
    #     await _kafka_producer.stop()

    # TODO: Fechar MongoDB Client
    # if _mongodb_client:
    #     await _mongodb_client.disconnect()

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
    return {
        "service": settings.service_name,
        "status": "healthy",
        "version": settings.service_version,
        "kafka_connected": _kafka_producer is not None,
        "mongodb_connected": _mongodb_client is not None,
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
