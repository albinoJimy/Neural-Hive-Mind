"""
Ponto de entrada principal do serviço Orchestrator Dynamic.
Implementa FastAPI para API REST e gerencia lifecycle do Temporal Worker e Kafka Consumer.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from src.config import get_settings
from src.consumers.decision_consumer import DecisionConsumer
from src.workers.temporal_worker import TemporalWorkerManager, create_temporal_client
from src.clients.mongodb_client import MongoDBClient
from src.clients.kafka_producer import KafkaProducerClient
from src.integration.flow_c_consumer import FlowCConsumer


# Configurar logger estruturado
logger = structlog.get_logger()


class AppState:
    """Gerencia estado global da aplicação."""

    def __init__(self):
        self.temporal_client = None
        self.kafka_consumer: Optional[DecisionConsumer] = None
        self.flow_c_consumer: Optional[FlowCConsumer] = None
        self.temporal_worker: Optional[TemporalWorkerManager] = None
        self.worker_task: Optional[asyncio.Task] = None
        self.consumer_task: Optional[asyncio.Task] = None
        self.flow_c_task: Optional[asyncio.Task] = None
        self.mongodb_client: Optional[MongoDBClient] = None
        self.kafka_producer: Optional[KafkaProducerClient] = None
        self.redis_client = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia lifecycle da aplicação (startup/shutdown).
    """
    config = get_settings()

    # Startup
    logger.info(
        'Inicializando Orchestrator Dynamic',
        service=config.service_name,
        version=config.service_version,
        environment=config.environment
    )

    try:
        # Inicializar MongoDB
        logger.info('Conectando ao MongoDB', uri=config.mongodb_uri)
        app_state.mongodb_client = MongoDBClient(config)
        await app_state.mongodb_client.initialize()
        logger.info('MongoDB conectado com sucesso')

        # Inicializar Kafka Producer
        logger.info('Inicializando Kafka Producer', topic=config.kafka_tickets_topic)
        app_state.kafka_producer = KafkaProducerClient(config)
        await app_state.kafka_producer.initialize()
        logger.info('Kafka Producer inicializado com sucesso')

        # Conectar ao Temporal Server
        logger.info('Conectando ao Temporal Server', host=config.temporal_host, port=config.temporal_port)
        app_state.temporal_client = await create_temporal_client(config)
        logger.info('Conectado ao Temporal Server com sucesso')

        # Inicializar Kafka Consumer
        logger.info('Inicializando Kafka Consumer', topic=config.kafka_consensus_topic)
        app_state.kafka_consumer = DecisionConsumer(
            config,
            app_state.temporal_client,
            app_state.mongodb_client
        )
        await app_state.kafka_consumer.initialize()

        # Inicializar Temporal Worker com dependências
        logger.info('Inicializando Temporal Worker', task_queue=config.temporal_task_queue)
        app_state.temporal_worker = TemporalWorkerManager(
            config,
            app_state.temporal_client,
            app_state.kafka_producer,
            app_state.mongodb_client
        )
        await app_state.temporal_worker.initialize()

        # Iniciar Temporal Worker em background
        app_state.worker_task = asyncio.create_task(app_state.temporal_worker.start())
        logger.info('Temporal Worker iniciado em background')

        # Iniciar Kafka Consumer em background
        app_state.consumer_task = asyncio.create_task(app_state.kafka_consumer.start())
        logger.info('Kafka Consumer iniciado em background')

        # Inicializar Flow C Consumer
        logger.info('Inicializando Flow C Consumer')
        app_state.flow_c_consumer = FlowCConsumer()
        await app_state.flow_c_consumer.start()

        # Iniciar Flow C Consumer em background
        app_state.flow_c_task = asyncio.create_task(app_state.flow_c_consumer.consume())
        logger.info('Flow C Consumer iniciado em background')

        logger.info('Orchestrator Dynamic inicializado com sucesso')

    except Exception as e:
        logger.error('Erro ao inicializar Orchestrator Dynamic', error=str(e), exc_info=True)
        raise

    yield

    # Shutdown
    logger.info('Encerrando Orchestrator Dynamic')

    try:
        # Parar Flow C Consumer
        if app_state.flow_c_consumer:
            logger.info('Parando Flow C Consumer')
            await app_state.flow_c_consumer.stop()

        # Parar Kafka Consumer
        if app_state.kafka_consumer:
            logger.info('Parando Kafka Consumer')
            await app_state.kafka_consumer.stop()

        # Parar Temporal Worker
        if app_state.temporal_worker:
            logger.info('Parando Temporal Worker')
            await app_state.temporal_worker.stop()

        # Cancelar background tasks
        if app_state.flow_c_task:
            app_state.flow_c_task.cancel()
            try:
                await app_state.flow_c_task
            except asyncio.CancelledError:
                pass

        if app_state.consumer_task:
            app_state.consumer_task.cancel()
            try:
                await app_state.consumer_task
            except asyncio.CancelledError:
                pass

        if app_state.worker_task:
            app_state.worker_task.cancel()
            try:
                await app_state.worker_task
            except asyncio.CancelledError:
                pass

        # Fechar Kafka Producer
        if app_state.kafka_producer:
            logger.info('Fechando Kafka Producer')
            await app_state.kafka_producer.close()

        # Fechar MongoDB
        if app_state.mongodb_client:
            logger.info('Fechando MongoDB client')
            await app_state.mongodb_client.close()

        logger.info('Orchestrator Dynamic encerrado com sucesso')

    except Exception as e:
        logger.error('Erro ao encerrar Orchestrator Dynamic', error=str(e), exc_info=True)


