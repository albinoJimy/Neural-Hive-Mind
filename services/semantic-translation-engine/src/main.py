"""
Semantic Translation Engine - Main Entry Point

Motor de Tradução Semântica que implementa o Fluxo B (Geração de Planos)
do Neural Hive-Mind. Converte Intent Envelopes em Cognitive Plans executáveis.
"""

import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from neural_hive_observability import (
    get_tracer,
    init_observability,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)

from src.config.settings import get_settings
from src.consumers.intent_consumer import IntentConsumer
from src.producers.plan_producer import KafkaPlanProducer
from src.clients.neo4j_client import Neo4jClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.services.semantic_parser import SemanticParser
from src.services.dag_generator import DAGGenerator
from src.services.risk_scorer import RiskScorer
from src.services.explainability_generator import ExplainabilityGenerator
from src.services.orchestrator import SemanticTranslationOrchestrator
from src.observability.metrics import register_metrics

# Configure structured logging
logger = structlog.get_logger()

# Global state for clients
state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    settings = get_settings()

    logger.info(
        "Starting Semantic Translation Engine",
        version=settings.service_version,
        environment=settings.environment
    )

    init_observability(
        service_name='semantic-translation-engine',
        service_version='1.0.0',
        neural_hive_component='semantic-translator',
        neural_hive_layer='cognitiva',
        neural_hive_domain='plan-generation',
        otel_endpoint=settings.otel_endpoint,
        prometheus_port=0,  # Desabilitado - usando /metrics endpoint do FastAPI
    )

    try:
        # Initialize clients
        logger.info("Initializing infrastructure clients...")

        # Neo4j client
        neo4j_client = Neo4jClient(settings)
        await neo4j_client.initialize()
        state['neo4j'] = neo4j_client

        # MongoDB client
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.initialize()
        state['mongodb'] = mongodb_client

        # Redis client
        redis_client = RedisClient(settings)
        await redis_client.initialize()
        state['redis'] = redis_client

        # Initialize Kafka producer
        plan_producer = KafkaPlanProducer(settings)
        await plan_producer.initialize()
        plan_producer = instrument_kafka_producer(plan_producer)
        state['producer'] = plan_producer

        # Initialize services
        logger.info("Initializing processing services...")

        semantic_parser = SemanticParser(neo4j_client, mongodb_client, redis_client)
        dag_generator = DAGGenerator()
        risk_scorer = RiskScorer(settings)
        explainability_generator = ExplainabilityGenerator(mongodb_client)

        # Initialize orchestrator
        from src.observability.metrics import NeuralHiveMetrics
        metrics = NeuralHiveMetrics(
            service_name=settings.service_name,
            component='semantic-translator',
            layer='cognitiva'
        )

        orchestrator = SemanticTranslationOrchestrator(
            semantic_parser=semantic_parser,
            dag_generator=dag_generator,
            risk_scorer=risk_scorer,
            explainability_generator=explainability_generator,
            mongodb_client=mongodb_client,
            neo4j_client=neo4j_client,
            plan_producer=plan_producer,
            metrics=metrics
        )
        state['orchestrator'] = orchestrator

        logger.info(
            'Orchestrator inicializado com persistencia Neo4j habilitada',
            neo4j_uri=settings.neo4j_uri
        )

        # Initialize Kafka consumer
        intent_consumer = IntentConsumer(settings)
        await intent_consumer.initialize()
        intent_consumer = instrument_kafka_consumer(intent_consumer)
        state['consumer'] = intent_consumer

        # Start consuming in background
        asyncio.create_task(
            intent_consumer.start_consuming(orchestrator.process_intent)
        )

        logger.info("Semantic Translation Engine started successfully")

        yield  # Application is running

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down Semantic Translation Engine...")

        if 'consumer' in state:
            await state['consumer'].close()

        if 'producer' in state:
            await state['producer'].close()

        if 'neo4j' in state:
            await state['neo4j'].close()

        if 'mongodb' in state:
            await state['mongodb'].close()

        if 'redis' in state:
            await state['redis'].close()

        logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Semantic Translation Engine",
    description="Motor de Tradução Semântica - Geração de Planos Cognitivos (Fluxo B)",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register metrics
register_metrics()


@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "semantic-translation-engine",
        "version": "1.0.0"
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies all dependencies are connected"""
    checks = {
        "kafka_consumer": False,
        "kafka_producer": False,
        "neo4j": False,
        "mongodb": False,
        "redis": False
    }

    try:
        # Check Redis connectivity
        if 'redis' in state and state['redis'].client:
            try:
                await state['redis'].client.ping()
                checks['redis'] = True
            except Exception as e:
                logger.warning("Redis ping failed", error=str(e))

        # Check MongoDB connectivity
        if 'mongodb' in state and state['mongodb'].client:
            try:
                await state['mongodb'].client.admin.command('ping')
                checks['mongodb'] = True
            except Exception as e:
                logger.warning("MongoDB ping failed", error=str(e))

        # Check Neo4j connectivity
        if 'neo4j' in state and state['neo4j'].driver:
            try:
                await state['neo4j'].driver.verify_connectivity()
                checks['neo4j'] = True
            except Exception as e:
                logger.warning("Neo4j connectivity check failed", error=str(e))

        # Check Kafka producer
        if 'producer' in state and state['producer'].producer:
            try:
                # Lightweight metadata fetch with timeout
                state['producer'].producer.list_topics(timeout=2)
                checks['kafka_producer'] = True
            except Exception as e:
                logger.warning("Kafka producer check failed", error=str(e))

        # Check Kafka consumer
        if 'consumer' in state and state['consumer'].consumer:
            try:
                # Verify consumer is properly connected and has assignments
                state['consumer'].consumer.list_topics(timeout=2)
                assignments = state['consumer'].consumer.assignment()
                if assignments:
                    checks['kafka_consumer'] = True
                else:
                    logger.warning("Kafka consumer has no topic assignments yet")
            except Exception as e:
                logger.warning("Kafka consumer check failed", error=str(e))

        all_ready = all(checks.values())

        return {
            "ready": all_ready,
            "checks": checks
        }

    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return {
            "ready": False,
            "checks": checks,
            "error": str(e)
        }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
        log_level=settings.log_level.lower()
    )
