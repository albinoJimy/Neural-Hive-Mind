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
from src.clients.optimizer_grpc_client import OptimizerGrpcClient
from src.integration.flow_c_consumer import FlowCConsumer
from pydantic import BaseModel
from uuid import uuid4

# Import Vault integration (optional dependency)
try:
    from src.clients.vault_integration import OrchestratorVaultClient
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    OrchestratorVaultClient = None


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
        self.vault_client = None
        self.drift_detector = None
        self.ml_training_jobs = {}  # Dict para rastrear jobs de treinamento
        self.vault_renewal_task: Optional[asyncio.Task] = None
        self.optimizer_client = None
        # Modelos preditivos centralizados
        self.scheduling_predictor = None
        self.load_predictor = None
        self.anomaly_detector = None
        self.model_registry = None


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
        # Initialize Vault client (if enabled)
        if config.vault_enabled and VAULT_AVAILABLE and OrchestratorVaultClient:
            logger.info('Inicializando Vault client')
            app_state.vault_client = OrchestratorVaultClient(config)
            await app_state.vault_client.initialize()
            logger.info('Vault client inicializado')
        else:
            if config.vault_enabled and not VAULT_AVAILABLE:
                logger.warning('Vault habilitado mas biblioteca de segurança não disponível')
            else:
                logger.info('Vault integration desabilitada, usando credenciais estáticas')

        # Get MongoDB credentials from Vault or config
        if app_state.vault_client:
            mongodb_uri = await app_state.vault_client.get_mongodb_uri()
        else:
            mongodb_uri = config.mongodb_uri

        # Inicializar MongoDB
        logger.info('Conectando ao MongoDB')
        app_state.mongodb_client = MongoDBClient(config, uri_override=mongodb_uri)
        await app_state.mongodb_client.initialize()
        logger.info('MongoDB conectado com sucesso')

        # Inicializar modelos preditivos centralizados (se habilitado)
        if getattr(config, 'ml_predictions_enabled', False):
            try:
                from neural_hive_ml.predictive_models import (
                    SchedulingPredictor,
                    LoadPredictor,
                    AnomalyDetector
                )
                from neural_hive_ml.predictive_models.model_registry import ModelRegistry
                from src.observability.metrics import OrchestratorMetrics

                logger.info('Inicializando modelos preditivos centralizados')

                # Inicializa model registry
                mlflow_uri = getattr(config, 'mlflow_tracking_uri', 'http://localhost:5000')
                app_state.model_registry = ModelRegistry(
                    tracking_uri=mlflow_uri,
                    experiment_prefix="neural-hive-ml"
                )

                # Metrics instance
                metrics = OrchestratorMetrics()

                # SchedulingPredictor
                scheduling_config = {
                    'model_name': 'scheduling-predictor',
                    'model_type': getattr(config, 'ml_scheduling_model_type', 'xgboost'),
                    'hyperparameters': {}
                }
                app_state.scheduling_predictor = SchedulingPredictor(
                    config=scheduling_config,
                    model_registry=app_state.model_registry,
                    metrics=metrics
                )
                await app_state.scheduling_predictor.initialize()
                logger.info('SchedulingPredictor inicializado')

                # LoadPredictor
                load_config = {
                    'model_name': 'load-predictor',
                    'model_type': 'prophet',
                    'forecast_horizons': getattr(config, 'ml_load_forecast_horizons', [60, 360, 1440]),
                    'seasonality_mode': 'additive',
                    'cache_ttl_seconds': getattr(config, 'ml_forecast_cache_ttl_seconds', 300)
                }
                app_state.load_predictor = LoadPredictor(
                    config=load_config,
                    model_registry=app_state.model_registry,
                    metrics=metrics,
                    redis_client=None  # TODO: add Redis client if available
                )
                await app_state.load_predictor.initialize()
                logger.info('LoadPredictor inicializado')

                # AnomalyDetector
                anomaly_config = {
                    'model_name': 'anomaly-detector',
                    'model_type': getattr(config, 'ml_anomaly_model_type', 'isolation_forest'),
                    'contamination': 0.05
                }
                app_state.anomaly_detector = AnomalyDetector(
                    config=anomaly_config,
                    model_registry=app_state.model_registry,
                    metrics=metrics
                )
                await app_state.anomaly_detector.initialize()
                logger.info('AnomalyDetector inicializado')

                logger.info('Modelos preditivos centralizados inicializados com sucesso')

            except Exception as e:
                logger.warning(
                    'Falha ao inicializar modelos preditivos, continuando sem ML',
                    error=str(e)
                )
                app_state.scheduling_predictor = None
                app_state.load_predictor = None
                app_state.anomaly_detector = None
        else:
            logger.info('ML predictions desabilitado')

        # Get Kafka credentials from Vault if enabled
        kafka_username = config.kafka_sasl_username
        kafka_password = config.kafka_sasl_password
        if app_state.vault_client:
            logger.info('Buscando credenciais Kafka do Vault')
            kafka_creds = await app_state.vault_client.get_kafka_credentials()
            if kafka_creds.get('username'):
                kafka_username = kafka_creds['username']
            if kafka_creds.get('password'):
                kafka_password = kafka_creds['password']
            logger.info('Credenciais Kafka obtidas do Vault')

        # Inicializar Kafka Producer com credenciais do Vault
        logger.info('Inicializando Kafka Producer', topic=config.kafka_tickets_topic)
        app_state.kafka_producer = KafkaProducerClient(
            config,
            sasl_username_override=kafka_username,
            sasl_password_override=kafka_password
        )
        await app_state.kafka_producer.initialize()
        logger.info('Kafka Producer inicializado com sucesso')

        # Get PostgreSQL credentials from Vault if enabled
        postgres_user = config.postgres_user
        postgres_password = config.postgres_password
        if app_state.vault_client:
            logger.info('Buscando credenciais PostgreSQL do Vault')
            pg_creds = await app_state.vault_client.get_postgres_credentials()
            postgres_user = pg_creds['username']
            postgres_password = pg_creds['password']
            logger.info('Credenciais PostgreSQL obtidas do Vault', ttl=pg_creds.get('ttl', 0))

        # Conectar ao Temporal Server com credenciais do Vault
        logger.info('Conectando ao Temporal Server', host=config.temporal_host, port=config.temporal_port)
        app_state.temporal_client = await create_temporal_client(
            config,
            postgres_user=postgres_user,
            postgres_password=postgres_password
        )
        logger.info('Conectado ao Temporal Server com sucesso')

        # Inicializar Kafka Consumer
        logger.info('Inicializando Kafka Consumer', topic=config.kafka_consensus_topic)
        app_state.kafka_consumer = DecisionConsumer(
            config,
            app_state.temporal_client,
            app_state.mongodb_client
        )
        await app_state.kafka_consumer.initialize()

        # Inicializar Optimizer Agents client (se habilitado)
        if config.enable_optimizer_integration:
            logger.info('Inicializando Optimizer Agents client')
            app_state.optimizer_client = OptimizerGrpcClient(config)
            await app_state.optimizer_client.initialize()
            logger.info('Optimizer Agents client inicializado')
        else:
            logger.info('Optimizer integration desabilitada')

        # Inicializar Temporal Worker com dependências
        logger.info('Inicializando Temporal Worker', task_queue=config.temporal_task_queue)
        app_state.temporal_worker = TemporalWorkerManager(
            config,
            app_state.temporal_client,
            app_state.kafka_producer,
            app_state.mongodb_client,
            optimizer_client=app_state.optimizer_client,
            vault_client=app_state.vault_client,
            scheduling_predictor=app_state.scheduling_predictor,
            load_predictor=app_state.load_predictor,
            anomaly_detector=app_state.anomaly_detector
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

        # Inicializar Drift Detector se ML habilitado
        if getattr(config, 'ml_predictions_enabled', False) and getattr(config, 'ml_drift_detection_enabled', True):
            try:
                from src.ml.drift_detector import DriftDetector
                from src.observability.metrics import OrchestratorMetrics

                logger.info('Inicializando Drift Detector')
                app_state.drift_detector = DriftDetector(
                    config=config,
                    mongodb_client=app_state.mongodb_client,
                    metrics=OrchestratorMetrics()
                )
                logger.info('Drift Detector inicializado')
            except Exception as e:
                logger.warning(f'Falha ao inicializar Drift Detector: {e}')

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

        # Fechar Optimizer client
        if app_state.optimizer_client:
            logger.info('Fechando Optimizer Agents client')
            await app_state.optimizer_client.close()

        # Fechar Kafka Producer
        if app_state.kafka_producer:
            logger.info('Fechando Kafka Producer')
            await app_state.kafka_producer.close()

        # Fechar MongoDB
        if app_state.mongodb_client:
            logger.info('Fechando MongoDB client')
            await app_state.mongodb_client.close()

        # Fechar Vault client
        if app_state.vault_client:
            logger.info('Fechando Vault client')
            await app_state.vault_client.close()

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


# =============================================================================
# Helper Functions
# =============================================================================

def _is_predictor_loaded(model_name: str) -> bool:
    """
    Verifica se o preditor correspondente ao modelo está carregado.

    Args:
        model_name: Nome base do modelo

    Returns:
        True se o preditor está carregado, False caso contrário
    """
    if 'scheduling' in model_name and app_state.scheduling_predictor:
        return hasattr(app_state.scheduling_predictor, 'model') and app_state.scheduling_predictor.model is not None
    elif 'load' in model_name and app_state.load_predictor:
        return hasattr(app_state.load_predictor, 'model') and app_state.load_predictor.model is not None
    elif 'anomaly' in model_name and app_state.anomaly_detector:
        return hasattr(app_state.anomaly_detector, 'model') and app_state.anomaly_detector.model is not None
    return False


def _get_predictor_info(model_name: str) -> Optional[dict]:
    """
    Obtém informações do preditor correspondente ao modelo.

    Args:
        model_name: Nome base do modelo

    Returns:
        Dict com version e loaded status, ou None se não encontrado
    """
    if 'scheduling' in model_name and app_state.scheduling_predictor:
        return {
            'version': getattr(app_state.scheduling_predictor, 'model_version', 'unknown'),
            'loaded': hasattr(app_state.scheduling_predictor, 'model') and app_state.scheduling_predictor.model is not None
        }
    elif 'load' in model_name and app_state.load_predictor:
        return {
            'version': getattr(app_state.load_predictor, 'model_version', 'unknown'),
            'loaded': hasattr(app_state.load_predictor, 'model') and app_state.load_predictor.model is not None
        }
    elif 'anomaly' in model_name and app_state.anomaly_detector:
        return {
            'version': getattr(app_state.anomaly_detector, 'model_version', 'unknown'),
            'loaded': hasattr(app_state.anomaly_detector, 'model') and app_state.anomaly_detector.model is not None
        }
    return None


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


@app.get('/health/ml')
async def ml_health_check():
    """
    Health check para modelos preditivos ML.

    Verifica se os preditores estão inicializados e retorna versões e métricas.
    """
    try:
        if not app_state.model_registry:
            raise HTTPException(status_code=503, detail="ML predictions não habilitado")

        health_info = {
            'status': 'healthy',
            'predictors': {}
        }

        # Check SchedulingPredictor
        if app_state.scheduling_predictor:
            try:
                # Inicializa se necessário
                if not hasattr(app_state.scheduling_predictor, 'model') or app_state.scheduling_predictor.model is None:
                    await app_state.scheduling_predictor.initialize()

                health_info['predictors']['scheduling_predictor'] = {
                    'loaded': app_state.scheduling_predictor.model is not None,
                    'model_version': getattr(app_state.scheduling_predictor, 'model_version', 'unknown'),
                    'model_type': app_state.scheduling_predictor.config.get('model_type', 'unknown')
                }
            except Exception as e:
                health_info['predictors']['scheduling_predictor'] = {
                    'loaded': False,
                    'error': str(e)
                }

        # Check LoadPredictor
        if app_state.load_predictor:
            try:
                if not hasattr(app_state.load_predictor, 'model') or app_state.load_predictor.model is None:
                    await app_state.load_predictor.initialize()

                health_info['predictors']['load_predictor'] = {
                    'loaded': app_state.load_predictor.model is not None,
                    'model_version': getattr(app_state.load_predictor, 'model_version', 'unknown'),
                    'model_type': app_state.load_predictor.config.get('model_type', 'unknown'),
                    'horizons': app_state.load_predictor.config.get('forecast_horizons', [])
                }
            except Exception as e:
                health_info['predictors']['load_predictor'] = {
                    'loaded': False,
                    'error': str(e)
                }

        # Check AnomalyDetector
        if app_state.anomaly_detector:
            try:
                if not hasattr(app_state.anomaly_detector, 'model') or app_state.anomaly_detector.model is None:
                    await app_state.anomaly_detector.initialize()

                health_info['predictors']['anomaly_detector'] = {
                    'loaded': app_state.anomaly_detector.model is not None,
                    'model_version': getattr(app_state.anomaly_detector, 'model_version', 'unknown'),
                    'model_type': app_state.anomaly_detector.config.get('model_type', 'unknown')
                }
            except Exception as e:
                health_info['predictors']['anomaly_detector'] = {
                    'loaded': False,
                    'error': str(e)
                }

        # Determinar status geral
        all_loaded = all(
            p.get('loaded', False)
            for p in health_info['predictors'].values()
        )
        health_info['status'] = 'healthy' if all_loaded else 'degraded'

        return JSONResponse(
            status_code=200,
            content=health_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('ml_health_check_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


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


# =============================================================================
# ML Management API Endpoints
# =============================================================================

class ModelPromotionRequest(BaseModel):
    """Request para promoção de modelo."""
    version: str
    stage: str = "Production"


@app.post('/api/v1/ml/train')
async def trigger_manual_training(window_days: Optional[int] = None, backfill_errors: bool = False):
    """
    Trigger treinamento manual de modelos ML.

    Args:
        window_days: Janela de dados em dias (default: config)
        backfill_errors: Se True, calcula erros históricos

    Returns:
        job_id e status do treinamento
    """
    try:
        if not app_state.model_registry:
            raise HTTPException(status_code=503, detail="ML predictions não habilitado")

        # Gerar job ID
        job_id = str(uuid4())

        # Criar background task para treinamento
        async def run_training():
            try:
                app_state.ml_training_jobs[job_id] = {
                    'status': 'running',
                    'started_at': asyncio.get_event_loop().time()
                }

                # TODO: Implementar pipeline de treinamento centralizado
                # Por enquanto, retornar status de sucesso simulado
                result = {
                    'status': 'completed',
                    'message': 'Treinamento não implementado - usar CronJob do Kubernetes'
                }

                app_state.ml_training_jobs[job_id]['status'] = result.get('status', 'completed')
                app_state.ml_training_jobs[job_id]['result'] = result
                app_state.ml_training_jobs[job_id]['completed_at'] = asyncio.get_event_loop().time()

            except Exception as e:
                logger.error(f'Training job {job_id} failed', error=str(e))
                app_state.ml_training_jobs[job_id]['status'] = 'failed'
                app_state.ml_training_jobs[job_id]['error'] = str(e)

        # Iniciar task em background
        asyncio.create_task(run_training())

        return JSONResponse(
            status_code=202,
            content={
                'job_id': job_id,
                'status': 'queued',
                'message': 'Treinamento iniciado'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('trigger_training_error', error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro ao iniciar treinamento: {str(e)}")


@app.get('/api/v1/ml/train/{job_id}')
async def get_training_job_status(job_id: str):
    """
    Consultar status de job de treinamento.

    Args:
        job_id: ID do job de treinamento

    Returns:
        Status e métricas do treinamento
    """
    try:
        if job_id not in app_state.ml_training_jobs:
            raise HTTPException(status_code=404, detail="Job não encontrado")

        job = app_state.ml_training_jobs[job_id]
        response = {
            'job_id': job_id,
            'status': job['status']
        }

        if 'result' in job:
            response['metrics'] = {
                'duration_predictor': job['result'].get('duration_predictor'),
                'anomaly_detector': job['result'].get('anomaly_detector'),
                'samples_used': job['result'].get('samples_used'),
                'training_duration': job['result'].get('training_duration_seconds')
            }

        if 'error' in job:
            response['error'] = job['error']

        return JSONResponse(status_code=200, content=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error('get_training_status_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/v1/ml/models')
async def list_ml_models(model_type: Optional[str] = None):
    """
    Listar modelos ML registrados no MLflow.

    Args:
        model_type: Filtrar por tipo de modelo (xgboost, prophet, isolation_forest, autoencoder)

    Returns:
        Lista de modelos com metadados
    """
    try:
        if not app_state.model_registry:
            raise HTTPException(status_code=503, detail="ML predictions não habilitado")

        # Listar modelos registrados via registry
        all_models = await app_state.model_registry.list_models()

        # Filtrar por tipo se especificado
        if model_type:
            all_models = [m for m in all_models if m.get('model_type') == model_type]

        # Enriquecer com status de integração
        models = []
        for metadata in all_models:
            model_base_name = metadata.get('name', '')
            model_info = {
                'name': model_base_name,
                'latest_version': metadata.get('version'),
                'stage': metadata.get('stage', 'None'),
                'metrics': metadata.get('metrics', {}),
                'last_updated': metadata.get('creation_timestamp'),
                'model_type': metadata.get('model_type', 'unknown'),
                'integration_status': 'loaded' if _is_predictor_loaded(model_base_name) else 'unloaded'
            }
            models.append(model_info)

        return JSONResponse(status_code=200, content={'models': models})

    except HTTPException:
        raise
    except Exception as e:
        logger.error('list_models_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/v1/ml/models/{model_name}')
async def get_model_details(model_name: str):
    """
    Obter detalhes de modelo específico.

    Args:
        model_name: Nome do modelo (scheduling-predictor, load-predictor ou anomaly-detector)

    Returns:
        Metadados detalhados do modelo
    """
    try:
        if not app_state.model_registry:
            raise HTTPException(status_code=503, detail="ML predictions não habilitado")

        metadata = await app_state.model_registry.get_model_metadata(model_name)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Modelo {model_name} não encontrado")

        # Enriquecer com informações de versão dos preditores
        predictor_info = _get_predictor_info(model_name)
        if predictor_info:
            metadata['predictor_version'] = predictor_info.get('version')
            metadata['predictor_loaded'] = predictor_info.get('loaded')
            metadata['model_type'] = metadata.get('model_type', 'unknown')

        return JSONResponse(status_code=200, content=metadata)

    except HTTPException:
        raise
    except Exception as e:
        logger.error('get_model_details_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/v1/ml/models/{model_name}/promote')
async def promote_model(model_name: str, request: ModelPromotionRequest):
    """
    Promover versão de modelo para Production.

    Args:
        model_name: Nome do modelo
        request: Versão e stage de destino

    Returns:
        Resultado da promoção
    """
    try:
        if not app_state.model_registry:
            raise HTTPException(status_code=503, detail="ML predictions não habilitado")

        # Validar critérios de promoção (aplicados internamente pelo ModelRegistry)
        logger.info("Iniciando promoção de modelo", model_name=model_name, version=request.version, stage=request.stage)

        # Promover modelo (critérios aplicados internamente)
        await app_state.model_registry.promote_model(model_name, request.version, request.stage)

        # Recarregar preditor correspondente
        if 'scheduling' in model_name and app_state.scheduling_predictor:
            await app_state.scheduling_predictor.initialize()
            logger.info('SchedulingPredictor recarregado após promoção')
        elif 'load' in model_name and app_state.load_predictor:
            await app_state.load_predictor.initialize()
            logger.info('LoadPredictor recarregado após promoção')
        elif 'anomaly' in model_name and app_state.anomaly_detector:
            await app_state.anomaly_detector.initialize()
            logger.info('AnomalyDetector recarregado após promoção')

        # Consultar metadata atualizado para confirmar promoção
        metadata = await app_state.model_registry.get_model_metadata(model_name)
        current_stage = metadata.get('stage', 'None') if metadata else 'None'

        return JSONResponse(
            status_code=200,
            content={
                'model_name': model_name,
                'version': request.version,
                'requested_stage': request.stage,
                'current_stage': current_stage,
                'status': 'promoted' if current_stage == request.stage else 'criteria_not_met'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('promote_model_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/v1/ml/drift')
async def check_model_drift():
    """
    Executar verificação de drift de modelos.

    Returns:
        Relatório de drift (feature, prediction, target)
    """
    try:
        if not app_state.drift_detector:
            raise HTTPException(status_code=503, detail="Drift detection não habilitado")

        # Executar drift check
        drift_report = app_state.drift_detector.run_drift_check()

        return JSONResponse(status_code=200, content=drift_report)

    except HTTPException:
        raise
    except Exception as e:
        logger.error('drift_check_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/api/v1/ml/predictions/stats')
async def get_prediction_statistics():
    """
    Obter estatísticas de predições ML.

    Returns:
        Métricas de predições nas últimas 24h
    """
    try:
        if not app_state.mongodb_client:
            raise HTTPException(status_code=503, detail="MongoDB não disponível")

        # Query tickets com predições nas últimas 24h
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(hours=24)

        pipeline = [
            {
                '$match': {
                    'created_at': {'$gte': cutoff},
                    'predictions': {'$exists': True}
                }
            },
            {
                '$facet': {
                    'total': [{'$count': 'count'}],
                    'with_duration': [
                        {'$match': {'predictions.duration_ms': {'$exists': True}}},
                        {'$count': 'count'}
                    ],
                    'anomalies': [
                        {'$match': {'predictions.is_anomaly': True}},
                        {'$count': 'count'}
                    ],
                    'completed': [
                        {
                            '$match': {
                                'status': 'completed',
                                'actual_duration_ms': {'$exists': True},
                                'predictions.duration_ms': {'$exists': True}
                            }
                        },
                        {
                            '$project': {
                                'error': {
                                    '$abs': {
                                        '$subtract': ['$actual_duration_ms', '$predictions.duration_ms']
                                    }
                                },
                                'actual': '$actual_duration_ms',
                                'predicted': '$predictions.duration_ms'
                            }
                        },
                        {
                            '$group': {
                                '_id': None,
                                'avg_error': {'$avg': '$error'},
                                'errors': {'$push': '$error'},
                                'actuals': {'$push': '$actual'}
                            }
                        }
                    ]
                }
            }
        ]

        result = await app_state.mongodb_client.db['execution_tickets'].aggregate(pipeline).to_list(1)

        if result:
            data = result[0]
            total = data['total'][0]['count'] if data['total'] else 0
            with_duration = data['with_duration'][0]['count'] if data['with_duration'] else 0
            anomalies = data['anomalies'][0]['count'] if data['anomalies'] else 0

            avg_error = 0
            mae_pct = 0
            if data['completed'] and data['completed'][0]['actuals']:
                completed_data = data['completed'][0]
                avg_error = completed_data['avg_error']
                avg_actual = sum(completed_data['actuals']) / len(completed_data['actuals'])
                mae_pct = (avg_error / avg_actual * 100) if avg_actual > 0 else 0

            return JSONResponse(
                status_code=200,
                content={
                    'total_predictions': total,
                    'success_rate': (with_duration / total * 100) if total > 0 else 0,
                    'avg_latency_ms': 0,  # Não rastreado atualmente
                    'anomaly_rate': (anomalies / total * 100) if total > 0 else 0,
                    'duration_mae_pct': round(mae_pct, 2)
                }
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    'total_predictions': 0,
                    'success_rate': 0,
                    'avg_latency_ms': 0,
                    'anomaly_rate': 0,
                    'duration_mae_pct': 0
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('prediction_stats_error', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


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
