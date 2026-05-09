"""Aplicação FastAPI do Unified Gateway."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from src.api.routers.health import health_router
from src.api.routers.request import request_router
from src.api.routers.status import status_router
from src.api.routers.stream import stream_router
from src.config.settings import get_settings
from src.middleware import JWTAuthMiddleware, RateLimitMiddleware, TracingMiddleware

settings = get_settings()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    logger.info(
        "starting_unified_gateway",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        port=settings.PORT,
    )

    # Inicializar observabilidade (tracing)
    try:
        from neural_hive_observability import init_observability

        init_observability(
            service_name="unified-gateway",
            service_version=settings.VERSION,
            neural_hive_component="gateway",
            neural_hive_layer="gateway",
        )
        logger.info("observability_initialized")
    except ImportError:
        logger.warning("neural_hive_observability not available - tracing disabled")
    except Exception as e:
        logger.warning("observability_init_failed", error=str(e))

    yield

    # Shutdown
    logger.info("shutting_down_unified_gateway")


# Criar aplicação FastAPI
app = FastAPI(
    title="Unified Gateway - Neural Hive-Mind",
    description="Gateway unificado para roteamento de requisições com autenticação e tracing",
    version=settings.VERSION,
    lifespan=lifespan,
)

# Adicionar SecurityHeadersMiddleware (se disponível)
try:
    from neural_hive_security import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("security_headers_middleware_added")
except ImportError:
    logger.warning("neural_hive_security not available - security headers disabled")


# Adicionar TracingMiddleware (INV-11: traceparent propagation)
app.add_middleware(TracingMiddleware, service_name="unified-gateway")

# Adicionar JWTAuthMiddleware (INV-7: user_id, tenant_id extraction)
app.add_middleware(
    JWTAuthMiddleware,
    exclude_paths=[
        "/",  # service descriptor — match exacto, não prefix
        "/health",
        "/health/ready",
        "/health/live",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    ],
    require_auth=settings.JWT_AUTH_REQUIRED,
)

# Adicionar RateLimitMiddleware (INV-8: rate limiting por tenant)
app.add_middleware(
    RateLimitMiddleware,
    exclude_paths=[
        "/health",
        "/health/ready",
        "/health/live",
        "/metrics",
    ],
    enabled=True,
)

# Adicionar endpoint /metrics para Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routers
app.include_router(health_router, tags=["health"])
app.include_router(request_router, tags=["request"])
app.include_router(status_router, tags=["status"])
app.include_router(stream_router, tags=["stream"])


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
        "service": "unified-gateway",
        "version": settings.VERSION,
        "status": "operational",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }
