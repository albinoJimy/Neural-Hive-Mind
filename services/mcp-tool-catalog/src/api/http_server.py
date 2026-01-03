"""FastAPI HTTP server for MCP Tool Catalog."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.config import get_settings


def create_app(lifespan: Optional[asynccontextmanager] = None) -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="MCP Tool Catalog Service",
        description="Intelligent tool selection via genetic algorithms for Neural Hive-Mind",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OpenTelemetry instrumentation
    FastAPIInstrumentor.instrument_app(app)

    # Health endpoints
    @app.get("/health")
    async def health():
        """Health check endpoint - verifica se o serviço está vivo."""
        # Health check básico - apenas verifica se o processo está rodando
        # Não verifica dependências para evitar falsos positivos
        return {
            "status": "healthy",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
        }

    @app.get("/ready")
    async def ready():
        """Readiness check - verifica se o serviço está pronto para receber tráfego."""
        import structlog
        from src.main import service

        logger = structlog.get_logger()

        checks = {
            "mongodb": False,
            "redis": False,
            "kafka_consumer": False,
            "kafka_producer": False,
            "service_registry": False,
        }

        try:
            # Verificar MongoDB
            if service and service.mongodb_client and service.mongodb_client.client:
                await service.mongodb_client.client.admin.command("ping")
                checks["mongodb"] = True
        except Exception as e:
            logger.warning("mongodb_health_check_failed", error=str(e))

        try:
            # Verificar Redis
            if service and service.redis_client and service.redis_client.client:
                await service.redis_client.client.ping()
                checks["redis"] = True
        except Exception as e:
            logger.warning("redis_health_check_failed", error=str(e))

        # Kafka e Service Registry são considerados prontos se foram inicializados
        if service:
            checks["kafka_consumer"] = service.kafka_consumer is not None
            checks["kafka_producer"] = service.kafka_producer is not None
            checks["service_registry"] = service.service_registry_client is not None

        # Serviço está pronto se MongoDB e Redis estão saudáveis
        # Kafka e Service Registry são opcionais para readiness
        is_ready = checks["mongodb"] and checks["redis"]

        return {
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
        }

    # Include routers
    from src.api.tools import router as tools_router
    from src.api.selections import router as selections_router
    app.include_router(tools_router)
    app.include_router(selections_router)

    return app
