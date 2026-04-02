import structlog
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from neural_hive_api.health import HealthRouter

from ..config import get_settings
from ..integration.generation_webhook import (
    router as webhook_router,
)
from .generation_api import router as generation_router
from .pipeline_api import router as pipeline_router

logger = structlog.get_logger()
settings = get_settings()

# Health Router (neural_hive_api)
health_router = HealthRouter("code-forge")


def create_app() -> FastAPI:
    """Cria aplicação FastAPI"""

    app = FastAPI(
        title="Code Forge", description="Neural Code Generation Pipeline", version="1.0.0"
    )

    # Include health router from neural_hive_api
    health_router.add_route(app)

    # Include webhook router
    app.include_router(webhook_router)
    app.include_router(pipeline_router)
    app.include_router(generation_router)

    @app.get("/metrics")
    async def metrics():
        """Métricas Prometheus"""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
