"""
Explainability API - Neural Hive-Mind

API RESTful para consulta de explicações de decisões, planos e opiniões.
Integrado com ledger de explicabilidade no MongoDB.
"""

import os
import structlog
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

# Inicializar observabilidade
from neural_hive_observability import init_observability

logger = structlog.get_logger(__name__)

# Inicializar FastAPI
app = FastAPI(
    title="Explainability API",
    description="API de consulta de explicações do Neural Hive-Mind",
    version="1.0.0"
)

# MongoDB client (global)
mongo_client: Optional[AsyncIOMotorClient] = None
db = None

# Métricas Prometheus
explainability_queries = Counter(
    'neural_hive_explainability_queries_total',
    'Total de consultas de explicabilidade',
    ['query_type', 'status']
)
explainability_query_duration = Histogram(
    'neural_hive_explainability_query_duration_seconds',
    'Duração de consultas de explicabilidade',
    ['query_type']
)


@app.on_event('startup')
async def startup_event():
    """Inicialização do serviço."""
    global mongo_client, db

    # Inicializar observabilidade
    init_observability(service_name='explainability-api')

    logger.info("starting_explainability_api", version="1.0.0")

    # Conectar ao MongoDB
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://mongodb:27017')
    mongo_client = AsyncIOMotorClient(mongo_uri)
    db = mongo_client['neural_hive']

    logger.info("mongodb_connected", uri=mongo_uri)


@app.on_event('shutdown')
async def shutdown_event():
    """Encerramento do serviço."""
    global mongo_client

    logger.info("shutting_down_explainability_api")

    if mongo_client:
        mongo_client.close()
        logger.info("mongodb_connection_closed")


@app.get('/health')
async def health_check():
    """Health check."""
    return {'status': 'healthy', 'service': 'explainability-api', 'timestamp': datetime.utcnow().isoformat()}


@app.get('/ready')
async def readiness_check():
    """Readiness check - verifica conectividade com MongoDB."""
    global mongo_client

    if not mongo_client:
        raise HTTPException(status_code=503, detail="MongoDB client not initialized")

    try:
        await mongo_client.admin.command('ping')
        return {'status': 'ready', 'mongodb': 'connected'}
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"MongoDB not ready: {str(e)}")


@app.get('/metrics')
async def metrics():
    """Métricas Prometheus."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get('/api/v1/explainability/{token}')
async def get_explainability_by_token(token: str):
    """Consulta explicação por token."""
    global db

    with explainability_query_duration.labels(query_type='by_token').time():
        try:
            explanation = await db.explainability_ledger.find_one({'explainability_token': token})

            if not explanation:
                explainability_queries.labels(query_type='by_token', status='not_found').inc()
                raise HTTPException(status_code=404, detail=f"Explanation not found for token: {token}")

            # Remover _id do MongoDB (não serializável)
            explanation.pop('_id', None)

            explainability_queries.labels(query_type='by_token', status='success').inc()

            logger.info("explainability_query_success", token=token, method=explanation.get('method'))

            return explanation

        except HTTPException:
            raise
        except Exception as e:
            explainability_queries.labels(query_type='by_token', status='error').inc()
            logger.error("explainability_query_error", token=token, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get('/api/v1/explainability/by-plan/{plan_id}')
async def get_explainability_by_plan(plan_id: str):
    """Consulta explicações de um plano."""
    global db

    with explainability_query_duration.labels(query_type='by_plan').time():
        try:
            explanations = await db.explainability_ledger.find({'plan_id': plan_id}).to_list(length=100)

            if not explanations:
                explainability_queries.labels(query_type='by_plan', status='not_found').inc()
                return {'plan_id': plan_id, 'explanations': []}

            # Remover _id do MongoDB
            for exp in explanations:
                exp.pop('_id', None)

            explainability_queries.labels(query_type='by_plan', status='success').inc()

            logger.info("explainability_query_success", plan_id=plan_id, count=len(explanations))

            return {'plan_id': plan_id, 'explanations': explanations, 'count': len(explanations)}

        except Exception as e:
            explainability_queries.labels(query_type='by_plan', status='error').inc()
            logger.error("explainability_query_error", plan_id=plan_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get('/api/v1/explainability/by-decision/{decision_id}')
async def get_explainability_by_decision(decision_id: str):
    """Consulta explicações de uma decisão."""
    global db

    with explainability_query_duration.labels(query_type='by_decision').time():
        try:
            explanations = await db.explainability_ledger.find({'decision_id': decision_id}).to_list(length=100)

            if not explanations:
                explainability_queries.labels(query_type='by_decision', status='not_found').inc()
                return {'decision_id': decision_id, 'explanations': []}

            # Remover _id do MongoDB
            for exp in explanations:
                exp.pop('_id', None)

            explainability_queries.labels(query_type='by_decision', status='success').inc()

            logger.info("explainability_query_success", decision_id=decision_id, count=len(explanations))

            return {'decision_id': decision_id, 'explanations': explanations, 'count': len(explanations)}

        except Exception as e:
            explainability_queries.labels(query_type='by_decision', status='error').inc()
            logger.error("explainability_query_error", decision_id=decision_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get('/api/v1/explainability/stats')
async def get_explainability_stats(
    start_date: Optional[str] = Query(None, description="Data de início (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data de fim (YYYY-MM-DD)")
):
    """Estatísticas de explicabilidade."""
    global db

    with explainability_query_duration.labels(query_type='stats').time():
        try:
            pipeline = []

            # Filtro de data (opcional)
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter['$gte'] = datetime.fromisoformat(start_date)
                if end_date:
                    date_filter['$lte'] = datetime.fromisoformat(end_date)
                pipeline.append({'$match': {'generated_at': date_filter}})

            # Agregação por método
            pipeline.append({
                '$group': {
                    '_id': '$method',
                    'count': {'$sum': 1}
                }
            })

            method_stats = await db.explainability_ledger.aggregate(pipeline).to_list(length=100)

            # Total de explicações
            total = await db.explainability_ledger.count_documents({})

            explainability_queries.labels(query_type='stats', status='success').inc()

            logger.info("explainability_stats_query_success", total=total)

            return {
                'total_explanations': total,
                'by_method': {item['_id']: item['count'] for item in method_stats},
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            explainability_queries.labels(query_type='stats', status='error').inc()
            logger.error("explainability_stats_query_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global de exceções."""
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={'error': 'Internal server error', 'detail': str(exc)}
    )
