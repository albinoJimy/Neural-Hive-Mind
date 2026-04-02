import asyncio

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from redis.asyncio import Redis
from src.clients import (
    AnalystAgentGrpcClient,
    MongoDBClient,
    PheromoneClient,
    QueenAgentGrpcClient,
    SpecialistsGrpcClient,
)
from src.config import get_settings
from src.consumers import PlanConsumer
from src.producers import DecisionProducer

from neural_hive_api.health import HealthRouter
from neural_hive_observability import (
    init_observability,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)
from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.health import HealthChecker, HealthStatus
from neural_hive_observability.health_checks.otel import OTELPipelineHealthCheck

logger = structlog.get_logger()

# Configurações
settings = get_settings()

# Aplicação FastAPI
app = FastAPI(
    title="Consensus Engine",
    version="1.0.0",
    description="Mecanismo de Consenso Multi-Agente - Neural Hive-Mind",
)


# Estado global
class AppState:
    specialists_client: SpecialistsGrpcClient = None
    mongodb_client: MongoDBClient = None
    pheromone_client: PheromoneClient = None
    queen_agent_client: QueenAgentGrpcClient = None
    analyst_agent_client: AnalystAgentGrpcClient = None
    redis_client = None
    plan_consumer: PlanConsumer = None
    decision_producer: DecisionProducer = None
    decision_queue: asyncio.Queue = None
    consumer_task = None
    producer_task = None
    health_checker: HealthChecker = None

    # Health Router (neural_hive_api)
    health_router: HealthRouter = None


state = AppState()


