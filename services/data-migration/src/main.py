"""Main application for Data Migration service."""

import asyncio
import signal
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from src.clients.service_registry_client import DataMigrationServiceRegistryClient
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

# Global instances
_registry_client: DataMigrationServiceRegistryClient | None = None
_shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager para iniciar/parar componentes."""
    global _registry_client

    # Startup
    logger.info("starting_data_migration_service")

    # Registrar no Service Registry
    try:
        _registry_client = DataMigrationServiceRegistryClient(
            service_name="data-migration", agent_type=11  # DATA_MIGRATION
        )

        if await _registry_client.initialize():
            agent_id = await _registry_client.register(
                capabilities=[
                    "schema_mapping",
                    "batch_migration",
                    "cdc_migration",
                    "data_validation",
                    "rollback",
                ],
                metadata={
                    "version": "1.0.0",
                    "batch_size": str(settings.batch_size),
                    "max_parallel_migrations": str(settings.max_parallel_migrations),
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="data-migration",
                    agent_id=agent_id,
                    port=8019,
                )
                await _registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = _registry_client
            else:
                logger.error("service_registration_failed", service="data-migration")
        else:
            logger.error("service_registry_init_failed", service="data-migration")
    except Exception as e:
        logger.error("service_registry_exception", error=str(e))

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        _shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    yield

    # Shutdown
    logger.info("shutting_down_data_migration_service")
    if _registry_client:
        try:
            await _registry_client.close()
            logger.info("service_deregistered", service="data-migration")
        except Exception as e:
            logger.error("service_deregister_failed", error=str(e))
    logger.info("data_migration_service_stopped")


# Criar aplicação FastAPI com lifespan
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Data Migration API for Neural Hive-Mind Fluxo H",
    lifespan=lifespan,
)


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
        "registry_connected": _registry_client is not None,
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
