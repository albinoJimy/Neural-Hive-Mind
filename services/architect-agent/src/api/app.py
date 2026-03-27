"""Aplicação FastAPI para Architect Agent."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import architecture, validation
from src.config.settings import get_settings
import structlog

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Cria e configura aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="Architect Agent",
        description="Sistema de arquitetura de software - planejamento e validacao",
        version=settings.service.version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: configurar via settings
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(architecture.router)
    app.include_router(validation.router)

    # Health checks
    @app.get("/health/live")
    async def liveness():
        """Health check - liveness."""
        return {"status": "alive"}

    @app.get("/health/ready")
    async def readiness():
        """Health check - readiness."""
        return {"status": "ready"}

    logger.info(
        "app_created",
        service=settings.service.service_name,
        version=settings.service.version,
    )

    return app


# App instance para uvicorn
app = create_app()
