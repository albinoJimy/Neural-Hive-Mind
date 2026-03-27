"""Main entry point for Architect Agent service"""
import asyncio
import signal
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn

from src.config.settings import get_settings
from src.observability.metrics import init_metrics
from src.api.router import api_router

logger = structlog.get_logger(__name__)
shutdown_event = asyncio.Event()


def configure_logging():
    """Configure structured logging"""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def handle_signal(signum, frame):
    """Handle shutdown signals"""
    logger.info("shutdown_signal_received", signal=signum)
    shutdown_event.set()


@asynccontextmanager
async def lifespan(app):
    """Gerencia ciclo de vida da aplicacao."""
    settings = get_settings()
    logger.info(
        "starting_architect_agent",
        service=settings.service.service_name,
        version=settings.service.version,
        environment=settings.service.environment
    )

    # TODO: Iniciar Kafka consumer (background) - Task 7
    # TODO: Iniciar conexoes MongoDB - Task 6

    yield

    logger.info("shutting_down_architect_agent")
    # TODO: Cleanup resources


def create_app():
    """Create and configure FastAPI application"""
    settings = get_settings()

    app = FastAPI(
        title="Architect Agent",
        description="Sistema de arquitetura de software - planejamento e validacao",
        version=settings.service.version,
        lifespan=lifespan
    )

    # Incluir rotas
    app.include_router(api_router, prefix="/api/v1")

    # Health checks
    @app.get("/health/live")
    async def liveness():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def readiness():
        return {"status": "ready"}

    # Inicializar metricas
    init_metrics(app)

    return app


# Import FastAPI after function definition to avoid circular dependency
from fastapi import FastAPI

app = create_app()


async def main():
    """Main entry point"""
    settings = get_settings()

    # Configure logging
    configure_logging()

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start HTTP server
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.service.http_port,
        log_config=None,  # Use structlog instead
        access_log=False
    )

    server = uvicorn.Server(config)

    # Run server with shutdown handling
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        logger.info("architect_agent_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
