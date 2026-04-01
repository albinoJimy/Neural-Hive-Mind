import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neural_hive_observability import (
    ObservabilityConfig,
    create_instrumented_async_grpc_server,
    init_observability,
)

from .api import (
    decisions_router,
    election_router,
    exceptions_router,
    health_router,
    mcp_router,
    status_router,
    workers_router,
)
from .clients import (
    MongoDBClient,
    Neo4jClient,
    OPAClient,
    OrchestratorClient,
    PheromoneClient,
    PrometheusClient,
    RedisClient,
    ServiceRegistryClient,
)
from .clients.mcp_client import HTTPMCPClient, MCPClient
from .config import get_settings
from .consumers import ConsensusConsumer, IncidentConsumer, TelemetryConsumer
from .grpc_server import QueenAgentServicer
from .producers import StrategicDecisionProducer
from .proto import queen_agent_pb2_grpc
from .services import (
    ConflictArbitrator,
    ExceptionApprovalService,
    LeaderElection,
    LoadBalancer,
    MCPToolOrchestrator,
    ReplanningCoordinator,
    StrategicDecisionEngine,
    TelemetryAggregator,
)

if TYPE_CHECKING:
    from grpc import aio

# Configurar structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
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
        self.opa_client: OPAClient | None = None

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

        # MCP
        self.mcp_scout_client: MCPClient | None = None
        self.mcp_optimizer_client: MCPClient | None = None
        self.mcp_orchestrator: MCPToolOrchestrator | None = None

        # High Availability
        self.leader_election: LeaderElection | None = None
        self.load_balancer: LoadBalancer | None = None

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
                prometheus_port=settings.METRICS_PORT,
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

        # 2.5. Inicializar OPA Client (se habilitado)
        if settings.OPA_ENABLED:
            logger.info("initializing_opa_client")
            app_state.opa_client = OPAClient(
                base_url=settings.OPA_URL, timeout=settings.OPA_TIMEOUT_SECONDS
            )
            try:
                await app_state.opa_client.connect()
                logger.info("opa_client_connected")
            except Exception as e:
                if not settings.OPA_FAIL_OPEN:
                    logger.exception("opa_client_connection_failed_fail_closed", error=str(e))
                    raise
                else:
                    logger.warning("opa_client_connection_failed_fail_open", error=str(e))

        # 3. Inicializar serviços
        logger.info("initializing_services")

        app_state.replanning_coordinator = ReplanningCoordinator(
            app_state.orchestrator_client, app_state.redis_client, settings
        )

        app_state.decision_engine = StrategicDecisionEngine(
            app_state.mongodb_client,
            app_state.redis_client,
            app_state.neo4j_client,
            app_state.prometheus_client,
            app_state.pheromone_client,
            app_state.replanning_coordinator,
            app_state.opa_client,
            app_state.orchestrator_client,
            settings,
        )

        app_state.conflict_arbitrator = ConflictArbitrator(app_state.neo4j_client, settings)

        app_state.exception_service = ExceptionApprovalService(app_state.mongodb_client, settings)

        app_state.telemetry_aggregator = TelemetryAggregator(
            app_state.prometheus_client, app_state.redis_client, settings
        )

        # 3.5. Inicializar MCP Tool Orchestrator (se habilitado)
        if settings.MCP_ENABLED:
            logger.info("initializing_mcp_tool_orchestrator")

            # Criar clientes MCP - ambos usam HTTPMCPClient (REST API)
            app_state.mcp_scout_client = HTTPMCPClient(
                server_url=settings.MCP_SCOUT_URL, timeout=settings.MCP_TIMEOUT
            )
            app_state.mcp_optimizer_client = HTTPMCPClient(
                server_url=settings.MCP_OPTIMIZER_URL, timeout=settings.MCP_TIMEOUT
            )

            # Conectar aos servidores MCP
            await app_state.mcp_scout_client.connect()
            await app_state.mcp_optimizer_client.connect()

            # Criar orquestrador com clientes conectados
            app_state.mcp_orchestrator = MCPToolOrchestrator(
                scout_client=app_state.mcp_scout_client,
                optimizer_client=app_state.mcp_optimizer_client,
            )

            logger.info(
                "mcp_tool_orchestrator_initialized",
                scout_url=settings.MCP_SCOUT_URL,
                optimizer_url=settings.MCP_OPTIMIZER_URL,
            )

        # 3.5. Inicializar Leader Election (se habilitado)
        if settings.ELECTION_ENABLED:
            logger.info("initializing_leader_election")

            # Gerar node_id único se não configurado
            node_id = settings.ELECTION_NODE_ID
            if node_id == "queen-agent-1":
                # Adicionar timestamp para garantir unicidade
                import socket

                hostname = socket.gethostname()
                node_id = f"queen-agent-{hostname}-{settings.SERVICE_VERSION}"

            app_state.leader_election = LeaderElection(
                redis_client=app_state.redis_client,
                settings=settings,
                node_id=node_id,
            )
            await app_state.leader_election.start()

            logger.info(
                "leader_election_initialized",
                node_id=node_id,
                ttl=settings.ELECTION_LEASE_TTL_SECONDS,
            )

        # 3.6. Inicializar Load Balancer
        logger.info("initializing_load_balancer")

        app_state.load_balancer = LoadBalancer(
            redis_client=app_state.redis_client,
            service_registry_client=app_state.service_registry_client,
            settings=settings,
        )
        await app_state.load_balancer.start()

        logger.info(
            "load_balancer_initialized",
            strategy=settings.LOAD_BALANCER_STRATEGY,
        )

        # 4. Inicializar Kafka producer
        logger.info("initializing_kafka_producer")

        app_state.strategic_producer = StrategicDecisionProducer(settings)
        await app_state.strategic_producer.initialize()

        # 5. Inicializar Kafka consumers
        logger.info("initializing_kafka_consumers")

        app_state.consensus_consumer = ConsensusConsumer(
            settings, app_state.decision_engine, app_state.strategic_producer
        )
        await app_state.consensus_consumer.initialize()

        app_state.telemetry_consumer = TelemetryConsumer(
            settings, app_state.decision_engine, app_state.strategic_producer
        )
        await app_state.telemetry_consumer.initialize()

        app_state.incident_consumer = IncidentConsumer(
            settings,
            app_state.decision_engine,
            app_state.redis_client,
            app_state.strategic_producer,
        )
        await app_state.incident_consumer.initialize()

        # 6. Inicializar gRPC server
        logger.info("initializing_grpc_server")

        app_state.grpc_servicer = QueenAgentServicer(
            app_state.mongodb_client,
            app_state.neo4j_client,
            app_state.exception_service,
            app_state.telemetry_aggregator,
            app_state.decision_engine,
        )

        obs_config = ObservabilityConfig(
            service_name=settings.SERVICE_NAME,
            service_version=settings.SERVICE_VERSION,
            neural_hive_component="queen-agent",
            neural_hive_layer="coordination",
            environment=settings.ENVIRONMENT,
            otel_endpoint=settings.OTEL_EXPORTER_ENDPOINT,
        )
        app_state.grpc_server = create_instrumented_async_grpc_server(config=obs_config)
        queen_agent_pb2_grpc.add_QueenAgentServicer_to_server(
            app_state.grpc_servicer, app_state.grpc_server
        )

        # Configurar porta gRPC com suporte a mTLS
        grpc_port = settings.GRPC_PORT if hasattr(settings, "GRPC_PORT") else 50051

        if settings.SPIFFE_ENABLED and settings.SPIFFE_ENABLE_X509:
            try:
                from neural_hive_security import SPIFFEConfig, SPIFFEManager

                spiffe_config = SPIFFEConfig(
                    workload_api_socket=settings.SPIFFE_SOCKET_PATH,
                    trust_domain=settings.SPIFFE_TRUST_DOMAIN,
                    enable_x509=True,
                    environment=settings.ENVIRONMENT,
                )
                spiffe_manager = SPIFFEManager(spiffe_config)
                await spiffe_manager.initialize()

                server_credentials = await spiffe_manager.get_grpc_server_credentials()
                app_state.grpc_server.add_secure_port(f"[::]:{grpc_port}", server_credentials)
                logger.info("grpc_server_mtls_enabled", port=grpc_port)
            except ImportError:
                logger.warning("neural_hive_security_not_available", fallback="insecure_port")
                app_state.grpc_server.add_insecure_port(f"[::]:{grpc_port}")
            except Exception as e:
                logger.exception("grpc_mtls_setup_failed", error=str(e))
                if settings.ENVIRONMENT in ["production", "staging", "prod"]:
                    raise
                app_state.grpc_server.add_insecure_port(f"[::]:{grpc_port}")
        else:
            app_state.grpc_server.add_insecure_port(f"[::]:{grpc_port}")
            if settings.ENVIRONMENT in ["production", "staging", "prod"]:
                logger.warning("grpc_server_insecure_mode_in_production", port=grpc_port)

        # Iniciar servidor gRPC
        await app_state.grpc_server.start()
        logger.info("grpc_server_started", port=grpc_port, mtls=settings.SPIFFE_ENABLE_X509)

        # 7. Iniciar consumers em background
        logger.info("starting_kafka_consumers_background_tasks")

        app_state.consumer_tasks.append(asyncio.create_task(app_state.consensus_consumer.start()))
        app_state.consumer_tasks.append(asyncio.create_task(app_state.telemetry_consumer.start()))
        app_state.consumer_tasks.append(asyncio.create_task(app_state.incident_consumer.start()))

        logger.info("queen_agent_started_successfully")

    except Exception as e:
        logger.exception("queen_agent_startup_failed", error=str(e))
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

        # 3.5. Parar Load Balancer
        if app_state.load_balancer:
            logger.info("stopping_load_balancer")
            await app_state.load_balancer.stop()

        # 3.6. Parar Leader Election
        if app_state.leader_election:
            logger.info("stopping_leader_election")
            await app_state.leader_election.stop()

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
        if app_state.opa_client:
            await app_state.opa_client.close()

        # 6. Fechar clientes MCP
        if app_state.mcp_scout_client:
            await app_state.mcp_scout_client.disconnect()
        if app_state.mcp_optimizer_client:
            await app_state.mcp_optimizer_client.disconnect()

        logger.info("queen_agent_shutdown_complete")

    except Exception as e:
        logger.exception("queen_agent_shutdown_failed", error=str(e))


# Criar aplicação FastAPI
app = FastAPI(
    title="Queen Agent",
    description="Coordenador Estratégico do Neural Hive-Mind",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
)

# Injetar app_state para que os routers possam acessá-lo
app.state.app_state = app_state

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar routers
app.include_router(health_router)
app.include_router(decisions_router)
app.include_router(exceptions_router)
app.include_router(status_router)
app.include_router(mcp_router)
app.include_router(election_router)
app.include_router(workers_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,  # Usar objeto app diretamente em vez de string
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
