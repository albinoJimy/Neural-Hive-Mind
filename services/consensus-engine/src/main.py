import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
import structlog
from redis.asyncio import Redis
from src.config import get_settings
from src.clients import SpecialistsGrpcClient, PheromoneClient, MongoDBClient
from src.observability import ConsensusMetrics
from src.consumers import PlanConsumer
from src.producers import DecisionProducer

logger = structlog.get_logger()

# Configurações
settings = get_settings()

# Aplicação FastAPI
app = FastAPI(
    title='Consensus Engine',
    version='1.0.0',
    description='Mecanismo de Consenso Multi-Agente - Neural Hive-Mind'
)

# Estado global
class AppState:
    specialists_client: SpecialistsGrpcClient = None
    mongodb_client: MongoDBClient = None
    pheromone_client: PheromoneClient = None
    redis_client = None
    plan_consumer: PlanConsumer = None
    decision_producer: DecisionProducer = None
    decision_queue: asyncio.Queue = None
    consumer_task = None
    producer_task = None

state = AppState()


@app.on_event('startup')
async def startup_event():
    '''Inicialização da aplicação'''
    logger.info('Iniciando Consensus Engine', environment=settings.environment)

    try:
        # Inicializar clientes
        # MongoDB
        state.mongodb_client = MongoDBClient(settings)
        await state.mongodb_client.initialize()
        logger.info('MongoDB client inicializado')

        # Redis
        redis_nodes = settings.redis_cluster_nodes.split(',')
        state.redis_client = Redis(
            host=redis_nodes[0].split(':')[0],
            port=int(redis_nodes[0].split(':')[1]) if ':' in redis_nodes[0] else 6379,
            password=settings.redis_password,
            ssl=settings.redis_ssl_enabled,
            decode_responses=True
        )
        await state.redis_client.ping()
        state.pheromone_client = PheromoneClient(state.redis_client, settings)
        logger.info('Redis client inicializado')

        # gRPC Specialists
        state.specialists_client = SpecialistsGrpcClient(settings)
        await state.specialists_client.initialize()
        logger.info('Specialists gRPC client inicializado')

        # Inicializar fila de decisões
        state.decision_queue = asyncio.Queue()
        logger.info('Fila de decisões inicializada')

        # Inicializar Kafka consumer
        state.plan_consumer = PlanConsumer(
            settings,
            state.specialists_client,
            state.mongodb_client,
            state.pheromone_client
        )
        await state.plan_consumer.initialize()
        logger.info('Plan consumer inicializado')

        # Inicializar Kafka producer
        state.decision_producer = DecisionProducer(settings)
        await state.decision_producer.initialize()
        logger.info('Decision producer inicializado')

        # Iniciar consumer em background
        state.consumer_task = asyncio.create_task(state.plan_consumer.start())
        logger.info('Plan consumer task iniciada')

        # Iniciar producer em background
        state.producer_task = asyncio.create_task(
            state.decision_producer.start(state.decision_queue)
        )
        logger.info('Decision producer task iniciada')

        logger.info('Consensus Engine iniciado com sucesso')

    except Exception as e:
        logger.error('Erro na inicialização', error=str(e))
        raise


@app.on_event('shutdown')
async def shutdown_event():
    '''Encerramento graceful'''
    logger.info('Encerrando Consensus Engine')

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
    if state.specialists_client:
        await state.specialists_client.close()

    if state.mongodb_client:
        await state.mongodb_client.close()

    if state.redis_client:
        await state.redis_client.close()

    logger.info('Consensus Engine encerrado')


@app.get('/health')
async def health():
    '''Health check básico'''
    return {'status': 'healthy', 'service': 'consensus-engine'}


@app.get('/ready')
async def readiness():
    '''Readiness check'''
    checks = {
        'mongodb': False,
        'specialists': False,
        'redis': False
    }

    try:
        # Verificar MongoDB
        if state.mongodb_client and state.mongodb_client.client:
            await state.mongodb_client.client.admin.command('ping')
            checks['mongodb'] = True

        # Verificar especialistas
        if state.specialists_client:
            health_results = await state.specialists_client.health_check_all()
            all_healthy = all(
                result.get('status') != 'NOT_SERVING'
                for result in health_results.values()
            )
            checks['specialists'] = all_healthy

        # Verificar Redis
        if state.redis_client:
            await state.redis_client.ping()
            checks['redis'] = True

        all_ready = all(checks.values())

        return {
            'ready': all_ready,
            'checks': checks
        }

    except Exception as e:
        logger.error('Erro no readiness check', error=str(e))
        return JSONResponse(
            status_code=503,
            content={'ready': False, 'checks': checks, 'error': str(e)}
        )


@app.get('/api/v1/decisions/{decision_id}')
async def get_decision(decision_id: str):
    '''Consultar decisão consolidada por ID'''
    try:
        decision = await state.mongodb_client.get_decision(decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail='Decisão não encontrada')
        return decision
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Erro consultando decisão', decision_id=decision_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/v1/decisions/by-plan/{plan_id}')
async def get_decision_by_plan(plan_id: str):
    '''Consultar decisão por plan_id'''
    try:
        decision = await state.mongodb_client.get_decision_by_plan(plan_id)
        if not decision:
            raise HTTPException(status_code=404, detail='Decisão não encontrada')
        return decision
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Erro consultando decisão por plan', plan_id=plan_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/v1/pheromones/stats')
async def get_pheromone_stats():
    '''Estatísticas de feromônios'''
    # Implementar quando PheromoneClient estiver completo
    return {
        'message': 'Pheromone stats endpoint - implementação em progresso',
        'available': False
    }


# Montar métricas Prometheus
metrics_app = make_asgi_app()
app.mount('/metrics', metrics_app)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, workers=4)
