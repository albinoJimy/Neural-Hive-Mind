import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from grpc import aio
from neural_hive_observability import (
    init_observability,
    create_instrumented_async_grpc_server,
    ObservabilityConfig
)

from .config import get_settings
from .clients import (
    MongoDBClient, RedisClient, Neo4jClient, PrometheusClient,
    OrchestratorClient, ServiceRegistryClient, PheromoneClient
)
from .services import (
    StrategicDecisionEngine, ConflictArbitrator, ReplanningCoordinator,
    ExceptionApprovalService, TelemetryAggregator
)
from .consumers import ConsensusConsumer, TelemetryConsumer, IncidentConsumer
from .producers import StrategicDecisionProducer
from .api import health_router, decisions_router, exceptions_router, status_router
from .grpc_server import QueenAgentServicer
from .proto import queen_agent_pb2_grpc


# Configurar structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()
settings = get_settings()


class AppState:
    """Estado global da aplicação"""

    def __init__(self):
        # Clientes
        self.mongodb_client: MongoDBClient | None = None
        self.redis_client: RedisClient | None = None
        self.neo4j_client: Neo4jClient | None = None
        self.prometheus_client: PrometheusClient | None = None
        self.orchestrator_client: OrchestratorClient | None = None
        self.service_registry_client: ServiceRegistryClient | None = None
        self.pheromone_client: PheromoneClient | None = None

        # Serviços
        self.decision_engine: StrategicDecisionEngine | None = None
        self.conflict_arbitrator: ConflictArbitrator | None = None
        self.replanning_coordinator: ReplanningCoordinator | None = None
        self.exception_service: ExceptionApprovalService | None = None
        self.telemetry_aggregator: TelemetryAggregator | None = None

        # Kafka
        self.consensus_consumer: ConsensusConsumer | None = None
        self.telemetry_consumer: TelemetryConsumer | None = None
        self.incident_consumer: IncidentConsumer | None = None
        self.strategic_producer: StrategicDecisionProducer | None = None

        # gRPC
        self.grpc_server: aio.Server | None = None
        self.grpc_servicer: QueenAgentServicer | None = None

        # Background tasks
        self.consumer_tasks: list[asyncio.Task] = []


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciar lifecycle da aplicação"""

    # === STARTUP ===
    logger.info("queen_agent_starting", version=settings.SERVICE_VERSION)

    try:
        # 1. Configurar tracing
        try:
            init_observability(
                service_name=settings.SERVICE_NAME,
                service_version=settings.SERVICE_VERSION,
                neural_hive_component="queen-agent",
                neural_hive_layer="coordination",
                environment=settings.ENVIRONMENT,
                otel_endpoint=settings.OTEL_EXPORTER_ENDPOINT,
                prometheus_port=settings.METRICS_PORT,
                log_level=settings.LOG_LEVEL,
            )
        except Exception as e:
            logger.warning(
                "observability_init_failed",
                error=str(e),
                otel_endpoint=settings.OTEL_EXPORTER_ENDPOINT,
                prometheus_port=settings.METRICS_PORT
            )

        # 2. Inicializar clientes
        logger.info("initializing_clients")

        app_state.mongodb_client = MongoDBClient(settings)
        await app_state.mongodb_client.initialize()

        app_state.redis_client = RedisClient(settings)
        await app_state.redis_client.initialize()

        app_state.neo4j_client = Neo4jClient(settings)
        await app_state.neo4j_client.initialize()

        app_state.prometheus_client = PrometheusClient(settings)

        app_state.orchestrator_client = OrchestratorClient(settings)
        await app_state.orchestrator_client.initialize()

        app_state.service_registry_client = ServiceRegistryClient(settings)
        await app_state.service_registry_client.initialize()

        app_state.pheromone_client = PheromoneClient(app_state.redis_client, settings)

        # 3. Inicializar serviços
        logger.info("initializing_services")

        app_state.replanning_coordinator = ReplanningCoordinator(
            app_state.orchestrator_client,
            app_state.redis_client,
            settings
        )

        app_state.decision_engine = StrategicDecisionEngine(
            app_state.mongodb_client,
            app_state.redis_client,
            app_state.neo4j_client,
            app_state.prometheus_client,
            app_state.pheromone_client,
            app_state.replanning_coordinator,
            settings
        )

        app_state.conflict_arbitrator = ConflictArbitrator(
            app_state.neo4j_client,
            settings
        )

        app_state.exception_service = ExceptionApprovalService(
            app_state.mongodb_client,
            settings
        )

        app_state.telemetry_aggregator = TelemetryAggregator(
            app_state.prometheus_client,
            app_state.redis_client,
            settings
        )

        # 4. Inicializar Kafka producer
        logger.info("initializing_kafka_producer")

        app_state.strategic_producer = StrategicDecisionProducer(settings)
        await app_state.strategic_producer.initialize()

        # 5. Inicializar Kafka consumers
        logger.info("initializing_kafka_consumers")

        app_state.consensus_consumer = ConsensusConsumer(
            settings,
            app_state.decision_engine,
            app_state.strategic_producer
        )
        await app_state.consensus_consumer.initialize()

        app_state.telemetry_consumer = TelemetryConsumer(
            settings,
            app_state.decision_engine,
            app_state.strategic_producer
        )
        await app_state.telemetry_consumer.initialize()

        app_state.incident_consumer = IncidentConsumer(
            settings,
            app_state.decision_engine,
            app_state.redis_client,
            app_state.strategic_producer
        )
        await app_state.incident_consumer.initialize()

        # 6. Inicializar gRPC server
        logger.info("initializing_grpc_server")

        app_state.grpc_servicer = QueenAgentServicer(
            app_state.mongodb_client,
            app_state.neo4j_client,
            app_state.exception_service,
            app_state.telemetry_aggregator
        )

        obs_config = ObservabilityConfig(
            service_name=settings.SERVICE_NAME,
            service_version=settings.SERVICE_VERSION,
            neural_hive_component="queen-agent",
            neural_hive_layer="coordination",
            environment=settings.ENVIRONMENT,
            otel_endpoint=settings.OTEL_EXPORTER_ENDPOINT
        )
        app_state.grpc_server = create_instrumented_async_grpc_server(
            config=obs_config
        )
        queen_agent_pb2_grpc.add_QueenAgentServicer_to_server(
            app_state.grpc_servicer,
            app_state.grpc_server
        )

        # Configurar porta gRPC
        grpc_port = settings.GRPC_PORT if hasattr(settings, 'GRPC_PORT') else 50051
        app_state.grpc_server.add_insecure_port(f'[::]:{grpc_port}')

        # Iniciar servidor gRPC
        await app_state.grpc_server.start()
        logger.info("grpc_server_started", port=grpc_port)

        # 7. Iniciar consumers em background
        logger.info("starting_kafka_consumers_background_tasks")

        app_state.consumer_tasks.append(
            asyncio.create_task(app_state.consensus_consumer.start())
        )
        app_state.consumer_tasks.append(
            asyncio.create_task(app_state.telemetry_consumer.start())
        )
        app_state.consumer_tasks.append(
            asyncio.create_task(app_state.incident_consumer.start())
        )

        logger.info("queen_agent_started_successfully")

    except Exception as e:
        logger.error("queen_agent_startup_failed", error=str(e))
        raise

    # === APP RUNNING ===
    yield

    # === SHUTDOWN ===
    logger.info("queen_agent_shutting_down")

    try:
        # 1. Parar gRPC server
        if app_state.grpc_server:
            logger.info("stopping_grpc_server")
            await app_state.grpc_server.stop(grace=5)
            logger.info("grpc_server_stopped")

        # 2. Parar consumers
        if app_state.consensus_consumer:
            await app_state.consensus_consumer.stop()
        if app_state.telemetry_consumer:
            await app_state.telemetry_consumer.stop()
        if app_state.incident_consumer:
            await app_state.incident_consumer.stop()

        # 3. Cancelar background tasks
        for task in app_state.consumer_tasks:
            task.cancel()

        await asyncio.gather(*app_state.consumer_tasks, return_exceptions=True)

        # 4. Fechar producer
        if app_state.strategic_producer:
            await app_state.strategic_producer.close()

        # 5. Fechar clientes
        if app_state.mongodb_client:
            await app_state.mongodb_client.close()
        if app_state.redis_client:
            await app_state.redis_client.close()
        if app_state.neo4j_client:
            await app_state.neo4j_client.close()
        if app_state.orchestrator_client:
            await app_state.orchestrator_client.close()
        if app_state.service_registry_client:
            await app_state.service_registry_client.close()

        logger.info("queen_agent_shutdown_complete")

    except Exception as e:
        logger.error("queen_agent_shutdown_failed", error=str(e))


# Criar aplicação FastAPI
app = FastAPI(
    title="Queen Agent",
    description="Coordenador Estratégico do Neural Hive-Mind",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan
)

# Injetar app_state para que os routers possam acessá-lo
app.state.app_state = app_state

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Montar routers
app.include_router(health_router)
app.include_router(decisions_router)
app.include_router(exceptions_router)
app.include_router(status_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,  # Usar objeto app diretamente em vez de string
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
        log_level=settings.LOG_LEVEL.lower()
    )
