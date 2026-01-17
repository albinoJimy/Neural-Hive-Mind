"""
Semantic Translation Engine - Main Entry Point

Motor de Tradução Semântica que implementa o Fluxo B (Geração de Planos)
do Neural Hive-Mind. Converte Intent Envelopes em Cognitive Plans executáveis.
"""

import asyncio
import json
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from confluent_kafka.admin import AdminClient
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
from src.services.nlp_processor import NLPProcessor
from src.observability.metrics import register_metrics

# Configure structured logging
logger = structlog.get_logger()

# Global state for clients
state = {}


async def validate_kafka_topics_exist(settings) -> None:
    """
    Valida que todos os tópicos Kafka configurados existem no cluster.

    Fail-fast validation executada durante startup antes de inicializar consumer.
    Esta validação complementa a validação no IntentConsumer, fornecendo
    feedback mais rápido durante o startup e logs mais claros para diagnóstico.

    Args:
        settings: Settings object com configurações Kafka

    Raises:
        RuntimeError: Se tópicos não existirem ou conexão falhar

    Exemplo de uso no lifespan:
        await validate_kafka_topics_exist(settings)
    """
    logger.info(
        'Iniciando validação de tópicos Kafka',
        topics=settings.kafka_topics,
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    # Construir configuração do AdminClient
    admin_config = {
        'bootstrap.servers': settings.kafka_bootstrap_servers,
        'socket.timeout.ms': 10000,
    }

    # Adicionar configurações de segurança se necessário
    if settings.kafka_security_protocol != 'PLAINTEXT':
        admin_config['security.protocol'] = settings.kafka_security_protocol
        if settings.kafka_sasl_mechanism:
            admin_config['sasl.mechanism'] = settings.kafka_sasl_mechanism
        if settings.kafka_sasl_username:
            admin_config['sasl.username'] = settings.kafka_sasl_username
        if settings.kafka_sasl_password:
            admin_config['sasl.password'] = settings.kafka_sasl_password

    try:
        admin_client = AdminClient(admin_config)
        cluster_metadata = admin_client.list_topics(timeout=10)
        available_topics = set(cluster_metadata.topics.keys())

        # Verificar tópicos configurados
        configured_topics = set(settings.kafka_topics)
        missing_topics = configured_topics - available_topics

        if missing_topics:
            sorted_available = sorted(list(available_topics))[:20]
            logger.error(
                'STARTUP FAILED: Tópicos Kafka obrigatórios não encontrados',
                missing_topics=sorted(list(missing_topics)),
                configured_topics=sorted(list(configured_topics)),
                available_topics=sorted_available
            )
            raise RuntimeError(
                f"Tópicos Kafka obrigatórios não encontrados: {sorted(list(missing_topics))}. "
                f"Verifique se os tópicos foram criados no cluster Kafka. "
                f"Tópicos disponíveis: {sorted_available[:10]}"
            )

        logger.info(
            'Todos os tópicos Kafka configurados existem no cluster',
            topics=sorted(list(configured_topics)),
            total_available_topics=len(available_topics)
        )

    except RuntimeError:
        # Re-raise RuntimeError (já tratado acima)
        raise
    except Exception as e:
        logger.error(
            'STARTUP FAILED: Não foi possível conectar ao Kafka para validar tópicos',
            error=str(e),
            error_type=type(e).__name__,
            bootstrap_servers=settings.kafka_bootstrap_servers
        )
        raise RuntimeError(
            f"Não foi possível conectar ao Kafka para validar tópicos: {e}"
        ) from e


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

        # Initialize NLP Processor
        nlp_processor = None
        if settings.nlp_enabled:
            try:
                nlp_processor = NLPProcessor(
                    redis_client=redis_client,
                    cache_enabled=settings.nlp_cache_enabled,
                    cache_ttl_seconds=settings.nlp_cache_ttl_seconds,
                    model_pt=settings.nlp_model_pt,
                    model_en=settings.nlp_model_en
                )
                await nlp_processor.initialize()
                state['nlp_processor'] = nlp_processor
                logger.info(
                    'NLP Processor inicializado',
                    cache_enabled=settings.nlp_cache_enabled,
                    cache_ttl=settings.nlp_cache_ttl_seconds,
                    model_pt=settings.nlp_model_pt,
                    model_en=settings.nlp_model_en
                )
            except Exception as e:
                logger.warning(
                    'NLP Processor não inicializado, usando fallback heurístico',
                    error=str(e)
                )

        # Fail-fast validation: verificar tópicos antes de criar consumer
        logger.info('Validando existência de tópicos Kafka no cluster...')
        await validate_kafka_topics_exist(settings)

        # Initialize Kafka producer
        plan_producer = KafkaPlanProducer(settings)
        await plan_producer.initialize()
        plan_producer = instrument_kafka_producer(plan_producer)
        state['producer'] = plan_producer

        # Initialize services
        logger.info("Initializing processing services...")

        # Passar nlp_processor para Neo4jClient
        neo4j_client.nlp_processor = nlp_processor

        semantic_parser = SemanticParser(
            neo4j_client,
            mongodb_client,
            redis_client,
            nlp_processor=nlp_processor
        )
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
        try:
            logger.info('Inicializando Kafka consumer...')
            intent_consumer = IntentConsumer(settings)
            await intent_consumer.initialize()
            intent_consumer = instrument_kafka_consumer(intent_consumer)
            state['consumer'] = intent_consumer
            logger.info(
                'Kafka consumer inicializado com sucesso',
                group_id=settings.kafka_consumer_group_id,
                topics=settings.kafka_topics
            )
        except RuntimeError as e:
            logger.error(
                'STARTUP FAILED: Erro crítico ao inicializar Kafka consumer',
                error=str(e),
                error_type=type(e).__name__,
                group_id=settings.kafka_consumer_group_id,
                topics=settings.kafka_topics
            )
            # Re-raise para impedir startup do serviço
            raise
        except Exception as e:
            logger.error(
                'STARTUP FAILED: Erro inesperado ao inicializar Kafka consumer',
                error=str(e),
                error_type=type(e).__name__
            )
            raise RuntimeError(f"Falha ao inicializar Kafka consumer: {e}") from e

        # Start consuming in background with exception handling
        async def consume_with_error_handling():
            """Wrapper to catch and log exceptions from consumer task"""
            try:
                await intent_consumer.start_consuming(orchestrator.process_intent)
            except Exception as e:
                logger.error(
                    'Consumer task failed with exception',
                    error=str(e),
                    error_type=type(e).__name__
                )
                import traceback
                logger.error(f'Consumer traceback: {traceback.format_exc()}')
                # Atualiza estado para indicar falha do consumer
                if 'consumer' in state and state['consumer']:
                    state['consumer'].running = False
                state['consumer_error'] = str(e)

        consumer_task = asyncio.create_task(consume_with_error_handling())
        state['consumer_task'] = consumer_task  # Store task for monitoring

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
        "redis": False,
        "nlp_processor": False
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

        # Check Kafka consumer usando método is_healthy()
        if 'consumer' in state and state['consumer']:
            try:
                is_healthy, reason = state['consumer'].is_healthy(max_poll_age_seconds=60.0)
                checks['kafka_consumer'] = is_healthy

                if is_healthy:
                    logger.debug("Kafka consumer saudável", reason=reason)
                else:
                    logger.warning("Kafka consumer não saudável", reason=reason)
            except Exception as e:
                logger.error(
                    "Falha ao verificar Kafka consumer",
                    error=str(e),
                    error_type=type(e).__name__
                )
                checks['kafka_consumer'] = False
        else:
            checks['kafka_consumer'] = False
            logger.warning("Kafka consumer não encontrado no state")

        # Check NLP Processor
        if 'nlp_processor' in state:
            checks['nlp_processor'] = state['nlp_processor'].is_ready()
        else:
            # NLP é opcional, marcar como ready se não estiver habilitado
            settings = get_settings()
            checks['nlp_processor'] = not settings.nlp_enabled

        all_ready = all(checks.values())

        response_data = {
            "ready": all_ready,
            "checks": checks
        }

        if all_ready:
            return response_data
        else:
            return Response(
                content=json.dumps(response_data),
                status_code=503,
                media_type="application/json"
            )

    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return Response(
            content=json.dumps({
                "ready": False,
                "checks": checks,
                "error": str(e)
            }),
            status_code=503,
            media_type="application/json"
        )


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
