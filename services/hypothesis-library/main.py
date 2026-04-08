"""Hypothesis Library - Biblioteca Persistente de Hipóteses."""

import asyncio
import signal
import sys

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neural_hive_observability import init_observability

from src.api import api_router, health_handler, metrics_handler, root_handler
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import get_settings
from src.repositories.hypothesis_repository import HypothesisRepository
from src.repositories.version_repository import HypothesisVersionRepository
from src.services.hypothesis_service import HypothesisService
from src.services.versioning_service import VersioningService

logger = structlog.get_logger()

# Global instances
mongodb_client: MongoDBClient | None = None
hypothesis_repository: HypothesisRepository | None = None
version_repository: HypothesisVersionRepository | None = None
versioning_service: VersioningService | None = None
hypothesis_service: HypothesisService | None = None

app: FastAPI | None = None

# Shutdown event
shutdown_event = asyncio.Event()


def create_app() -> FastAPI:
    """Cria e configura aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="Hypothesis Library",
        description="Biblioteca Persistente de Hipóteses com Versionamento e Workflow",
        version=settings.service_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rotas
    app.include_router(api_router, prefix=settings.api_prefix)
    app.get("/")(root_handler)
    app.get("/health")(health_handler)
    app.get("/metrics")(metrics_handler)

    # Eventos de lifecycle
    @app.on_event("startup")
    async def startup():
        """Tarefas de inicialização."""
        global mongodb_client, hypothesis_repository, version_repository
        global versioning_service, hypothesis_service

        settings = get_settings()

        logger.info(
            "hypothesis_library_starting",
            service=settings.service_name,
            version=settings.service_version,
        )

        # Inicializar observabilidade
        init_observability(
            service_name="hypothesis-library",
            service_version=settings.service_version,
            neural_hive_component="hypothesis-library",
            neural_hive_layer="biblioteca",
            neural_hive_domain="continuous-improvement",
            otel_endpoint=settings.otel_endpoint,
        )
        logger.info("observability_initialized")

        # Conectar ao MongoDB
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.connect()

        # Inicializar repositories
        mongo_client_instance = mongodb_client.get_client()
        hypothesis_repository = await HypothesisRepository.get_repository(
            mongo_client_instance, settings
        )
        version_repository = await HypothesisVersionRepository.get_version_repository(
            mongo_client_instance, settings
        )

        # Inicializar services
        versioning_service = VersioningService(version_repository)
        hypothesis_service = HypothesisService(
            hypothesis_repository, versioning_service
        )

        logger.info("hypothesis_library_started")

    @app.on_event("shutdown")
    async def shutdown():
        """Tarefas de desligamento."""
        global mongodb_client

        logger.info("hypothesis_library_shutting_down")

        if mongodb_client:
            await mongodb_client.disconnect()

        logger.info("hypothesis_library_stopped")

    return app


async def main():
    """Ponto de entrada principal."""
    global app

    settings = get_settings()
    app = create_app()

    config = uvicorn.Config(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )

    server = uvicorn.Server(config)

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()
        server.should_exit = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