# Criar aplicação FastAPI
app = FastAPI(
    title='Orchestrator Dynamic',
    version='1.0.0',
    description='Orquestrador Dinâmico do Neural Hive-Mind usando Temporal',
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Montar métricas Prometheus
metrics_app = make_asgi_app()
app.mount('/metrics', metrics_app)


@app.get('/health')
async def health_check():
    """Health check básico."""
    return JSONResponse(
        status_code=200,
        content={
            'status': 'healthy',
            'service': 'orchestrator-dynamic',
            'version': '1.0.0'
        }
    )


@app.get('/ready')
async def readiness_check():
    """
    Readiness check - verifica se serviço está pronto para receber requisições.
    Valida conexões com Temporal, Kafka e MongoDB.
    """
    checks = {
        'temporal': False,
        'kafka_consumer': False,
        'worker': False
    }

    try:
        # Verificar Temporal Client
        if app_state.temporal_client:
            checks['temporal'] = True

        # Verificar Kafka Consumer
        if app_state.kafka_consumer and app_state.kafka_consumer.running:
            checks['kafka_consumer'] = True

        # Verificar Temporal Worker
        if app_state.temporal_worker and app_state.temporal_worker.running:
            checks['worker'] = True

        # Verificar Flow C Consumer
        checks['flow_c_consumer'] = False
        if app_state.flow_c_consumer and app_state.flow_c_consumer.running:
            checks['flow_c_consumer'] = True

        all_ready = all(checks.values())

        return JSONResponse(
            status_code=200 if all_ready else 503,
            content={
                'status': 'ready' if all_ready else 'not_ready',
                'checks': checks
            }
        )

    except Exception as e:
        logger.error('Erro no readiness check', error=str(e), exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                'status': 'error',
                'error': str(e)
            }
        )


@app.get('/api/v1/tickets/{ticket_id}')
async def get_ticket(ticket_id: str):
    """Consultar ticket por ID."""
    # Implementação futura: consultar MongoDB
    raise HTTPException(status_code=501, detail='Not implemented')


@app.get('/api/v1/tickets/by-plan/{plan_id}')
async def get_tickets_by_plan(plan_id: str):
    """Listar tickets de um plano."""
    # Implementação futura: consultar MongoDB
    raise HTTPException(status_code=501, detail='Not implemented')


@app.get('/api/v1/flow-c/status')
async def get_flow_c_status():
    """
    Retorna estatísticas de execução do Flow C agregadas do MongoDB.
    """
    try:
        if not app_state.mongodb_client:
            raise HTTPException(status_code=503, detail="MongoDB não inicializado")

        db = app_state.mongodb_client.db
        collection = db['flow_c_executions']

        # Agregação de métricas usando MongoDB pipeline
        pipeline = [
            {
                '$facet': {
                    'total': [{'$count': 'count'}],
                    'success': [
                        {'$match': {'status': 'completed'}},
                        {'$count': 'count'}
                    ],
                    'latency': [
                        {'$match': {'total_duration_ms': {'$exists': True}}},
                        {
                            '$group': {
                                '_id': None,
                                'avg': {'$avg': '$total_duration_ms'},
                                'durations': {'$push': '$total_duration_ms'}
                            }
                        }
                    ],
                    'active': [
                        {'$match': {'status': {'$in': ['running', 'in_progress']}}},
                        {'$count': 'count'}
                    ]
                }
            }
        ]

        result = await collection.aggregate(pipeline).to_list(1)

        if result:
            data = result[0]
            total = data['total'][0]['count'] if data['total'] else 0
            success = data['success'][0]['count'] if data['success'] else 0
            success_rate = (success / total * 100) if total > 0 else 0.0

            # Calcular p95 latency
            avg_latency = 0
            p95_latency = 0
            if data['latency'] and data['latency'][0]['durations']:
                durations = sorted(data['latency'][0]['durations'])
                avg_latency = int(data['latency'][0]['avg'])
                p95_index = int(len(durations) * 0.95)
                p95_latency = durations[p95_index] if p95_index < len(durations) else durations[-1]

            active = data['active'][0]['count'] if data['active'] else 0

            return JSONResponse(
                status_code=200,
                content={
                    'total_processed': total,
                    'success_rate': round(success_rate, 2),
                    'average_latency_ms': avg_latency,
                    'p95_latency_ms': p95_latency,
                    'active_executions': active,
                }
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    'total_processed': 0,
                    'success_rate': 0.0,
                    'average_latency_ms': 0,
                    'p95_latency_ms': 0,
                    'active_executions': 0,
                }
            )

    except Exception as e:
        logger.error('flow_c_status_error', error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro ao obter status: {str(e)}")


@app.get('/api/v1/workflows/{workflow_id}')
async def get_workflow_status(workflow_id: str):
    """Consultar status de workflow Temporal."""
    # Implementação futura: consultar Temporal
    raise HTTPException(status_code=501, detail='Not implemented')


if __name__ == '__main__':
    import uvicorn

    config = get_settings()

    uvicorn.run(
        'src.main:app',
        host='0.0.0.0',
        port=8000,
        log_level=config.log_level.lower(),
        reload=config.environment == 'development'
    )
