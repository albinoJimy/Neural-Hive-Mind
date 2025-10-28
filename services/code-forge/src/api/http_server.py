from fastapi import FastAPI, HTTPException
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import structlog

from ..config import get_settings
from ..integration.generation_webhook import router as webhook_router, webhook_handler, WebhookHandler

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

    @app.get('/api/v1/pipelines')
    async def list_pipelines(
        status: str = None,
        ticket_id: str = None,
        limit: int = 10,
        offset: int = 0
    ):
        """Lista pipelines"""
        # TODO: Implementar busca no PostgreSQL
        return {'pipelines': [], 'total': 0}

    @app.get('/api/v1/pipelines/{pipeline_id}')
    async def get_pipeline(pipeline_id: str):
        """Busca pipeline por ID"""
        # TODO: Implementar
        raise HTTPException(status_code=404, detail='Pipeline not found')

    @app.get('/api/v1/pipelines/{pipeline_id}/artifacts')
    async def list_artifacts(pipeline_id: str):
        """Lista artefatos de um pipeline"""
        # TODO: Implementar
        return {'artifacts': []}

    @app.get('/api/v1/pipelines/{pipeline_id}/logs')
    async def get_logs(pipeline_id: str):
        """Busca logs de pipeline"""
        # TODO: Implementar
        return {'logs': []}

    @app.post('/api/v1/pipelines/{pipeline_id}/retry')
    async def retry_pipeline(pipeline_id: str):
        """Retry de pipeline falhado"""
        # TODO: Implementar
        return {'status': 'retrying'}

    @app.get('/api/v1/templates')
    async def list_templates():
        """Lista templates disponíveis"""
        # TODO: Implementar
        return {'templates': []}

    @app.get('/api/v1/statistics')
    async def get_statistics():
        """Estatísticas agregadas"""
        # TODO: Implementar
        return {'success_rate': 0.0, 'avg_duration_ms': 0, 'total_pipelines': 0}

    return app