@app.on_event("startup")
async def startup_event():
    """Inicialização da aplicação"""
    logger.info("Iniciando Consensus Engine", environment=settings.environment)

    init_observability(
        service_name="consensus-engine",
        service_version="1.0.0",
        neural_hive_component="consensus-engine",
        neural_hive_layer="cognitiva",
        neural_hive_domain="consensus",
        otel_endpoint=settings.otel_endpoint,
        prometheus_port=settings.prometheus_port,
    )

    # Initialize HealthChecker for OTEL pipeline validation
    observability_config = ObservabilityConfig(
        service_name="consensus-engine",
        service_version="1.0.0",
        neural_hive_component="consensus-engine",
        neural_hive_layer="cognitiva",
    )
    state.health_checker = HealthChecker(config=observability_config)

    # Register OTEL pipeline health check
    otel_health_check = OTELPipelineHealthCheck(
        otel_endpoint=settings.otel_endpoint,
        service_name="consensus-engine",
        name="otel_pipeline",
        timeout_seconds=5.0,
        verify_trace_export=True,
    )
    state.health_checker.register_check(otel_health_check)
    logger.info("otel_pipeline_health_check_registered", otel_endpoint=settings.otel_endpoint)

    # Initialize HealthRouter (neural_hive_api)
    state.health_router = HealthRouter("consensus-engine")
    state.health_router.add_route(app)
    logger.info("health_router_initialized")

    try:
        # Inicializar clientes
        # MongoDB
        state.mongodb_client = MongoDBClient(settings)
        await state.mongodb_client.initialize()
        logger.info("MongoDB client inicializado")

        # Redis
        redis_nodes = settings.redis_cluster_nodes.split(",")
        state.redis_client = Redis(
            host=redis_nodes[0].split(":")[0],
            port=int(redis_nodes[0].split(":")[1]) if ":" in redis_nodes[0] else 6379,
            password=settings.redis_password,
            ssl=settings.redis_ssl_enabled,
            decode_responses=True,
        )
        await state.redis_client.ping()
        state.pheromone_client = PheromoneClient(state.redis_client, settings)
        logger.info("Redis client inicializado")

        # gRPC Specialists
        state.specialists_client = SpecialistsGrpcClient(settings)
        await state.specialists_client.initialize()
        logger.info("Specialists gRPC client inicializado")

        # gRPC Queen Agent
        state.queen_agent_client = QueenAgentGrpcClient(settings)
        await state.queen_agent_client.initialize()
        logger.info("Queen Agent gRPC client inicializado")

        # gRPC Analyst Agent (OPTIONAL - don't fail startup if unavailable)
        try:
            state.analyst_agent_client = AnalystAgentGrpcClient(settings)
            await state.analyst_agent_client.initialize()
            logger.info("Analyst Agent gRPC client inicializado")
        except Exception as e:
            logger.warning(
                "Analyst Agent não disponível - continuando sem este serviço (opcional)",
                error=str(e),
            )
            state.analyst_agent_client = None

        # Inicializar fila de decisões
        state.decision_queue = asyncio.Queue()
        logger.info("Fila de decisões inicializada")

        # Inicializar Kafka consumer
        state.plan_consumer = PlanConsumer(
            settings, state.specialists_client, state.mongodb_client, state.pheromone_client
        )
        await state.plan_consumer.initialize()
        state.plan_consumer = instrument_kafka_consumer(state.plan_consumer)
        logger.info("Plan consumer inicializado")

        # Inicializar Kafka producer
        state.decision_producer = DecisionProducer(settings)
        await state.decision_producer.initialize()
        state.decision_producer = instrument_kafka_producer(state.decision_producer)
        logger.info("Decision producer inicializado")

        # Iniciar consumer em background
        state.consumer_task = asyncio.create_task(state.plan_consumer.start())
        logger.info("Plan consumer task iniciada")

        # Iniciar producer em background
        state.producer_task = asyncio.create_task(
            state.decision_producer.start(state.decision_queue)
        )
        logger.info("Decision producer task iniciada")

        logger.info("Consensus Engine iniciado com sucesso")

    except Exception as e:
        logger.error("Erro na inicialização", error=str(e), exc_info=True)
        # Cleanup parcial se houver erro
        if state.mongodb_client:
            try:
                await state.mongodb_client.close()
            except:
                pass
        if state.redis_client:
            try:
                await state.redis_client.close()
            except:
                pass
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Encerramento graceful"""
    logger.info("Encerrando Consensus Engine")

    # Parar consumer e producer
    if state.plan_consumer:
        await state.plan_consumer.stop()

    if state.decision_producer:
        await state.decision_producer.stop()

    # Aguardar tasks terminarem
    if state.consumer_task:
        state.consumer_task.cancel()
        try:
            await state.consumer_task
        except asyncio.CancelledError:
            pass

    if state.producer_task:
        state.producer_task.cancel()
        try:
            await state.producer_task
        except asyncio.CancelledError:
            pass

    # Fechar clientes
    if state.analyst_agent_client:
        await state.analyst_agent_client.close()

    if state.queen_agent_client:
        await state.queen_agent_client.close()

    if state.specialists_client:
        await state.specialists_client.close()

    if state.mongodb_client:
        await state.mongodb_client.close()

    if state.redis_client:
        await state.redis_client.close()

    logger.info("Consensus Engine encerrado")



@app.get("/api/v1/decisions/{decision_id}")
async def get_decision(decision_id: str):
    """Consultar decisão consolidada por ID"""
    try:
        decision = await state.mongodb_client.get_decision(decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decisão não encontrada")
        return decision
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro consultando decisão", decision_id=decision_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/decisions/by-plan/{plan_id}")
async def get_decision_by_plan(plan_id: str):
    """Consultar decisão por plan_id"""
    try:
        decision = await state.mongodb_client.get_decision_by_plan(plan_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decisão não encontrada")
        return decision
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro consultando decisão por plan", plan_id=plan_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/pheromones/stats")
async def get_pheromone_stats():
    """Estatísticas de feromônios"""
    # Implementar quando PheromoneClient estiver completo
    return {"message": "Pheromone stats endpoint - implementação em progresso", "available": False}


# Montar métricas Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, workers=4)
