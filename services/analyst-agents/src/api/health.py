from fastapi import APIRouter, Request
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.get('/health')
async def health_check():
    """Health check básico"""
    return {'status': 'healthy', 'service': 'analyst-agents'}


@router.get('/ready')
async def readiness_check(request: Request):
    """Readiness check - verifica dependências"""
    app_state = request.app.state.app_state
    dependencies = {}

    try:
        # Verificar MongoDB
        if app_state.mongodb_client and app_state.mongodb_client.client:
            dependencies['mongodb'] = 'connected'
        else:
            dependencies['mongodb'] = 'disconnected'

        # Verificar Redis
        if app_state.redis_client and app_state.redis_client.client:
            await app_state.redis_client.client.ping()
            dependencies['redis'] = 'connected'
        else:
            dependencies['redis'] = 'disconnected'

        # Verificar Neo4j
        if app_state.neo4j_client and app_state.neo4j_client.driver:
            dependencies['neo4j'] = 'connected'
        else:
            dependencies['neo4j'] = 'disconnected'

        # Verificar ClickHouse
        if app_state.clickhouse_client and app_state.clickhouse_client.client:
            dependencies['clickhouse'] = 'connected'
        else:
            dependencies['clickhouse'] = 'disconnected'

        # Verificar Elasticsearch
        if app_state.elasticsearch_client and app_state.elasticsearch_client.client:
            dependencies['elasticsearch'] = 'connected'
        else:
            dependencies['elasticsearch'] = 'disconnected'

        # Verificar Prometheus
        if app_state.prometheus_client and app_state.prometheus_client.client:
            dependencies['prometheus'] = 'connected'
        else:
            dependencies['prometheus'] = 'disconnected'

        ready = all(status == 'connected' for status in dependencies.values())

        return {
            'ready': ready,
            'dependencies': dependencies,
            'timestamp': int(__import__('time').time() * 1000)
        }

    except Exception as e:
        logger.error('readiness_check_failed', error=str(e))
        return {
            'ready': False,
            'dependencies': dependencies,
            'error': str(e)
        }


@router.get('/live')
async def liveness_check():
    """Liveness check - verifica se serviço está responsivo"""
    return {'alive': True}
