import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neural_hive_observability import init_observability

from .config import get_settings
from .clients import MongoDBClient, RedisClient, Neo4jClient, ClickHouseClient, ElasticsearchClient, PrometheusClient, QueenAgentGRPCClient
from .services import AnalyticsEngine, QueryEngine, InsightGenerator, CausalAnalyzer, EmbeddingService
from .consumers import TelemetryConsumer, ConsensusConsumer, ExecutionConsumer, PheromoneConsumer
from .producers import InsightProducer
from .api import health, insights, analytics, status, semantics
from .observability.metrics import setup_metrics
from .grpc_service import AnalystGRPCServer

logger = structlog.get_logger()
settings = get_settings()


class AppState:
    """Estado global da aplicação"""

    def __init__(self):
        # Clientes
        self.mongodb_client = None
        self.redis_client = None
        self.neo4j_client = None
        self.clickhouse_client = None
        self.elasticsearch_client = None
        self.prometheus_client = None
        self.queen_agent_client = None

        # Serviços
        self.analytics_engine = None
        self.query_engine = None
        self.insight_generator = None
        self.causal_analyzer = None
        self.embedding_service = None

        # Kafka
        self.telemetry_consumer = None
        self.consensus_consumer = None
        self.execution_consumer = None
        self.pheromone_consumer = None
        self.insight_producer = None
        self.consumer_tasks = []

        # gRPC
        self.grpc_server = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciar ciclo de vida da aplicação"""
    logger.info('starting_analyst_agents', version=settings.SERVICE_VERSION)

    init_observability(
        service_name='analyst-agents',
        service_version=settings.SERVICE_VERSION,
        neural_hive_component='analyst-agent',
        neural_hive_layer='analise',
        neural_hive_domain='insight-generation',
        otel_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
    )
    setup_metrics()

    # Inicializar clientes
    try:
        # MongoDB
        app_state.mongodb_client = MongoDBClient(
            uri=settings.MONGODB_URI,
            database=settings.MONGODB_DATABASE,
            collection=settings.MONGODB_COLLECTION_INSIGHTS,
            max_pool_size=settings.MONGODB_MAX_POOL_SIZE,
            min_pool_size=settings.MONGODB_MIN_POOL_SIZE
        )
        await app_state.mongodb_client.initialize()

        # Redis
        app_state.redis_client = RedisClient(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            ttl=settings.REDIS_INSIGHTS_TTL
        )
        await app_state.redis_client.initialize()

        # Neo4j
        app_state.neo4j_client = Neo4jClient(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
            database=settings.NEO4J_DATABASE
        )
        await app_state.neo4j_client.initialize()

        # ClickHouse
        app_state.clickhouse_client = ClickHouseClient(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE
        )
        app_state.clickhouse_client.initialize()

        # Elasticsearch
        app_state.elasticsearch_client = ElasticsearchClient(
            hosts=settings.ELASTICSEARCH_HOSTS,
            user=settings.ELASTICSEARCH_USER,
            password=settings.ELASTICSEARCH_PASSWORD
        )
        await app_state.elasticsearch_client.initialize()

        # Prometheus
        app_state.prometheus_client = PrometheusClient(url=settings.PROMETHEUS_URL)
        app_state.prometheus_client.initialize()

        # Queen Agent gRPC Client
        app_state.queen_agent_client = QueenAgentGRPCClient(
            host=settings.QUEEN_AGENT_GRPC_HOST,
            port=settings.QUEEN_AGENT_GRPC_PORT
        )
        await app_state.queen_agent_client.initialize()

        logger.info('database_clients_initialized')

    except Exception as e:
        logger.error('client_initialization_failed', error=str(e))
        raise

    # Inicializar serviços
    try:
        app_state.analytics_engine = AnalyticsEngine(min_confidence=settings.ANALYTICS_MIN_CONFIDENCE)

        app_state.query_engine = QueryEngine(
            clickhouse_client=app_state.clickhouse_client,
            neo4j_client=app_state.neo4j_client,
            elasticsearch_client=app_state.elasticsearch_client,
            prometheus_client=app_state.prometheus_client,
            redis_client=app_state.redis_client
        )

        app_state.insight_generator = InsightGenerator(min_confidence=settings.ANALYTICS_MIN_CONFIDENCE)

        app_state.causal_analyzer = CausalAnalyzer(min_confidence=settings.ANALYTICS_MIN_CONFIDENCE)

        app_state.embedding_service = EmbeddingService(
            model_name='all-MiniLM-L6-v2',
            cache_client=app_state.redis_client
        )
        await app_state.embedding_service.initialize()

        logger.info('services_initialized')

    except Exception as e:
        logger.error('service_initialization_failed', error=str(e))
        raise

    # Inicializar Kafka Producer
    try:
        app_state.insight_producer = InsightProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            default_topic=settings.KAFKA_TOPICS_INSIGHTS
        )
        await app_state.insight_producer.initialize()
        logger.info('kafka_producer_initialized')

    except Exception as e:
        logger.error('kafka_producer_initialization_failed', error=str(e))
        raise

    # Inicializar Kafka Consumers
    try:
        # Telemetry Consumer
        app_state.telemetry_consumer = TelemetryConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            topic=settings.KAFKA_TOPICS_TELEMETRY,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            analytics_engine=app_state.analytics_engine,
            insight_generator=app_state.insight_generator,
            mongodb_client=app_state.mongodb_client,
            redis_client=app_state.redis_client,
            insight_producer=app_state.insight_producer,
            queen_agent_client=app_state.queen_agent_client,
            window_size_seconds=settings.ANALYTICS_WINDOW_SIZE_SECONDS
        )
        await app_state.telemetry_consumer.initialize()

        # Consensus Consumer
        app_state.consensus_consumer = ConsensusConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            topic=settings.KAFKA_TOPICS_CONSENSUS,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            analytics_engine=app_state.analytics_engine,
            insight_generator=app_state.insight_generator,
            mongodb_client=app_state.mongodb_client,
            redis_client=app_state.redis_client,
            insight_producer=app_state.insight_producer,
            queen_agent_client=app_state.queen_agent_client
        )
        await app_state.consensus_consumer.initialize()

        # Execution Consumer
        app_state.execution_consumer = ExecutionConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            topic=settings.KAFKA_TOPICS_EXECUTION,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            insight_generator=app_state.insight_generator,
            mongodb_client=app_state.mongodb_client,
            redis_client=app_state.redis_client,
            insight_producer=app_state.insight_producer,
            queen_agent_client=app_state.queen_agent_client
        )
        await app_state.execution_consumer.initialize()

        # Pheromone Consumer
        app_state.pheromone_consumer = PheromoneConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            topic=settings.KAFKA_TOPICS_PHEROMONES,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            insight_generator=app_state.insight_generator,
            mongodb_client=app_state.mongodb_client,
            redis_client=app_state.redis_client,
            insight_producer=app_state.insight_producer,
            queen_agent_client=app_state.queen_agent_client
        )
        await app_state.pheromone_consumer.initialize()

        logger.info('kafka_consumers_initialized')

        # Iniciar consumers em background tasks
        app_state.consumer_tasks = [
            asyncio.create_task(app_state.telemetry_consumer.start()),
            asyncio.create_task(app_state.consensus_consumer.start()),
            asyncio.create_task(app_state.execution_consumer.start()),
            asyncio.create_task(app_state.pheromone_consumer.start())
        ]

        logger.info('kafka_consumers_started', count=len(app_state.consumer_tasks))

    except Exception as e:
        logger.error('kafka_consumers_initialization_failed', error=str(e))
        raise

    # Inicializar gRPC Server (opcional)
    try:
        if settings.GRPC_ENABLED:
            app_state.grpc_server = AnalystGRPCServer(
                host=settings.GRPC_HOST,
                port=settings.GRPC_PORT,
                mongodb_client=app_state.mongodb_client,
                redis_client=app_state.redis_client,
                query_engine=app_state.query_engine,
                analytics_engine=app_state.analytics_engine,
                insight_generator=app_state.insight_generator
            )
            await app_state.grpc_server.start()
            logger.info('grpc_server_started')

    except Exception as e:
        logger.warning('grpc_server_initialization_failed', error=str(e))
        # Não falhar se gRPC não estiver disponível

    logger.info('analyst_agents_started')

    yield

    # Shutdown
    logger.info('shutting_down_analyst_agents')

    # Parar gRPC server
    if app_state.grpc_server:
        await app_state.grpc_server.stop()

    # Parar consumers
    if app_state.telemetry_consumer:
        await app_state.telemetry_consumer.stop()
    if app_state.consensus_consumer:
        await app_state.consensus_consumer.stop()
    if app_state.execution_consumer:
        await app_state.execution_consumer.stop()
    if app_state.pheromone_consumer:
        await app_state.pheromone_consumer.stop()

    # Cancelar tasks
    for task in app_state.consumer_tasks:
        task.cancel()

    # Fechar producer
    if app_state.insight_producer:
        await app_state.insight_producer.close()

    # Fechar serviços
    if app_state.embedding_service:
        await app_state.embedding_service.close()

    # Fechar clientes
    if app_state.queen_agent_client:
        await app_state.queen_agent_client.close()
    if app_state.mongodb_client:
        await app_state.mongodb_client.close()
    if app_state.redis_client:
        await app_state.redis_client.close()
    if app_state.neo4j_client:
        await app_state.neo4j_client.close()
    if app_state.clickhouse_client:
        app_state.clickhouse_client.close()
    if app_state.elasticsearch_client:
        await app_state.elasticsearch_client.close()
    if app_state.prometheus_client:
        await app_state.prometheus_client.close()

    logger.info('analyst_agents_stopped')


# Criar aplicação FastAPI
app = FastAPI(
    title='Analyst Agents',
    description='Consolidação de Insights Multi-Fonte',
    version=settings.SERVICE_VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Routers
app.include_router(health.router, tags=['health'])
app.include_router(insights.router, prefix='/api/v1', tags=['insights'])
app.include_router(analytics.router, prefix='/api/v1', tags=['analytics'])
app.include_router(status.router, prefix='/api/v1', tags=['status'])
app.include_router(semantics.router, prefix='/api/v1', tags=['semantics'])


# Adicionar app_state ao app
app.state.app_state = app_state


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host=settings.FASTAPI_HOST, port=settings.FASTAPI_PORT)
