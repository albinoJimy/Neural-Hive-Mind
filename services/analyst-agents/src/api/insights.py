from fastapi import APIRouter, Request, HTTPException, Query
from typing import List, Optional
import structlog
import time

from ..models.query_request import InsightQueryRequest, InsightQueryResponse, QueryType

logger = structlog.get_logger()
router = APIRouter()


@router.get('/insights')
async def list_insights(
    request: Request,
    insight_type: Optional[str] = None,
    priority: Optional[str] = None,
    start_timestamp: Optional[int] = None,
    end_timestamp: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """Listar insights com filtros"""
    try:
        app_state = request.app.state.app_state
        mongodb_client = app_state.mongodb_client

        filters = {}
        if insight_type:
            filters['insight_type'] = insight_type
        if priority:
            filters['priority'] = priority
        if start_timestamp and end_timestamp:
            filters['created_at'] = {'$gte': start_timestamp, '$lte': end_timestamp}

        results = await mongodb_client.query_insights(filters, limit=limit, skip=offset)

        return {
            'insights': results,
            'count': len(results),
            'limit': limit,
            'offset': offset
        }

    except Exception as e:
        logger.error('list_insights_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/insights/{insight_id}')
async def get_insight(insight_id: str, request: Request):
    """Obter insight por ID"""
    try:
        app_state = request.app.state.app_state
        mongodb_client = app_state.mongodb_client
        redis_client = app_state.redis_client

        # Verificar cache
        cached = await redis_client.get_cached_insight(insight_id)
        if cached:
            await redis_client.increment_insight_access_count(insight_id)
            return {'insight': cached, 'cached': True}

        # Buscar no MongoDB
        insight = await mongodb_client.get_insight_by_id(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail='Insight não encontrado')

        # Cachear
        from ..models.insight import AnalystInsight
        insight_obj = AnalystInsight(**insight)
        await redis_client.cache_insight(insight_obj)
        await redis_client.increment_insight_access_count(insight_id)

        return {'insight': insight, 'cached': False}

    except HTTPException:
        raise
    except Exception as e:
        logger.error('get_insight_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/insights/by-entity/{entity_type}/{entity_id}')
async def get_insights_by_entity(entity_type: str, entity_id: str, request: Request, limit: int = 100):
    """Obter insights relacionados a entidade"""
    try:
        app_state = request.app.state.app_state
        mongodb_client = app_state.mongodb_client

        results = await mongodb_client.get_insights_by_entity(entity_type, entity_id, limit=limit)

        return {
            'insights': results,
            'count': len(results),
            'entity_type': entity_type,
            'entity_id': entity_id
        }

    except Exception as e:
        logger.error('get_insights_by_entity_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/insights/by-tags')
async def get_insights_by_tags(request: Request, tags: str = Query(...), limit: int = 100):
    """Obter insights por tags"""
    try:
        app_state = request.app.state.app_state
        mongodb_client = app_state.mongodb_client

        tag_list = [t.strip() for t in tags.split(',')]
        results = await mongodb_client.get_insights_by_tags(tag_list, limit=limit)

        return {
            'insights': results,
            'count': len(results),
            'tags': tag_list
        }

    except Exception as e:
        logger.error('get_insights_by_tags_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/insights/query')
async def query_insights(query_request: InsightQueryRequest, request: Request):
    """Consulta avançada de insights"""
    try:
        start_time = time.time()
        app_state = request.app.state.app_state
        mongodb_client = app_state.mongodb_client

        # Construir filtros baseado no tipo de consulta
        filters = {}

        if query_request.query_type == QueryType.BY_ID and query_request.insight_id:
            result = await mongodb_client.get_insight_by_id(query_request.insight_id)
            results = [result] if result else []

        elif query_request.query_type == QueryType.BY_TYPE and query_request.insight_type:
            results = await mongodb_client.get_insights_by_type(
                query_request.insight_type,
                limit=query_request.limit
            )

        elif query_request.query_type == QueryType.BY_PRIORITY and query_request.priority:
            results = await mongodb_client.get_insights_by_priority(
                query_request.priority,
                limit=query_request.limit
            )

        elif query_request.query_type == QueryType.BY_TIME_RANGE:
            results = await mongodb_client.get_insights_by_time_range(
                query_request.start_timestamp,
                query_request.end_timestamp,
                limit=query_request.limit
            )

        elif query_request.query_type == QueryType.BY_ENTITY:
            results = await mongodb_client.get_insights_by_entity(
                query_request.entity_type,
                query_request.entity_id,
                limit=query_request.limit
            )

        elif query_request.query_type == QueryType.BY_TAG and query_request.tags:
            results = await mongodb_client.get_insights_by_tags(
                query_request.tags,
                limit=query_request.limit
            )

        else:
            results = []

        query_time = (time.time() - start_time) * 1000

        return InsightQueryResponse(
            insights=results,
            total_count=len(results),
            query_time_ms=query_time,
            cached=False
        )

    except Exception as e:
        logger.error('query_insights_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/insights/statistics')
async def get_insights_statistics(request: Request):
    """Estatísticas de insights"""
    try:
        app_state = request.app.state.app_state
        mongodb_client = app_state.mongodb_client

        # Contar por tipo
        insights_by_type = {}
        for insight_type in ['STRATEGIC', 'OPERATIONAL', 'PREDICTIVE', 'CAUSAL', 'ANOMALY']:
            results = await mongodb_client.get_insights_by_type(insight_type, limit=10000)
            insights_by_type[insight_type] = len(results)

        # Contar por prioridade
        insights_by_priority = {}
        for priority in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']:
            results = await mongodb_client.get_insights_by_priority(priority, limit=10000)
            insights_by_priority[priority] = len(results)

        return {
            'insights_by_type': insights_by_type,
            'insights_by_priority': insights_by_priority,
            'timestamp': int(time.time() * 1000)
        }

    except Exception as e:
        logger.error('get_insights_statistics_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
