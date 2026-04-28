"""
Approval Service - Main Entry Point

Servico de aprovacao humana para Cognitive Plans de alto risco ou destrutivos.
Fornece API REST para admins e processamento async via Kafka.
"""

import asyncio
from contextlib import asynccontextmanager

import structlog
from confluent_kafka.admin import AdminClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# SEC-001: Security Headers
from neural_hive_security import SecurityHeadersMiddleware
from src.adapters.feedback_config_adapter import create_feedback_collector_config
from src.api.routers import (
    active_learning,
    approvals,
    continuous_feedback,
    dashboard,
    health,
)
from src.observability import configure_logging_with_pii_masking
from src.clients.cognitive_ledger_client import CognitiveLedgerClient
from src.clients.feature_store_client import FeatureStoreClient
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import get_settings
from src.consumers.approval_request_consumer import ApprovalRequestConsumer
from src.observability.metrics import NeuralHiveMetrics, register_metrics

# Neural Hive Observability
try:
    from neural_hive_observability import init_observability

    HAS_OBSERVABILITY = True
except ImportError:
    HAS_OBSERVABILITY = False
from src.producers.approval_response_producer import ApprovalResponseProducer
from src.producers.training_data_producer import TrainingDataProducer
from src.services.approval_service import ApprovalService
from src.services.continuous_feedback_service import ContinuousFeedbackService
from src.services.ml_predictor_service import get_ml_predictor_service

# Import opcional - pode nao estar disponivel em todos os ambientes
try:
    from neural_hive_specialists.feedback import FeedbackCollector

    HAS_FEEDBACK_COLLECTOR = True
except ImportError:
    FeedbackCollector = None
    HAS_FEEDBACK_COLLECTOR = False

# Configure structured logging with PII masking (GDPR/LGPD compliance)
configure_logging_with_pii_masking()

logger = structlog.get_logger()

# Estado global para clientes
state = {}


