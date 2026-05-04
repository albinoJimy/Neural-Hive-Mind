"""Aplicação FastAPI do PII Service."""

import asyncio
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.api.routers import health, pii
from src.config.settings import get_settings
from src.middleware import JWTAuthMiddleware
from src.services.audit import get_audit_logger
from src.services.grpc_server import serve_grpc

settings = get_settings()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    logger.info(
        "starting_pii_service",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        port=settings.PORT,
        grpc_port=settings.GRPC_PORT,
    )

    # Inicializar observabilidade (tracing)
    try:
        from neural_hive_observability import init_observability

        init_observability(
            service_name="pii-service",
            service_version=settings.VERSION,
            neural_hive_component="pii",
            neural_hive_layer="services",
        )
        logger.info("observability_initialized")
    except ImportError:
        logger.warning("neural_hive_observability not available - tracing disabled")
    except Exception as e:
        logger.warning("observability_init_failed", error=str(e))

    # Inicializar Audit Logger (INV-13)
    try:
        audit_logger = get_audit_logger()
        await audit_logger.initialize()
        logger.info("audit_logger_initialized")
    except Exception as e:
        logger.warning("audit_logger_init_failed", error=str(e))

    # Iniciar servidor gRPC em background
    grpc_task = None
    if settings.GRPC_PORT > 0:
        grpc_task = asyncio.create_task(serve_grpc(settings.GRPC_PORT))
        logger.info("grpc_server_started", port=settings.GRPC_PORT)

    yield

    # Shutdown
    logger.info("shutting_down_pii_service")

    # Fechar audit logger
    try:
        audit_logger = get_audit_logger()
        await audit_logger.close()
    except Exception:
        pass

    # Cancelar tarefa gRPC
    if grpc_task:
        grpc_task.cancel()
        try:
            await grpc_task
        except Exception:
            pass


# Criar aplicação FastAPI
app = FastAPI(
    title="PII Service - Neural Hive-Mind",
    description="Serviço centralizado de detecção e mascaramento de PII com gRPC+REST",
    version=settings.VERSION,
    lifespan=lifespan,
)

# Adicionar JWTAuthMiddleware (R-P4: JWT auth required)
# Nota: Em produção, require_auth=True
app.add_middleware(
    JWTAuthMiddleware,
    exclude_paths=[
        "/health",
        "/health/ready",
        "/health/live",
        "/api/v1/pii/capabilities",
        "/docs",
        "/openapi.json",
        "/redoc",
    ],
    require_auth=settings.JWT_AUTH_REQUIRED,
)

# Routers
app.include_router(health.health_router, tags=["health"])
app.include_router(pii.pii_router, tags=["PII"])


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global de exceções."""
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An internal error occurred"},
    )


# Root endpoint
@app.get("/")
async def root():
    """Endpoint raiz com informações do serviço."""
    return {
        "service": "pii-service",
        "version": settings.VERSION,
        "status": "operational",
        "docs": "/docs",
        "health": "/health",
        "capabilities": "/api/v1/pii/capabilities",
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        workers=1,
        log_level=settings.LOG_LEVEL.lower(),
    )
