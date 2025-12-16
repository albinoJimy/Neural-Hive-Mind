from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import structlog

from ..config import get_settings
from ..integration.generation_webhook import router as webhook_router, webhook_handler, WebhookHandler
from .pipeline_api import router as pipeline_router

logger = structlog.get_logger()
settings = get_settings()


def create_app() -> FastAPI:
    """Cria aplicação FastAPI"""

    app = FastAPI(
        title='Code Forge',
        description='Neural Code Generation Pipeline',
        version='1.0.0'
    )

    # Include webhook router
    app.include_router(webhook_router)
    app.include_router(pipeline_router)

    @app.get('/health')
    async def health():
        """Health check (liveness)"""
        return {'status': 'healthy', 'service': 'code-forge'}

    @app.get('/ready')
    async def ready():
        """Readiness check"""
        # TODO: Verificar conectividade com dependências
        return {'status': 'ready'}

    @app.get('/metrics')
    async def metrics():
        """Métricas Prometheus"""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

    return app