async def validate_kafka_topics_exist(settings) -> None:
    """
    Valida que topicos Kafka configurados existem no cluster.

    Args:
        settings: Settings object com configuracoes Kafka

    Raises:
        RuntimeError: Se topicos nao existirem ou conexao falhar
    """
    required_topics = [
        settings.kafka_approval_requests_topic,
        settings.kafka_approval_responses_topic,
    ]

    logger.info(
        "Validando topicos Kafka",
        topics=required_topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
    )

    admin_config = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "socket.timeout.ms": 10000,
    }

    if settings.kafka_security_protocol != "PLAINTEXT":
        admin_config["security.protocol"] = settings.kafka_security_protocol
        if settings.kafka_sasl_mechanism:
            admin_config["sasl.mechanism"] = settings.kafka_sasl_mechanism
        if settings.kafka_sasl_username:
            admin_config["sasl.username"] = settings.kafka_sasl_username
        if settings.kafka_sasl_password:
            admin_config["sasl.password"] = settings.kafka_sasl_password

    try:
        admin_client = AdminClient(admin_config)
        cluster_metadata = admin_client.list_topics(timeout=10)
        available_topics = set(cluster_metadata.topics.keys())

        missing_topics = set(required_topics) - available_topics

        if missing_topics:
            logger.error(
                "STARTUP FAILED: Topicos Kafka nao encontrados",
                missing_topics=sorted(list(missing_topics)),
                available_topics=sorted(list(available_topics))[:20],
            )
            raise RuntimeError(f"Topicos Kafka nao encontrados: {sorted(list(missing_topics))}")

        logger.info("Topicos Kafka validados", topics=required_topics)

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("STARTUP FAILED: Nao foi possivel conectar ao Kafka", error=str(e))
        raise RuntimeError(f"Falha na conexao com Kafka: {e}") from e


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicacao"""
    settings = get_settings()

    logger.info(
        "Starting Approval Service",
        version=settings.service_version,
        environment=settings.environment,
    )

    # Inicializa observabilidade (tracing, metrics)
    if HAS_OBSERVABILITY:
        try:
            init_observability(
                service_name="approval-service",
                service_version=settings.service_version,
                neural_hive_component="approval",
                neural_hive_layer="cognitive",
                neural_hive_domain="decision-making",
                otel_endpoint=settings.otel_endpoint,
                prometheus_port=0,  # Desabilitado - usando /metrics endpoint do FastAPI
            )
            logger.info("Observabilidade inicializada", otel_endpoint=settings.otel_endpoint)
        except Exception as e:
            logger.warning("Falha ao inicializar observabilidade", error=str(e))

    try:
        # Inicializa MongoDB client
        logger.info("Inicializando MongoDB client...")
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.initialize()
        state["mongodb"] = mongodb_client

        # Inicializa cliente do ledger cognitivo
        ledger_client = None
        if settings.enable_feedback_collection:
            logger.info("Inicializando CognitiveLedgerClient...")
            try:
                ledger_client = CognitiveLedgerClient(settings)
                await ledger_client.initialize()
                state["ledger_client"] = ledger_client
                logger.info("CognitiveLedgerClient inicializado com sucesso")
            except Exception as e:
                logger.error("Falha ao inicializar CognitiveLedgerClient", error=str(e))
                if settings.feedback_on_approval_failure_mode == "raise_error":
                    raise
                logger.warning("Continuando sem feedback collection")

        # Inicializa FeedbackCollector
        feedback_collector = None
        if settings.enable_feedback_collection and ledger_client and HAS_FEEDBACK_COLLECTOR:
            logger.info("Inicializando FeedbackCollector...")
            try:
                feedback_config = create_feedback_collector_config(settings)
                feedback_collector = FeedbackCollector(config=feedback_config, audit_logger=None)
                state["feedback_collector"] = feedback_collector
                logger.info("FeedbackCollector inicializado com sucesso")
            except Exception as e:
                logger.error("Falha ao inicializar FeedbackCollector", error=str(e))
                if settings.feedback_on_approval_failure_mode == "raise_error":
                    raise
                logger.warning("Continuando sem feedback collection")
        elif settings.enable_feedback_collection and not HAS_FEEDBACK_COLLECTOR:
            logger.warning(
                "FeedbackCollector nao disponivel - neural_hive_specialists nao instalado"
            )

        # Inicializa ML Predictor Service
        ml_predictor = None
        if settings.enable_ml_prediction:
            logger.info("Inicializando ML Predictor Service...")
            try:
                ml_predictor = get_ml_predictor_service(settings)
                if ml_predictor.is_enabled():
                    model_info = ml_predictor.get_model_info()
                    logger.info(
                        "ML Predictor Service inicializado",
                        model_version=model_info.get("version") if model_info else "unknown",
                        auto_approve_threshold=settings.ml_auto_approve_threshold,
                        auto_reject_threshold=settings.ml_auto_reject_threshold,
                    )
                else:
                    logger.info("ML Predictor desabilitado (modelo nao encontrado)")
            except Exception as e:
                logger.error("Falha ao inicializar ML Predictor", error=str(e))
                if settings.feedback_on_approval_failure_mode == "raise_error":
                    raise
                logger.warning("Continuando sem ML prediction")

        # Inicializa Active Learning components
        balance_analyzer = None
        learning_strategy = None
        priority_queue = None

        if settings.enable_active_learning and HAS_FEEDBACK_COLLECTOR:
            logger.info("Inicializando Active Learning components...")
            try:
                from neural_hive_specialists.feedback.active_learning.balance_analyzer import (
                    DatasetBalanceAnalyzer,
                )
                from neural_hive_specialists.feedback.active_learning.feedback_queue import (
                    PriorityFeedbackQueue,
                )
                from neural_hive_specialists.feedback.active_learning.learning_strategy import (
                    ActiveLearningStrategy,
                )

                # Inicializar BalanceAnalyzer
                balance_analyzer = DatasetBalanceAnalyzer(
                    mongodb_uri=settings.mongodb_uri,
                    database=settings.mongodb_database,
                    collection=settings.feedback_mongodb_collection,
                )

                # Inicializar ActiveLearningStrategy
                learning_strategy = ActiveLearningStrategy(
                    confidence_weight=0.5, representation_weight=0.3, novelty_weight=0.2
                )

                # Inicializar PriorityFeedbackQueue
                priority_queue = PriorityFeedbackQueue(
                    mongodb_uri=settings.mongodb_uri,
                    database=settings.mongodb_database,
                    collection=settings.active_learning_queue_collection,
                )
                await priority_queue.initialize()

                logger.info(
                    "Active Learning components inicializados",
                    min_information_value=settings.active_learning_min_information_value,
                    enqueue_rate=settings.active_learning_enqueue_rate,
                )
            except Exception as e:
                logger.error("Falha ao inicializar Active Learning", error=str(e))
                if settings.feedback_on_approval_failure_mode == "raise_error":
                    raise
                logger.warning("Continuando sem Active Learning")

        # Inicializa metricas
        metrics = NeuralHiveMetrics(mongodb_client=mongodb_client)
        state["metrics"] = metrics

        # Valida topicos Kafka
        logger.info("Validando topicos Kafka...")
        await validate_kafka_topics_exist(settings)

        # Inicializa Kafka producer
        logger.info("Inicializando Kafka producer...")
        response_producer = ApprovalResponseProducer(settings)
        await response_producer.initialize()
        state["producer"] = response_producer

        # EPIC 3.3: Inicializa Training Data Producer para continuous feedback
        logger.info("Inicializando Training Data Producer (continuous feedback)...")
        training_data_producer = TrainingDataProducer(settings)
        await training_data_producer.initialize()
        state["training_data_producer"] = training_data_producer

        # Inicializa Kafka consumer
        logger.info("Inicializando Kafka consumer...")
        request_consumer = ApprovalRequestConsumer(settings)
        await request_consumer.initialize()
        state["consumer"] = request_consumer

        # Inicializa Feature Store Client (opcional)
        feature_store_client = None
        try:
            feature_store_client = FeatureStoreClient(settings)
            await feature_store_client.initialize()
            state["feature_store_client"] = feature_store_client
            logger.info("Feature Store client inicializado")
        except Exception as e:
            logger.warning("Feature Store client não disponível", error=str(e))

        # Inicializa servico de aprovacao
        approval_service = ApprovalService(
            settings=settings,
            mongodb_client=mongodb_client,
            response_producer=response_producer,
            metrics=metrics,
            feedback_collector=feedback_collector,
            ledger_client=ledger_client,
            ml_predictor=ml_predictor,
            balance_analyzer=balance_analyzer,
            learning_strategy=learning_strategy,
            priority_queue=priority_queue,
            feature_store_client=feature_store_client,
        )
        state["approval_service"] = approval_service

        # Configura referencias nos routers e state
        approvals.set_approval_service(approval_service)
        health.set_app_state(state)

        # EPIC 3.3: Inicializa Continuous Feedback Service
        logger.info("Inicializando Continuous Feedback Service...")
        continuous_feedback_service = ContinuousFeedbackService(
            settings=settings,
            mongodb_client=mongodb_client,
            training_data_producer=training_data_producer,
        )
        await continuous_feedback_service.initialize()
        state["continuous_feedback_service"] = continuous_feedback_service
        continuous_feedback.set_continuous_feedback_service(continuous_feedback_service)
        logger.info("Continuous Feedback Service inicializado")

        # Configurar Active Learning no app.state para router
        app.state.balance_analyzer = balance_analyzer
        app.state.feedback_queue = priority_queue
        app.state.feedback_collector = feedback_collector

        # Inicia consumer em background
        async def consume_with_error_handling():
            """Wrapper para tratar excecoes do consumer"""
            try:
                await request_consumer.start_consuming(approval_service.process_approval_request)
            except Exception as e:
                logger.error("Consumer task falhou", error=str(e))
                import traceback

                logger.error(f"Consumer traceback: {traceback.format_exc()}")
                if "consumer" in state and state["consumer"]:
                    state["consumer"].running = False
                state["consumer_error"] = str(e)

        consumer_task = asyncio.create_task(consume_with_error_handling())
        state["consumer_task"] = consumer_task

        logger.info("Approval Service started successfully")

        yield  # Aplicacao rodando

    finally:
        # Cleanup no shutdown
        logger.info("Shutting down Approval Service...")

        if "consumer" in state:
            await state["consumer"].close()

        if "producer" in state:
            await state["producer"].close()

        # EPIC 3.3: Fecha Training Data Producer
        if "training_data_producer" in state:
            await state["training_data_producer"].close()

        if "mongodb" in state:
            await state["mongodb"].close()

        if "ledger_client" in state:
            await state["ledger_client"].close()

        if "feedback_collector" in state:
            state["feedback_collector"].close()

        if "feature_store_client" in state:
            await state["feature_store_client"].close()

        logger.info("Shutdown complete")


# Cria aplicacao FastAPI
app = FastAPI(
    title="Approval Service",
    description="Servico de Aprovacao Humana para Cognitive Plans",
    version="1.0.0",
    lifespan=lifespan,
)

# Configura CORS - usa origens do settings por ambiente
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)

# SEC-001: Adicionar middleware de security headers
app.add_middleware(SecurityHeadersMiddleware)

# Registra metricas
register_metrics()

# Inclui routers
app.include_router(health.router)
app.include_router(approvals.router)
app.include_router(active_learning.router)
app.include_router(dashboard.router)
app.include_router(continuous_feedback.router)  # EPIC 3.3


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "src.main:app", host="0.0.0.0", port=8080, workers=1, log_level=settings.log_level.lower()
    )
