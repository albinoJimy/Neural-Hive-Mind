from fastapi import APIRouter, Request
import structlog
import time

logger = structlog.get_logger()
router = APIRouter()


@router.get('/status')
async def get_status(request: Request):
    """Status geral do serviço"""
    try:
        from ..config import get_settings
        settings = get_settings()

        return {
            'service': settings.SERVICE_NAME,
            'version': settings.SERVICE_VERSION,
            'environment': settings.ENVIRONMENT,
            'status': 'running',
            'timestamp': int(time.time() * 1000)
        }

    except Exception as e:
        logger.error('get_status_failed', error=str(e))
        return {'status': 'error', 'error': str(e)}
