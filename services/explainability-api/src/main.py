"""
Explainability API - Neural Hive-Mind

API RESTful para consulta de explicações de decisões, planos e opiniões.
Integrado com ledger de explicabilidade no MongoDB.

GAPS-04 Enhanced Version:
- Explicações com campos hierárquicos
- SHAP values para feature attribution
- Quality scoring (completude, clareza, especificidade)
- Multi-formato (JSON, texto, HTML)
- Kafka integration para decisões de consenso
"""

import os
import asyncio
import structlog
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from pydantic import BaseModel

# Inicializar observabilidade
from neural_hive_observability import init_observability

# Serviços internos
from src.services.api_extensions import ExplainabilityAPIExtensions, setup_extensions
from src.services.shap_calculator import ShapCalculator
from src.services.quality_scorer import ExplanationQualityScorer
from src.services.reasoning_extractor import ReasoningExtractor
from src.consumers.consensus_decision_consumer import ConsensusDecisionConsumer
from src.producers.explanation_producer import ExplanationProducer

logger = structlog.get_logger(__name__)

# Configurações
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://mongodb:27017')
CONSUMER_GROUP_ID = os.getenv('CONSUMER_GROUP_ID', 'explainability-api-group')
ENABLE_KAFKA_CONSUMER = os.getenv('ENABLE_KAFKA_CONSUMER', 'true').lower() == 'true'
ENABLE_V3_API = os.getenv('ENABLE_V3_API', 'false').lower() == 'true'

