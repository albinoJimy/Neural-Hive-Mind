"""Main application for Requirements Engineering service."""

import asyncio
import signal
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from src.api.routers.api_design import router as api_design_router
from src.api.routers.requirements import router as requirements_router
from src.api.routers.ui_ux_design import router as ui_ux_design_router
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.config.settings import get_settings
from src.consumers.cognitive_plan_consumer import CognitivePlanConsumer
from src.dependencies import set_requirements_engineer
from src.producers.requirements_producer import RequirementsProducer
from src.proto import service_registry_pb2
from src.services.requirements_engineer import RequirementsEngineer

logger = structlog.get_logger(__name__)

settings = get_settings()

# Global instances
_kafka_consumer: CognitivePlanConsumer | None = None
_kafka_producer: RequirementsProducer | None = None
_consumer_task: asyncio.Task | None = None
_registry_client: EngineeringServiceRegistryClient | None = None

shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager para iniciar/parar componentes."""
    global _kafka_consumer, _kafka_producer, _consumer_task, _registry_client

    # Startup
    logger.info("starting_requirements_engineering_service")

    # Inicializar RequirementsEngineer
    requirements_engineer = RequirementsEngineer()
    set_requirements_engineer(requirements_engineer)

    # Inicializar Kafka Producer
    _kafka_producer = RequirementsProducer()
    await _kafka_producer.start()

    # Inicializar Kafka Consumer
    _kafka_consumer = CognitivePlanConsumer(
        requirements_engineer=requirements_engineer,
        producer=_kafka_producer,
    )
    await _kafka_consumer.start()

    # Iniciar consumer em background
    _consumer_task = asyncio.create_task(_kafka_consumer.consume())

    # Registrar no Service Registry
    try:
        _registry_client = EngineeringServiceRegistryClient(
            service_name="requirements-engineering",
            agent_type=service_registry_pb2.REQUIREMENTS_ENGINEERING,
        )

        if await _registry_client.initialize():
            agent_id = await _registry_client.register(
                capabilities=[
                    "requirements_generation",
                    "user_stories",
                    "acceptance_criteria",
                    "data_model_design",
                    "api_design",
                    "ui_ux_design",
                ],
                metadata={
                    "kafka_consumer": "cognitive_plan_consumer",
                    "kafka_producer": "requirements_producer",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="requirements-engineering",
                    agent_id=agent_id,
                    port=8010,
                )
                # Iniciar heartbeat a cada 30s
                await _registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = _registry_client
            else:
                logger.error("service_registration_failed", service="requirements-engineering")
        else:
            logger.error("service_registry_init_failed", service="requirements-engineering")
    except Exception as e:
        logger.error("service_registry_exception", error=str(e))

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    # Shutdown
    logger.info("shutting_down_requirements_engineering_service")
    if _registry_client:
        try:
            await _registry_client.close()
            logger.info("service_deregistered", service="requirements-engineering")
        except Exception as e:
            logger.error("service_deregister_failed", error=str(e))
    if _kafka_consumer:
        await _kafka_consumer.stop()
    if _kafka_producer:
        await _kafka_producer.stop()
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
    logger.info("requirements_engineering_service_stopped")


# Criar aplicação FastAPI com lifespan
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Requirements Engineering API for Neural Hive-Mind",
    lifespan=lifespan,
)


# Incluir routers
app.include_router(requirements_router, prefix=settings.api_prefix)
app.include_router(api_design_router, prefix=settings.api_prefix)
app.include_router(ui_ux_design_router, prefix=settings.api_prefix)


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

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
