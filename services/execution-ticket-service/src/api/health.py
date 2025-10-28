"""Health check endpoints."""
from fastapi import APIRouter, Response, status
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ..database import get_postgres_client, get_mongodb_client

router = APIRouter()


@router.get('/health')
async def health():
    """Liveness probe - verifica se serviço está rodando."""
    return {
        'status': 'healthy',
        'service': 'execution-ticket-service',
        'version': '1.0.0'
    }


@router.get('/ready')
async def ready():
    """Readiness probe - verifica dependências."""
    checks = {}

    # Verificar PostgreSQL
    try:
        postgres_client = await get_postgres_client()
        checks['postgres'] = await postgres_client.health_check()
    except Exception as e:
        checks['postgres'] = False

    # Verificar MongoDB
    try:
        mongodb_client = await get_mongodb_client()
        checks['mongodb'] = await mongodb_client.health_check()
    except Exception as e:
        checks['mongodb'] = False

    all_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return Response(
        content={'status': 'ready' if all_healthy else 'not_ready', 'checks': checks},
        status_code=status_code
    )


@router.get('/metrics')
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
