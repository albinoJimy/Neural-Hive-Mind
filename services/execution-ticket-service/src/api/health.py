"""Health check endpoints."""
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ..database import get_postgres_client, get_mongodb_client
from ..config import get_settings

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
    """Readiness probe - verifica dependências críticas."""
    checks = {}

    # Verificar PostgreSQL
    try:
        postgres_client = await get_postgres_client()
        checks['postgresql'] = await postgres_client.health_check()
    except Exception:
        checks['postgresql'] = False

    # Verificar MongoDB
    try:
        mongodb_client = await get_mongodb_client()
        checks['mongodb'] = await mongodb_client.health_check()
    except Exception:
        checks['mongodb'] = False

    all_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={'status': 'ready' if all_healthy else 'not_ready', 'checks': checks}
    )


@router.get('/grpc-health')
async def grpc_health(request: Request):
    """
    Verifica saúde do servidor gRPC.
    
    Retorna status do servidor gRPC e health servicer registrado.
    """
    settings = get_settings()
    
    grpc_server_running = (
        hasattr(request.app.state, 'grpc_server') 
        and request.app.state.grpc_server is not None
    )
    health_servicer_registered = (
        hasattr(request.app.state, 'grpc_health_servicer') 
        and request.app.state.grpc_health_servicer is not None
    )
    
    is_healthy = grpc_server_running and health_servicer_registered
    
    response_data = {
        'status': 'healthy' if is_healthy else 'unhealthy',
        'grpc_port': settings.grpc_port,
        'grpc_server_running': grpc_server_running,
        'health_servicer_registered': health_servicer_registered
    }
    
    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(status_code=status_code, content=response_data)


@router.get('/metrics')
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