# Globais
mongo_client: Optional[AsyncIOMotorClient] = None
db = None
shap_calculator: Optional[ShapCalculator] = None
quality_scorer: Optional[ExplanationQualityScorer] = None
reasoning_extractor: Optional[ReasoningExtractor] = None
api_extensions: Optional[ExplainabilityAPIExtensions] = None
explanation_producer: Optional[ExplanationProducer] = None
consensus_consumer: Optional[ConsensusDecisionConsumer] = None

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
explanations_generated = Counter(
    'neural_hive_explanations_generated_total',
    'Total de explicações geradas',
    ['format']
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia ciclo de vida da aplicação.
    """
    global mongo_client, db, shap_calculator, quality_scorer, reasoning_extractor
    global api_extensions, explanation_producer, consensus_consumer

    # ========== STARTUP ==========
    api_version = "3.0.0" if ENABLE_V3_API else "2.0.0"
    logger.info("starting_explainability_api", version=api_version, gaps04="enabled", v3_enabled=ENABLE_V3_API)

    # Inicializar observabilidade
    init_observability(service_name='explainability-api')

    # Conectar ao MongoDB
    mongo_client = AsyncIOMotorClient(MONGODB_URI)
    db = mongo_client['neural_hive']
    logger.info("mongodb_connected", uri=MONGODB_URI)

    # Inicializar V3 Router se habilitado
    global v3_router
    if ENABLE_V3_API:
        try:
            from src.api.routes.v3 import create_v3_router
            v3_router = create_v3_router(mongo_client)
            app.include_router(v3_router)
            logger.info("v3_router_initialized")
        except Exception as e:
            logger.warning("v3_router_init_failed", error=str(e))

    # Inicializar serviços de ML
    shap_calculator = ShapCalculator(n_background_samples=100)
    quality_scorer = ExplanationQualityScorer(mongodb_client=mongo_client)
    reasoning_extractor = ReasoningExtractor()

    logger.info("ml_services_initialized")

    # Inicializar API Extensions
    api_extensions = ExplainabilityAPIExtensions(
        mongodb_client=mongo_client,
        shap_calculator=shap_calculator,
        quality_scorer=quality_scorer,
        reasoning_extractor=reasoning_extractor
    )

    # Inicializar Kafka Producer
    try:
        explanation_producer = ExplanationProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            topic='consensus.explanations'
        )
        await explanation_producer.connect()
        logger.info("explanation_producer_connected")
    except Exception as e:
        logger.warning("explanation_producer_connection_failed", error=str(e))

    # Inicializar Kafka Consumer (se habilitado)
    if ENABLE_KAFKA_CONSUMER:
        try:
            consensus_consumer = ConsensusDecisionConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP_ID,
                explainability_service=api_extensions,
                explanation_producer=explanation_producer,
                input_topic='consensus.decision.created',
                output_topic='consensus.explanations'
            )
            await consensus_consumer.connect()
            await consensus_consumer.start_consuming()
            logger.info("consensus_consumer_started")
        except Exception as e:
            logger.warning("consensus_consumer_start_failed", error=str(e))

    logger.info("explainability_api_ready")

    yield

    # ========== SHUTDOWN ==========
    logger.info("shutting_down_explainability_api")

    # Parar consumer
    if consensus_consumer:
        try:
            await consensus_consumer.stop()
            logger.info("consensus_consumer_stopped")
        except Exception as e:
            logger.error("consensus_consumer_stop_error", error=str(e))

    # Desconectar producer
    if explanation_producer:
        try:
            await explanation_producer.disconnect()
            logger.info("explanation_producer_disconnected")
        except Exception as e:
            logger.error("explanation_producer_disconnect_error", error=str(e))

    # Fechar MongoDB
    if mongo_client:
        mongo_client.close()
        logger.info("mongodb_connection_closed")


# Inicializar FastAPI com lifespan
api_version = "3.0.0" if ENABLE_V3_API else "2.0.0"
api_description = "API de explicações do Neural Hive-Mind (GAPS-04 Enhanced)"
if ENABLE_V3_API:
    api_description += " com endpoints hierárquicos v3"

app = FastAPI(
    title="Explainability API",
    description=api_description,
    version=api_version,
    lifespan=lifespan
)

# ========== HEALTH ENDPOINTS ==========

@app.get('/health')
async def health_check():
    """Health check básico."""
    return {
        'status': 'healthy',
        'service': 'explainability-api',
        'version': '2.0.0',
        'timestamp': datetime.utcnow().isoformat()
    }


@app.get('/ready')
async def readiness_check():
    """Readiness check - verifica conectividade essencial."""
    global mongo_client, explanation_producer

    checks = {'mongodb': False, 'kafka_producer': False, 'api': True}

    if mongo_client:
        try:
            await mongo_client.admin.command('ping')
            checks['mongodb'] = True
        except Exception:
            pass

    # Kafka producer é opcional para readiness (pode falhar em alguns ambientes)
    if explanation_producer and explanation_producer.producer:
        checks['kafka_producer'] = True

    # API é ready se MongoDB estiver conectado (Kafka é opcional)
    all_ready = checks['mongodb'] and checks['api']
    status_code = 200 if all_ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            'status': 'ready' if all_ready else 'not_ready',
            'checks': checks,
            'note': 'kafka_producer is optional' if not checks['kafka_producer'] else None
        }
    )


@app.get('/metrics')
async def metrics():
    """Métricas Prometheus."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ========== LEGACY ENDPOINTS (Compatibilidade) ==========

@app.get('/api/v1/explainability/{token}')
async def get_explainability_by_token(token: str):
    """Consulta explicação por token (legado)."""
    global db

    with explainability_query_duration.labels(query_type='by_token').time():
        try:
            explanation = await db.explainability_ledger.find_one({'explainability_token': token})

            if not explanation:
                explainability_queries.labels(query_type='by_token', status='not_found').inc()
                raise HTTPException(status_code=404, detail=f"Explanation not found for token: {token}")

            explanation.pop('_id', None)
            explainability_queries.labels(query_type='by_token', status='success').inc()

            return explanation

        except HTTPException:
            raise
        except Exception as e:
            explainability_queries.labels(query_type='by_token', status='error').inc()
            logger.error("explainability_query_error", token=token, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ========== GAPS-04 EXTENDED ENDPOINTS ==========

class GenerateExplanationRequest(BaseModel):
    """Request para geração de explicação."""
    decision_id: str
    format: str = 'json'
    include_shap: bool = False
    include_reasoning_extraction: bool = False
    include_quality_score: bool = True
    specialist_votes: Optional[list] = None
    reasoning_text: Optional[str] = None
    final_decision: Optional[str] = None

    class Config:
        extra = 'allow'


@app.get('/api/v2/explainability/{decision_id}')
async def get_explanation_extended(decision_id: str):
    """
    Busca explicação extendida por decision_id (GAPS-04).

    Inclui campos hierárquicos, SHAP values e quality scores.
    """
    global api_extensions

    with explainability_query_duration.labels(query_type='extended').time():
        try:
            explanation = await api_extensions.get_explainability_by_decision_id(decision_id)

            if not explanation:
                explainability_queries.labels(query_type='extended', status='not_found').inc()
                raise HTTPException(status_code=404, detail=f"Explanation not found for decision_id: {decision_id}")

            explainability_queries.labels(query_type='extended', status='success').inc()
            logger.info("explanation_retrieved", decision_id=decision_id)

            return explanation

        except HTTPException:
            raise
        except Exception as e:
            explainability_queries.labels(query_type='extended', status='error').inc()
            logger.error("explanation_retrieval_error", decision_id=decision_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post('/api/v2/explainability/generate')
async def generate_explanation_endpoint(request: GenerateExplanationRequest):
    """
    Gera nova explicação sob demanda (GAPS-04).

    Suporta múltiplos formatos (json, text, html) e features avançadas.
    """
    global api_extensions

    with explainability_query_duration.labels(query_type='generate').time():
        try:
            explanation = await api_extensions.generate_explanation(request.dict())

            explanations_generated.labels(format=request.format).inc()
            explainability_queries.labels(query_type='generate', status='success').inc()

            logger.info(
                "explanation_generated",
                decision_id=request.decision_id,
                format=request.format,
                token=explanation.get('explainability_token')
            )

            return explanation

        except Exception as e:
            explainability_queries.labels(query_type='generate', status='error').inc()
            logger.error("explanation_generation_error", decision_id=request.decision_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get('/api/v2/explainability/{decision_id}/format/{output_format}')
async def get_explanation_formatted(decision_id: str, output_format: str):
    """
    Busca explicação em formato específico (GAPS-04).

    Formatos suportados: json, text, html
    """
    global api_extensions

    valid_formats = ['json', 'text', 'html']
    if output_format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format. Supported: {', '.join(valid_formats)}"
        )

    with explainability_query_duration.labels(query_type=f'format_{output_format}').time():
        try:
            explanation = await api_extensions.get_explainability_by_decision_id(decision_id)

            if not explanation:
                raise HTTPException(status_code=404, detail=f"Explanation not found for decision_id: {decision_id}")

            formatted = api_extensions.format_explanation(explanation, output_format)

            explainability_queries.labels(query_type='format', status='success').inc()

            return formatted

        except HTTPException:
            raise
        except Exception as e:
            explainability_queries.labels(query_type='format', status='error').inc()
            logger.error("explanation_format_error", decision_id=decision_id, format=output_format, error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ========== STATS ENDPOINT ==========

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

            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter['$gte'] = datetime.fromisoformat(start_date)
                if end_date:
                    date_filter['$lte'] = datetime.fromisoformat(end_date)
                pipeline.append({'$match': {'generated_at': date_filter}})

            pipeline.append({
                '$group': {
                    '_id': '$method',
                    'count': {'$sum': 1}
                }
            })

            method_stats = await db.explainability_ledger.aggregate(pipeline).to_list(length=100)
            total = await db.explainability_ledger.count_documents({})

            explainability_queries.labels(query_type='stats', status='success').inc()

            return {
                'total_explanations': total,
                'by_method': {item['_id']: item['count'] for item in method_stats},
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            explainability_queries.labels(query_type='stats', status='error').inc()
            logger.error("explainability_stats_query_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ========== EXCEPTION HANDLER ==========

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global de exceções."""
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={'error': 'Internal server error', 'detail': str(exc)}
    )
