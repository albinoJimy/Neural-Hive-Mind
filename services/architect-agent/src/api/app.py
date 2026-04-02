"""Aplicação FastAPI para Architect Agent."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neural_hive_api.health import HealthRouter
from src.api.routers import architecture, validation
from src.config.settings import get_settings

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

    # CORS - usa configuração segura por ambiente via neural_hive_security
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(architecture.router)
    app.include_router(validation.router)

    # Health checks - usa HealthRouter padronizado do neural_hive_api
    health_router = HealthRouter(settings.service.service_name)
    health_router.add_route(app)

    logger.info(
        "app_created",
        service=settings.service.service_name,
        version=settings.service.version,
    )

    return app


# App instance para uvicorn
app = create_app()
