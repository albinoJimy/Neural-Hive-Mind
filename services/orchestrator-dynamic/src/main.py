"""
Ponto de entrada principal do serviço Orchestrator Dynamic.
Implementa FastAPI para API REST e gerencia lifecycle do Temporal Worker e Kafka Consumer.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from neural_hive_observability import init_observability, get_logger

from src.config import get_settings
from src.consumers.decision_consumer import DecisionConsumer
from src.workers.temporal_worker import TemporalWorkerManager, create_temporal_client
from src.temporal_client import TemporalClientWrapper
from src.clients.mongodb_client import MongoDBClient
from src.clients.kafka_producer import KafkaProducerClient
from src.clients.self_healing_client import SelfHealingClient
from src.clients.optimizer_grpc_client import OptimizerGrpcClient
from src.clients.execution_ticket_client import ExecutionTicketClient
from src.clients.redis_client import (
    get_redis_client,
    close_redis_client,
    get_circuit_breaker_state,
    get_cache_metrics,
    redis_get_safe,
    redis_setex_safe
)
from src.integration.flow_c_consumer import FlowCConsumer
from src.workflows.orchestration_workflow import OrchestrationWorkflow
from src.ml.model_audit_logger import ModelAuditLogger
from src.api.model_audit import create_model_audit_router
from pydantic import BaseModel, Field
from uuid import uuid4
from datetime import datetime


# =============================================================================
# Pydantic Models for Authorization Audit
# =============================================================================

class AuthorizationAuditQuery(BaseModel):
    """Query parameters para consulta de auditoria."""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    decision: Optional[str] = None  # 'allow' ou 'deny'
    policy_path: Optional[str] = None
    start_time: Optional[str] = None  # ISO timestamp
    end_time: Optional[str] = None    # ISO timestamp
    limit: int = Field(default=100, ge=1, le=1000)
    skip: int = Field(default=0, ge=0)


class AuthorizationAuditResponse(BaseModel):
    """Resposta de consulta de auditoria."""
    total: int
    results: List[Dict[str, Any]]
    query: Dict[str, Any]

# Import Vault integration (optional dependency)
try:
    from src.clients.vault_integration import OrchestratorVaultClient
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    OrchestratorVaultClient = None


# Configurar logger estruturado
logger = structlog.get_logger()


def _build_mongodb_uri_with_credentials(base_uri: str, username: str, password: str) -> str:
    """
    Constrói uma URI MongoDB com credenciais dinâmicas.

    Suporta URIs no formato:
    - mongodb://host:port/database
    - mongodb://existing_user:pass@host:port/database
    - mongodb+srv://host/database

    Args:
        base_uri: URI base do MongoDB (pode ou não ter credenciais)
        username: Usuário dinâmico do Vault
        password: Senha dinâmica do Vault

    Returns:
        URI com credenciais atualizadas
    """
    from urllib.parse import urlparse, urlunparse, quote_plus

    parsed = urlparse(base_uri)

    # Escapar caracteres especiais em credenciais
    safe_username = quote_plus(username)
    safe_password = quote_plus(password)

    # Construir netloc com novas credenciais
    host_part = parsed.hostname
    if parsed.port:
        host_part = f'{host_part}:{parsed.port}'

    new_netloc = f'{safe_username}:{safe_password}@{host_part}'

    # Reconstruir URI
    new_uri = urlunparse((
        parsed.scheme,
        new_netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment
    ))

    return new_uri


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
        self.execution_ticket_client: Optional[ExecutionTicketClient] = None
        self.self_healing_client: Optional[SelfHealingClient] = None
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
        self.spiffe_manager = None
        # gRPC Server para comandos estratégicos da Queen Agent
        self.grpc_server = None
        self.opa_client = None
        self.intelligent_scheduler = None
        self.audit_logger: Optional[ModelAuditLogger] = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia lifecycle da aplicação (startup/shutdown).
    """
    global logger
    config = get_settings()

    # Startup
    logger.info(
        'Inicializando Orchestrator Dynamic',
        service=config.service_name,
        version=config.service_version,
        environment=config.environment
    )

    logger.info(
        'OPA configuration carregada',
        opa_enabled=getattr(config, 'opa_enabled', False),
        opa_host=getattr(config, 'opa_host', None),
        opa_port=getattr(config, 'opa_port', None),
        opa_fail_open=getattr(config, 'opa_fail_open', False),
        opa_security_enabled=getattr(config, 'opa_security_enabled', False)
    )

    # Qualquer falha na criação/inicialização do Vault client cai em fail-open quando habilitado,
    # e erros posteriores de fetch de segredos também respeitam o mesmo comportamento de fallback.
    try:
        # Inicializar integração Vault/SPIFFE com fail-open
        vault_client = None
        if config.vault_enabled:
            if VAULT_AVAILABLE and OrchestratorVaultClient:
                try:
                    logger.info('Inicializando Vault client')
                    vault_client = OrchestratorVaultClient(config)
                    await vault_client.initialize()
                    app_state.vault_client = vault_client
                    logger.info('Vault client inicializado')
                except Exception as vault_error:
                    logger.error('Erro ao inicializar Vault integration', error=str(vault_error))
                    if not getattr(config, 'vault_fail_open', True):
                        raise
                    logger.warning('Vault fail-open habilitado, continuando com credenciais estáticas')
                    vault_client = None
                    app_state.vault_client = None
            else:
                if config.vault_enabled and not VAULT_AVAILABLE:
                    logger.warning('Vault habilitado mas biblioteca de segurança não disponível')
                else:
                    logger.info('Vault integration desabilitada, usando credenciais estáticas')
        else:
            logger.info('Vault integration desabilitada, usando credenciais estáticas')

        # Extrair SPIFFE manager para gRPC auth
        spiffe_manager = vault_client.spiffe_manager if vault_client else None
        app_state.spiffe_manager = spiffe_manager

        # Initialize OpenTelemetry tracing (conditional based on otel_enabled)
        otel_enabled = getattr(config, 'otel_enabled', True)
        if otel_enabled:
            try:
                otel_endpoint = os.getenv('OTEL_EXPORTER_ENDPOINT', getattr(config, 'otel_exporter_endpoint', None))
                init_observability(
                    service_name=getattr(config, 'service_name', "orchestrator-dynamic"),
                    service_version=config.service_version,
                    neural_hive_component="orchestrator",
                    neural_hive_layer="orchestration",
                    environment=config.environment,
                    otel_endpoint=otel_endpoint,
                )
                logger.info(
                    "OpenTelemetry habilitado e inicializado",
                    otel_endpoint=otel_endpoint,
                    service_name=config.service_name
                )
            except Exception as observability_error:
                logger.warning(
                    "Failed to initialize OpenTelemetry tracing via neural_hive_observability",
                    error=str(observability_error)
                )

            try:
                trace_logger = get_logger(__name__)
                trace_logger.info(
                    f"Orchestrator Dynamic initialized with OpenTelemetry tracing - "
                    f"version={config.service_version}, endpoint={config.otel_exporter_endpoint}"
                )
            except Exception as log_error:
                logger.warning(
                    "Failed to configure structured logging with trace correlation",
                    error=str(log_error)
                )
        else:
            logger.info("OpenTelemetry desabilitado via OTEL_ENABLED=false")
            # Criar ObservabilityConfig manualmente para evitar AttributeError no Kafka producer/consumer
            # Mesmo quando OTEL está desabilitado, precisamos de um config válido para instrumentação
            try:
                from neural_hive_observability.config import ObservabilityConfig
                from neural_hive_observability import set_config

                obs_config = ObservabilityConfig(
                    service_name=getattr(config, 'service_name', "orchestrator-dynamic"),
                    service_version=config.service_version,
                    neural_hive_component="orchestrator",
                    neural_hive_layer="orchestration",
                    environment=config.environment,
                )
                set_config(obs_config)
                logger.info(
                    "ObservabilityConfig criado manualmente (sem OTEL)",
                    service_name=obs_config.service_name,
                    environment=obs_config.environment
                )
            except Exception as e:
                logger.warning(
                    "Falha ao criar ObservabilityConfig manual, componentes Kafka podem ter problemas",
                    error=str(e)
                )

        # Buscar segredos/credenciais com fallback para configuração
        mongodb_uri = config.mongodb_uri
        mongodb_credentials = None
        redis_password = config.redis_password
        kafka_username = config.kafka_sasl_username
        kafka_password = config.kafka_sasl_password
        postgres_user = config.postgres_user
        postgres_password = config.postgres_password

        if vault_client:
            try:
                # Usar credenciais dinâmicas em vez de URI estática
                mongodb_credentials = await vault_client.get_mongodb_credentials()
                if mongodb_credentials.get('username') and mongodb_credentials.get('password'):
                    mongodb_uri = _build_mongodb_uri_with_credentials(
                        config.mongodb_uri,
                        mongodb_credentials['username'],
                        mongodb_credentials['password']
                    )
                    logger.info(
                        'Credenciais MongoDB dinâmicas obtidas do Vault',
                        ttl=mongodb_credentials.get('ttl', 0)
                    )
            except Exception as mongo_vault_error:
                logger.warning(
                    'Falha ao buscar credenciais MongoDB do Vault, usando configuração',
                    error=str(mongo_vault_error)
                )

            try:
                redis_password = await vault_client.get_redis_password()
            except Exception as redis_error:
                logger.warning(
                    'Falha ao buscar senha do Redis no Vault, usando configuração',
                    error=str(redis_error)
                )

            try:
                kafka_creds = await vault_client.get_kafka_credentials()
                kafka_username = kafka_creds.get('username', kafka_username)
                kafka_password = kafka_creds.get('password', kafka_password)
                logger.info('Credenciais Kafka obtidas do Vault')
            except Exception as kafka_error:
                logger.warning(
                    'Falha ao buscar credenciais Kafka do Vault, usando configuração',
                    error=str(kafka_error)
                )

            try:
                pg_creds = await vault_client.get_postgres_credentials()
                postgres_user = pg_creds['username']
                postgres_password = pg_creds['password']
                logger.info('Credenciais PostgreSQL obtidas do Vault', ttl=pg_creds.get('ttl', 0))
            except Exception as pg_error:
                logger.warning(
                    'Falha ao buscar credenciais PostgreSQL no Vault, usando configuração',
                    error=str(pg_error)
                )

        # Propagar overrides para config para consumidores/produtores compartilharem
        config.kafka_sasl_username = kafka_username
        config.kafka_sasl_password = kafka_password
        config.redis_password = redis_password

        # Inicializar MongoDB (fail-open)
        try:
            logger.info('Conectando ao MongoDB')
            app_state.mongodb_client = MongoDBClient(config, uri_override=mongodb_uri)
            await app_state.mongodb_client.initialize()
            logger.info('MongoDB conectado com sucesso')

            # Registrar callback para rotação de credenciais MongoDB
            if vault_client and mongodb_credentials and mongodb_credentials.get('ttl', 0) > 0:
                async def _mongodb_credential_update_callback(new_creds: Dict[str, Any]):
                    """Callback para recriar cliente MongoDB com novas credenciais."""
                    try:
                        new_uri = _build_mongodb_uri_with_credentials(
                            config.mongodb_uri,
                            new_creds['username'],
                            new_creds['password']
                        )
                        # Fechar cliente antigo
                        if app_state.mongodb_client:
                            await app_state.mongodb_client.close()
                        # Criar novo cliente com credenciais atualizadas
                        app_state.mongodb_client = MongoDBClient(config, uri_override=new_uri)
                        await app_state.mongodb_client.initialize()
                        logger.info(
                            'MongoDB client recriado com novas credenciais',
                            ttl=new_creds.get('ttl', 0)
                        )
                    except Exception as e:
                        logger.error(
                            'Falha ao recriar MongoDB client com novas credenciais',
                            error=str(e)
                        )
                        raise

                vault_client.set_mongodb_credential_callback(_mongodb_credential_update_callback)
                logger.info('Callback de rotação de credenciais MongoDB registrado')

        except Exception as mongo_error:
            logger.warning(
                'Falha ao conectar ao MongoDB, continuando em modo degradado',
                error=str(mongo_error)
            )
            app_state.mongodb_client = None

        # Inicializar Model Audit Logger (fail-open)
        if app_state.mongodb_client and getattr(config, 'ml_audit_enabled', True):
            try:
                from src.observability.metrics import get_metrics
                metrics = get_metrics()
                app_state.audit_logger = ModelAuditLogger(
                    mongodb_client=app_state.mongodb_client.client,
                    config=config,
                    metrics=metrics
                )
                logger.info(
                    'Model Audit Logger inicializado',
                    collection=app_state.audit_logger.collection_name,
                    retention_days=app_state.audit_logger.retention_days
                )
            except Exception as audit_error:
                logger.warning(
                    'Falha ao inicializar Model Audit Logger',
                    error=str(audit_error)
                )
                app_state.audit_logger = None

        # Inicializar Redis Client (fail-open para cache de predições ML)
        try:
            logger.info('Inicializando Redis Client para cache de predições ML')
            app_state.redis_client = await get_redis_client(config)
            if app_state.redis_client:
                logger.info(
                    'Redis Client inicializado com sucesso',
                    redis_nodes=config.redis_cluster_nodes,
                    ssl_enabled=config.redis_ssl_enabled
                )
            else:
                logger.warning('Redis Client retornou None - operando sem cache')
        except Exception as redis_error:
            logger.warning(
                'Falha ao inicializar Redis Client, continuando sem cache',
                error=str(redis_error)
            )
            app_state.redis_client = None

        # Inicializar modelos preditivos centralizados (se habilitado)
        if getattr(config, 'ml_predictions_enabled', False):
            from src.observability.metrics import get_metrics as get_init_metrics
            ml_init_metrics = get_init_metrics()
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
                ml_init_metrics.record_component_initialization_status(
                    component_name='scheduling_predictor',
                    status='in_progress',
                    component='ml',
                    layer='intelligence'
                )
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
                ml_init_metrics.record_component_initialization_status(
                    component_name='scheduling_predictor',
                    status='success',
                    component='ml',
                    layer='intelligence'
                )
                # Registrar status de treinamento do modelo scheduling predictor
                scheduling_model_trained = (
                    app_state.scheduling_predictor.model is not None
                )
                ml_init_metrics.record_ml_model_init_training_status(
                    model_name='scheduling-predictor',
                    status='trained' if scheduling_model_trained else 'untrained',
                    component='ml',
                    layer='intelligence'
                )
                logger.info(
                    'SchedulingPredictor inicializado',
                    model_trained=scheduling_model_trained
                )

                # LoadPredictor
                ml_init_metrics.record_component_initialization_status(
                    component_name='load_predictor',
                    status='in_progress',
                    component='ml',
                    layer='intelligence'
                )
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
                    redis_client=app_state.redis_client
                )
                await app_state.load_predictor.initialize()
                ml_init_metrics.record_component_initialization_status(
                    component_name='load_predictor',
                    status='success',
                    component='ml',
                    layer='intelligence'
                )
                # Registrar status de treinamento do modelo load predictor
                load_model_trained = (
                    app_state.load_predictor.model is not None
                )
                ml_init_metrics.record_ml_model_init_training_status(
                    model_name='load-predictor',
                    status='trained' if load_model_trained else 'untrained',
                    component='ml',
                    layer='intelligence'
                )
                logger.info(
                    'LoadPredictor inicializado',
                    redis_cache_enabled=app_state.redis_client is not None,
                    model_trained=load_model_trained
                )

                # AnomalyDetector
                ml_init_metrics.record_component_initialization_status(
                    component_name='anomaly_detector',
                    status='in_progress',
                    component='ml',
                    layer='intelligence'
                )
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
                ml_init_metrics.record_component_initialization_status(
                    component_name='anomaly_detector',
                    status='success',
                    component='ml',
                    layer='intelligence'
                )
                logger.info('AnomalyDetector inicializado')

                logger.info('Modelos preditivos centralizados inicializados com sucesso')

            except Exception as e:
                logger.warning(
                    'Falha ao inicializar modelos preditivos, continuando sem ML',
                    error=str(e)
                )
                # Registrar falha para todos os preditores (status de componente)
                for predictor_name in ['scheduling_predictor', 'load_predictor', 'anomaly_detector']:
                    ml_init_metrics.record_component_initialization_status(
                        component_name=predictor_name,
                        status='failed',
                        component='ml',
                        layer='intelligence'
                    )
                # Registrar falha no treinamento dos modelos ML
                for model_name in ['scheduling-predictor', 'load-predictor', 'anomaly-detector']:
                    ml_init_metrics.record_ml_model_init_training_status(
                        model_name=model_name,
                        status='failed',
                        component='ml',
                        layer='intelligence'
                    )
                app_state.scheduling_predictor = None
                app_state.load_predictor = None
                app_state.anomaly_detector = None
        else:
            logger.info('ML predictions desabilitado')

        # Inicializar Kafka Producer com credenciais do Vault
        logger.info('Inicializando Kafka Producer', topic=config.kafka_tickets_topic)
        from src.observability.metrics import get_metrics
        init_metrics = get_metrics()
        init_metrics.record_component_initialization_status(
            component_name='kafka_producer',
            status='in_progress',
            component='messaging',
            layer='infrastructure'
        )
        try:
            app_state.kafka_producer = KafkaProducerClient(
                config,
                sasl_username_override=kafka_username,
                sasl_password_override=kafka_password
            )
            await app_state.kafka_producer.initialize()
            init_metrics.record_component_initialization_status(
                component_name='kafka_producer',
                status='success',
                component='messaging',
                layer='infrastructure'
            )
            logger.info('Kafka Producer inicializado com sucesso')
        except Exception as kafka_init_error:
            init_metrics.record_component_initialization_status(
                component_name='kafka_producer',
                status='failed',
                component='messaging',
                layer='infrastructure'
            )
            logger.error(
                'Falha ao inicializar Kafka Producer',
                error=str(kafka_init_error)
            )
            raise

        # Inicializar Execution Ticket Service client com SPIFFE (fail-open)
        try:
            app_state.execution_ticket_client = ExecutionTicketClient(
                config,
                spiffe_manager=spiffe_manager
            )
            await app_state.execution_ticket_client.initialize()
            logger.info(
                'Execution Ticket client inicializado',
                spiffe_enabled=config.spiffe_enabled
            )
        except Exception as et_error:
            logger.warning(
                'Falha ao inicializar Execution Ticket client, continuando em modo degradado',
                error=str(et_error)
            )
            app_state.execution_ticket_client = None

        # Inicializar Self-Healing client (lazy HTTP)
        app_state.self_healing_client = SelfHealingClient(
            base_url=config.self_healing_engine_url,
            timeout=config.self_healing_timeout_seconds
        )

        # Criar cliente Temporal (lazy connection - não conecta imediatamente)
        # Temporal é opcional - serviço funciona em modo degradado sem ele
        if config.temporal_enabled:
            try:
                logger.info(
                    'Criando cliente Temporal',
                    host=config.temporal_host,
                    port=config.temporal_port,
                    namespace=config.temporal_namespace
                )
                # Observação: credenciais do Vault são aplicadas apenas no bootstrap; o client/pool Temporal não é rotacionado dinamicamente ainda.
                temporal_client_raw = await create_temporal_client(
                    config,
                    postgres_user=postgres_user,
                    postgres_password=postgres_password
                )
                if temporal_client_raw:
                    # Envolver com circuit breaker
                    app_state.temporal_client = TemporalClientWrapper(
                        client=temporal_client_raw,
                        service_name=config.service_name,
                        circuit_breaker_enabled=getattr(config, 'TEMPORAL_CIRCUIT_BREAKER_ENABLED', True),
                        fail_max=getattr(config, 'TEMPORAL_CIRCUIT_BREAKER_FAIL_MAX', 5),
                        timeout_duration=getattr(config, 'TEMPORAL_CIRCUIT_BREAKER_TIMEOUT', 60),
                        recovery_timeout=getattr(config, 'TEMPORAL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 30)
                    )
                    logger.info('Cliente Temporal criado com circuit breaker (lazy connection)')
                else:
                    app_state.temporal_client = None
                    logger.info('Temporal desabilitado via create_temporal_client')
            except Exception as e:
                logger.warning(
                    'Falha ao criar cliente Temporal, continuando em modo degradado',
                    error=str(e)
                )
                app_state.temporal_client = None
        else:
            logger.info('Temporal desabilitado via configuração (temporal_enabled=False)')
            app_state.temporal_client = None

        # Inicializar Kafka Consumer
        logger.info('Inicializando Kafka Consumer', topic=config.kafka_consensus_topic)
        from src.observability.metrics import get_metrics
        orchestrator_metrics = get_metrics()
        app_state.kafka_consumer = DecisionConsumer(
            config,
            app_state.temporal_client,
            app_state.mongodb_client,
            redis_client=app_state.redis_client,
            metrics=orchestrator_metrics,
            sasl_username_override=kafka_username,
            sasl_password_override=kafka_password
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

        # Inicializar Temporal Worker com dependências (se Temporal disponível)
        if app_state.temporal_client:
            logger.info('Inicializando Temporal Worker', task_queue=config.temporal_task_queue)
            init_metrics.record_component_initialization_status(
                component_name='temporal_worker',
                status='in_progress',
                component='workflow',
                layer='orchestration'
            )
            try:
                app_state.temporal_worker = TemporalWorkerManager(
                    config,
                    app_state.temporal_client,
                    app_state.kafka_producer,
                    app_state.mongodb_client,
                    optimizer_client=app_state.optimizer_client,
                    vault_client=app_state.vault_client,
                    scheduling_predictor=app_state.scheduling_predictor,
                    load_predictor=app_state.load_predictor,
                    anomaly_detector=app_state.anomaly_detector,
                    self_healing_client=app_state.self_healing_client
                )
                await app_state.temporal_worker.initialize()

                init_metrics.record_component_initialization_status(
                    component_name='temporal_worker',
                    status='success',
                    component='workflow',
                    layer='orchestration'
                )

                logger.info(
                    'Temporal Worker inicializado com PolicyValidator',
                    opa_enabled=config.opa_enabled,
                    policy_validator_injected=app_state.temporal_worker.policy_validator is not None,
                    opa_host=getattr(config, 'opa_host', None),
                    opa_port=getattr(config, 'opa_port', None)
                )

                # Iniciar Temporal Worker em background
                app_state.worker_task = asyncio.create_task(app_state.temporal_worker.start())
                logger.info('Temporal Worker iniciado em background')
            except Exception as temporal_init_error:
                init_metrics.record_component_initialization_status(
                    component_name='temporal_worker',
                    status='failed',
                    component='workflow',
                    layer='orchestration'
                )
                logger.error(
                    'Falha ao inicializar Temporal Worker',
                    error=str(temporal_init_error)
                )
                # Não propaga erro - serviço continua em modo degradado
                app_state.temporal_worker = None
        else:
            logger.warning('Temporal Worker não inicializado - Temporal client não disponível')

        # Iniciar Kafka Consumer em background
        app_state.consumer_task = asyncio.create_task(app_state.kafka_consumer.start())
        logger.info('Kafka Consumer iniciado em background')

        # Inicializar Flow C Consumer com config injetada
        logger.info('Inicializando Flow C Consumer')
        app_state.flow_c_consumer = FlowCConsumer(config=config)
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

        # Inicializar gRPC Server para comandos estratégicos da Queen Agent
        if getattr(config, 'enable_grpc_server', True):
            try:
                from src.grpc_server import (
                    OrchestratorStrategicServicer,
                    start_grpc_server
                )
                from src.policies.opa_client import OPAClient

                # Inicializar OPA Client com mongodb_client para audit logging
                if config.opa_enabled:
                    app_state.opa_client = OPAClient(
                        config,
                        mongodb_client=app_state.mongodb_client
                    )
                    await app_state.opa_client.initialize()
                    logger.info('OPA Client inicializado para gRPC servicer')

                # Criar servicer com dependências
                grpc_servicer = OrchestratorStrategicServicer(
                    temporal_client=app_state.temporal_client,
                    intelligent_scheduler=app_state.intelligent_scheduler,
                    opa_client=app_state.opa_client,
                    mongodb_client=app_state.mongodb_client,
                    kafka_producer=app_state.kafka_producer,
                    config=config
                )

                # Iniciar servidor gRPC
                grpc_port = getattr(config, 'grpc_server_port', 50053)
                enable_mtls = getattr(config, 'spiffe_enable_x509', False)

                app_state.grpc_server = await start_grpc_server(
                    servicer=grpc_servicer,
                    port=grpc_port,
                    spiffe_manager=app_state.spiffe_manager,
                    enable_mtls=enable_mtls
                )

                logger.info(
                    'gRPC Server iniciado para comandos estratégicos',
                    port=grpc_port,
                    mtls_enabled=enable_mtls
                )
            except Exception as grpc_error:
                logger.warning(
                    'Falha ao inicializar gRPC Server, continuando sem suporte a comandos estratégicos',
                    error=str(grpc_error)
                )
                app_state.grpc_server = None

        # Incluir Model Audit API Router
        include_audit_router()

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

        if app_state.execution_ticket_client:
            logger.info('Fechando Execution Ticket client')
            await app_state.execution_ticket_client.close()

        if app_state.self_healing_client:
            logger.info('Fechando Self-Healing client')
            await app_state.self_healing_client.close()

        # Fechar gRPC Server
        if app_state.grpc_server:
            try:
                from src.grpc_server import stop_grpc_server
                logger.info('Parando gRPC Server')
                await stop_grpc_server(app_state.grpc_server, grace_seconds=5)
                logger.info('gRPC Server parado com sucesso')
            except Exception as grpc_close_error:
                logger.warning('Erro ao fechar gRPC Server', error=str(grpc_close_error))

        # Fechar OPA Client
        if app_state.opa_client:
            try:
                logger.info('Fechando OPA Client')
                await app_state.opa_client.close()
            except Exception as opa_close_error:
                logger.warning('Erro ao fechar OPA Client', error=str(opa_close_error))

        # Fechar MongoDB
        if app_state.mongodb_client:
            logger.info('Fechando MongoDB client')
            await app_state.mongodb_client.close()

        # Fechar Redis Client
        if app_state.redis_client:
            try:
                logger.info('Fechando Redis Client')
                await close_redis_client()
                logger.info('Redis Client fechado com sucesso')
            except Exception as redis_close_error:
                logger.warning('Erro ao fechar Redis Client', error=str(redis_close_error))

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
# Model Audit API Router
# =============================================================================

def include_audit_router():
    """Inclui o router de audit se o audit logger estiver inicializado."""
    if app_state.audit_logger:
        audit_router = create_model_audit_router(app_state.audit_logger)
        app.include_router(audit_router)
        logger.info('Model Audit API router incluído')


# =============================================================================
# Workflow State Cache
# =============================================================================

# TTL padrão para cache de estado de workflow (5 minutos)
WORKFLOW_CACHE_TTL_SECONDS = 300


async def get_cached_workflow_state(workflow_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtém estado de workflow do cache Redis.

    Args:
        workflow_id: ID do workflow

    Returns:
        Estado do workflow ou None se não encontrado no cache
    """
    import json

    cache_key = f"workflow_state:{workflow_id}"
    cached = await redis_get_safe(cache_key)

    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            logger.warning("workflow_cache_decode_error", workflow_id=workflow_id)
            return None

    return None


async def cache_workflow_state(workflow_id: str, state: Dict[str, Any], ttl: int = WORKFLOW_CACHE_TTL_SECONDS) -> bool:
    """
    Armazena estado de workflow no cache Redis.

    Args:
        workflow_id: ID do workflow
        state: Estado do workflow a cachear
        ttl: TTL em segundos (default: 300)

    Returns:
        True se cacheado com sucesso, False caso contrário
    """
    import json

    cache_key = f"workflow_state:{workflow_id}"

    try:
        state_json = json.dumps(state)
        return await redis_setex_safe(cache_key, ttl, state_json)
    except (TypeError, ValueError) as e:
        logger.warning("workflow_cache_encode_error", workflow_id=workflow_id, error=str(e))
        return False


async def get_cached_tickets_by_workflow(workflow_id: str) -> Optional[list]:
    """
    Obtém tickets de workflow do cache Redis.

    Args:
        workflow_id: ID do workflow

    Returns:
        Lista de tickets ou None se não encontrado no cache
    """
    import json

    cache_key = f"workflow_tickets:{workflow_id}"
    cached = await redis_get_safe(cache_key)

    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            logger.warning("workflow_tickets_cache_decode_error", workflow_id=workflow_id)
            return None

    return None


async def cache_tickets_by_workflow(workflow_id: str, tickets: list, ttl: int = WORKFLOW_CACHE_TTL_SECONDS) -> bool:
    """
    Armazena tickets de workflow no cache Redis.

    Args:
        workflow_id: ID do workflow
        tickets: Lista de tickets a cachear
        ttl: TTL em segundos (default: 300)

    Returns:
        True se cacheado com sucesso, False caso contrário
    """
    import json

    cache_key = f"workflow_tickets:{workflow_id}"

    try:
        tickets_json = json.dumps(tickets)
        return await redis_setex_safe(cache_key, ttl, tickets_json)
    except (TypeError, ValueError) as e:
        logger.warning("workflow_tickets_cache_encode_error", workflow_id=workflow_id, error=str(e))
        return False


async def get_cached_flow_c_status() -> Optional[Dict[str, Any]]:
    """
    Obtém estatísticas de Flow C do cache Redis.

    Returns:
        Estatísticas ou None se não encontrado no cache
    """
    import json

    cache_key = "flow_c_status:aggregated"
    cached = await redis_get_safe(cache_key)

    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            logger.warning("flow_c_status_cache_decode_error")
            return None

    return None


async def cache_flow_c_status(status: Dict[str, Any], ttl: int = 60) -> bool:
    """
    Armazena estatísticas de Flow C no cache Redis.

    Args:
        status: Estatísticas a cachear
        ttl: TTL em segundos (default: 60 - mais curto para dados agregados)

    Returns:
        True se cacheado com sucesso, False caso contrário
    """
    import json

    cache_key = "flow_c_status:aggregated"

    try:
        status_json = json.dumps(status)
        return await redis_setex_safe(cache_key, ttl, status_json)
    except (TypeError, ValueError) as e:
        logger.warning("flow_c_status_cache_encode_error", error=str(e))
        return False


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
    """Health check básico com status do Redis e Vault."""
    from datetime import datetime

    config = get_settings()
    overall_status = 'healthy'

    # Verificar Redis (opcional - fail-open)
    redis_status = {
        'available': False,
        'circuit_breaker_state': 'UNKNOWN'
    }

    if app_state.redis_client:
        try:
            await asyncio.wait_for(app_state.redis_client.ping(), timeout=2.0)
            redis_status['available'] = True
            cb_state = get_circuit_breaker_state()
            redis_status['circuit_breaker_state'] = cb_state['state']
        except asyncio.TimeoutError:
            redis_status['error'] = 'timeout'
            cb_state = get_circuit_breaker_state()
            redis_status['circuit_breaker_state'] = cb_state['state']
        except Exception as e:
            redis_status['error'] = str(e)
            cb_state = get_circuit_breaker_state()
            redis_status['circuit_breaker_state'] = cb_state['state']
    else:
        cb_state = get_circuit_breaker_state()
        redis_status['circuit_breaker_state'] = cb_state['state']
        redis_status['error'] = 'not_initialized'

    # Verificar Vault connectivity
    vault_status = {
        'enabled': config.vault_enabled,
        'status': 'disabled'
    }

    if config.vault_enabled and app_state.vault_client:
        try:
            # Check if Vault client has health_check method
            if hasattr(app_state.vault_client, 'vault_client') and app_state.vault_client.vault_client:
                vault_healthy = await app_state.vault_client.vault_client.health_check()
                vault_status['status'] = 'healthy' if vault_healthy else 'unhealthy'
            else:
                vault_status['status'] = 'client_not_initialized'

            if vault_status['status'] == 'unhealthy':
                # Check fail-open policy
                if not config.vault_fail_open:
                    overall_status = 'unhealthy'
                    vault_status['error'] = 'Vault unhealthy and fail_open=false'
        except Exception as e:
            vault_status['status'] = 'error'
            vault_status['error'] = str(e)
            if not config.vault_fail_open:
                overall_status = 'unhealthy'
    elif config.vault_enabled and not app_state.vault_client:
        vault_status['status'] = 'not_initialized'
        if not config.vault_fail_open:
            overall_status = 'unhealthy'
            vault_status['error'] = 'Vault enabled but client not initialized'

    return JSONResponse(
        status_code=200 if overall_status == 'healthy' else 503,
        content={
            'status': overall_status,
            'service': 'orchestrator-dynamic',
            'version': '1.0.0',
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {
                'redis': redis_status,
                'vault': vault_status
            }
        }
    )


@app.get('/health/opa')
async def opa_health_check():
    """
    Health check para integração OPA.

    Retorna status de saúde do OPA server, estado do circuit breaker,
    métricas de cache e informações de configuração.

    Returns:
        JSON com status detalhado da integração OPA:
        - status: 'healthy', 'unhealthy', ou 'disabled'
        - enabled: booleano indicando se OPA está habilitado
        - opa_server: URL do servidor OPA
        - circuit_breaker: estado atual do circuit breaker
        - cache_size: número de decisões em cache
        - last_check: timestamp da última verificação
    """
    from datetime import datetime

    config = get_settings()

    # Verificar se OPA está habilitado
    if not getattr(config, 'opa_enabled', False):
        return JSONResponse(
            status_code=200,
            content={
                'status': 'disabled',
                'enabled': False,
                'message': 'OPA integration está desabilitada via configuração'
            }
        )

    # Verificar se Temporal Worker e OPA Client estão disponíveis
    if not app_state.temporal_worker:
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unavailable',
                'enabled': True,
                'error': 'Temporal Worker não inicializado'
            }
        )

    # Verificar se OPA client está disponível no worker
    opa_client = getattr(app_state.temporal_worker, 'opa_client', None)
    if not opa_client:
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unavailable',
                'enabled': True,
                'error': 'OPA Client não inicializado no Temporal Worker'
            }
        )

    try:
        # Executar health check no OPA server
        is_healthy = await opa_client.health_check()
        circuit_state = opa_client.get_circuit_breaker_state()

        # Calcular métricas de cache
        cache_size = len(opa_client._cache) if hasattr(opa_client, '_cache') else 0

        # Determinar status geral
        # Se circuit breaker está aberto por muito tempo, considerar unhealthy
        status = 'healthy'
        if not is_healthy:
            status = 'unhealthy'
        elif circuit_state.get('state') == 'open':
            status = 'degraded'

        response = {
            'status': status,
            'enabled': True,
            'opa_server': f"http://{config.opa_host}:{config.opa_port}",
            'circuit_breaker': circuit_state,
            'cache_size': cache_size,
            'cache_ttl_seconds': config.opa_cache_ttl_seconds,
            'fail_open': config.opa_fail_open,
            'last_check': datetime.now().isoformat()
        }

        # Adicionar informações de políticas configuradas
        response['policies'] = {
            'resource_limits': config.opa_policy_resource_limits,
            'sla_enforcement': config.opa_policy_sla_enforcement,
            'feature_flags': config.opa_policy_feature_flags,
            'security_constraints': config.opa_policy_security_constraints if config.opa_security_enabled else 'disabled'
        }

        return JSONResponse(
            status_code=200 if status in ['healthy', 'degraded'] else 503,
            content=response
        )

    except Exception as e:
        logger.error('opa_health_check_error', error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                'status': 'error',
                'enabled': True,
                'error': str(e),
                'last_check': datetime.now().isoformat()
            }
        )


@app.get('/health/kafka-producer')
async def kafka_producer_health_check():
    """
    Health check específico para Kafka Producer.

    Valida:
    - Producer inicializado
    - Config válido (service_name presente)
    - Circuit breaker inicializado
    - Conexão com Kafka cluster
    """
    from datetime import datetime

    status = 'healthy'
    checks = {}

    # Verificar se producer existe
    if not app_state.kafka_producer:
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unhealthy',
                'error': 'Kafka Producer not initialized',
                'timestamp': datetime.utcnow().isoformat()
            }
        )

    producer = app_state.kafka_producer

    # Verificar config
    checks['config'] = {
        'valid': False,
        'service_name': None
    }

    if producer.config:
        checks['config']['valid'] = True
        checks['config']['service_name'] = getattr(producer.config, 'service_name', None)

        if not checks['config']['service_name']:
            status = 'degraded'
            checks['config']['error'] = 'service_name is None'
    else:
        status = 'unhealthy'
        checks['config']['error'] = 'config is None'

    # Verificar circuit breaker
    checks['circuit_breaker'] = {
        'initialized': False,
        'state': 'unknown'
    }

    if hasattr(producer, 'producer_breaker') and producer.producer_breaker:
        checks['circuit_breaker']['initialized'] = True
        checks['circuit_breaker']['state'] = producer.producer_breaker.current_state
    else:
        status = 'degraded'
        checks['circuit_breaker']['error'] = 'Circuit breaker not initialized'

    # Verificar producer Kafka
    checks['kafka_connection'] = {
        'initialized': False
    }

    if hasattr(producer, 'producer') and producer.producer:
        checks['kafka_connection']['initialized'] = True
    else:
        status = 'unhealthy'
        checks['kafka_connection']['error'] = 'Kafka producer not initialized'

    return JSONResponse(
        status_code=200 if status == 'healthy' else (503 if status == 'unhealthy' else 200),
        content={
            'status': status,
            'component': 'kafka_producer',
            'timestamp': datetime.utcnow().isoformat(),
            'checks': checks
        }
    )


@app.get('/health/temporal-activities')
async def temporal_activities_health_check():
    """
    Health check para validar que todas as activities estão registradas.

    Verifica se activities críticas estão na lista de activities do Worker.
    """
    from datetime import datetime

    if not app_state.temporal_worker:
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unavailable',
                'error': 'Temporal Worker not initialized',
                'timestamp': datetime.utcnow().isoformat()
            }
        )

    # Lista de activities críticas esperadas
    expected_activities = [
        'validate_cognitive_plan',
        'generate_execution_tickets',
        'consolidate_results',
        'check_workflow_sla_proactive',
        'publish_ticket_to_kafka',
        'allocate_resources'
    ]

    # Obter activities registradas
    registered_activities = []
    missing_activities = []

    if hasattr(app_state.temporal_worker, 'worker') and app_state.temporal_worker.worker:
        # Extrair nomes de activities registradas
        worker = app_state.temporal_worker.worker
        if hasattr(worker, '_activities'):
            registered_activities = [act.__name__ for act in worker._activities]

    # Verificar quais estão faltando
    for activity in expected_activities:
        if activity not in registered_activities:
            missing_activities.append(activity)

    status = 'healthy' if not missing_activities else 'degraded'

    return JSONResponse(
        status_code=200 if status == 'healthy' else 200,  # 200 mesmo degraded para não bloquear readiness
        content={
            'status': status,
            'component': 'temporal_activities',
            'timestamp': datetime.utcnow().isoformat(),
            'registered_count': len(registered_activities),
            'expected_count': len(expected_activities),
            'missing_activities': missing_activities,
            'registered_activities': registered_activities
        }
    )


@app.get('/ready')
async def readiness_check():
    """
    Readiness check - verifica se serviço está pronto para receber requisições.
    Valida conexões com Kafka e MongoDB. Temporal é opcional.
    """
    checks = {
        'kafka_consumer': False,
        'flow_c_consumer': False
    }

    try:
        # Verificar Kafka Consumer (obrigatório)
        if app_state.kafka_consumer and app_state.kafka_consumer.running:
            checks['kafka_consumer'] = True

        # Verificar Flow C Consumer (obrigatório)
        if app_state.flow_c_consumer and app_state.flow_c_consumer.running:
            checks['flow_c_consumer'] = True

        # Temporal é opcional - incluir no status se disponível
        if app_state.temporal_client:
            checks['temporal'] = True
            # Verificar Temporal Worker apenas se Temporal disponível
            checks['worker'] = bool(app_state.temporal_worker and app_state.temporal_worker.running)
        else:
            checks['temporal'] = 'disabled'
            checks['worker'] = 'disabled'

        # Ready se componentes obrigatórios estão OK
        required_checks = [checks['kafka_consumer'], checks['flow_c_consumer']]
        all_ready = all(v is True for v in required_checks)

        return JSONResponse(
            status_code=200 if all_ready else 503,
            content={
                'status': 'ready' if all_ready else 'not_ready',
                'checks': checks,
                'mode': 'full' if app_state.temporal_client else 'degraded'
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


@app.get('/redis/stats')
async def get_redis_stats():
    """
    Estatísticas do cache Redis em tempo real.

    Retorna informações sobre:
    - Estado do Redis e circuit breaker
    - Métricas de cache: total_hits, total_misses, hit_ratio
    - Latência média recente das operações

    Dados retornados mesmo quando Redis está degradado (fallback values).
    """
    config = get_settings()

    # Sempre incluir métricas de cache (disponível mesmo com Redis degradado)
    cache_telemetry = get_cache_metrics()
    circuit_breaker_state = get_circuit_breaker_state()

    # Base response com fallback values
    base_response = {
        'available': False,
        'circuit_breaker': circuit_breaker_state,
        'cache_telemetry': cache_telemetry,
        'cache_ttl_seconds': getattr(config, 'ml_forecast_cache_ttl_seconds', 300),
        'redis_nodes': config.redis_cluster_nodes,
        'ssl_enabled': config.redis_ssl_enabled
    }

    if not app_state.redis_client:
        base_response['error'] = 'Redis not initialized'
        return JSONResponse(status_code=503, content=base_response)

    try:
        # Testar conexão usando wrapper seguro
        from src.clients.redis_client import redis_ping_safe

        ping_result = await asyncio.wait_for(redis_ping_safe(), timeout=2.0)

        if ping_result:
            base_response['available'] = True
            return JSONResponse(status_code=200, content=base_response)
        else:
            base_response['error'] = 'Redis ping failed (circuit breaker may be open)'
            return JSONResponse(status_code=503, content=base_response)

    except asyncio.TimeoutError:
        base_response['error'] = 'Redis timeout'
        return JSONResponse(status_code=503, content=base_response)
    except Exception as e:
        logger.error('redis_stats_error', error=str(e))
        base_response['error'] = str(e)
        return JSONResponse(status_code=503, content=base_response)


# =============================================================================
# Authorization Audit API
# =============================================================================

@app.get('/api/v1/audit/authorizations', response_model=AuthorizationAuditResponse)
async def query_authorization_audit(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    decision: Optional[str] = None,
    policy_path: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0)
):
    """
    Consultar audit log de decisões de autorização.

    Filtros disponíveis:
    - user_id: Filtrar por usuário
    - tenant_id: Filtrar por tenant
    - decision: Filtrar por decisão ('allow' ou 'deny')
    - policy_path: Filtrar por política
    - start_time: Timestamp inicial (ISO format)
    - end_time: Timestamp final (ISO format)
    - limit: Número máximo de resultados (1-1000)
    - skip: Número de resultados a pular (paginação)

    Returns:
        Lista de entradas de auditoria com total e query
    """
    if not app_state.mongodb_client:
        raise HTTPException(status_code=503, detail='MongoDB não disponível')

    from src.observability.metrics import get_metrics
    metrics = get_metrics()
    start = datetime.now()

    try:
        # Construir filtro MongoDB
        filter_query = {}

        if user_id:
            filter_query['user_id'] = user_id
        if tenant_id:
            filter_query['tenant_id'] = tenant_id
        if decision:
            filter_query['decision'] = decision
        if policy_path:
            filter_query['policy_path'] = policy_path

        # Filtro de timestamp
        if start_time or end_time:
            timestamp_filter = {}
            if start_time:
                timestamp_filter['$gte'] = start_time
            if end_time:
                timestamp_filter['$lte'] = end_time
            filter_query['timestamp'] = timestamp_filter

        # Executar query com paginação
        cursor = app_state.mongodb_client.authorization_audit.find(filter_query)
        cursor = cursor.sort('timestamp', -1).skip(skip).limit(limit)

        results = await cursor.to_list(length=limit)

        # Contar total (sem paginação)
        total = await app_state.mongodb_client.authorization_audit.count_documents(filter_query)

        # Remover _id do MongoDB dos resultados
        for result in results:
            result.pop('_id', None)

        duration = (datetime.now() - start).total_seconds()
        metrics.record_authorization_audit_query_duration('list', duration)

        return AuthorizationAuditResponse(
            total=total,
            results=results,
            query={
                'user_id': user_id,
                'tenant_id': tenant_id,
                'decision': decision,
                'policy_path': policy_path,
                'start_time': start_time,
                'end_time': end_time,
                'limit': limit,
                'skip': skip
            }
        )

    except Exception as e:
        logger.error(
            'authorization_audit_query_failed',
            error=str(e),
            filter_query=filter_query if 'filter_query' in locals() else {}
        )
        metrics.record_authorization_audit_error('query_failed')
        raise HTTPException(status_code=500, detail=f'Erro ao consultar auditoria: {str(e)}')


@app.get('/api/v1/tickets/{ticket_id}')
async def get_ticket(ticket_id: str):
    """
    Consultar ticket de execução por ID.

    Retorna informações detalhadas do ticket incluindo status, alocação,
    SLA e metadata. Utiliza cache Redis para reduzir carga no MongoDB.

    Args:
        ticket_id: ID único do ticket de execução

    Returns:
        JSON com dados completos do ticket

    Raises:
        HTTPException 404: Ticket não encontrado
        HTTPException 503: MongoDB não disponível
        HTTPException 500: Erro interno
    """
    from opentelemetry import trace as otel_trace
    import json

    tracer = otel_trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "orchestrator.get_ticket",
        attributes={
            "ticket.id": ticket_id,
        }
    ) as span:
        try:
            # Verificar cache Redis primeiro (fail-open)
            cache_key = f"ticket:{ticket_id}"
            cached_data = await redis_get_safe(cache_key)
            if cached_data:
                try:
                    cached_ticket = json.loads(cached_data)
                    logger.info(
                        'ticket_cache_hit',
                        ticket_id=ticket_id
                    )
                    span.set_attribute("cache.hit", True)
                    cached_ticket['cached'] = True
                    return JSONResponse(status_code=200, content=cached_ticket)
                except json.JSONDecodeError:
                    logger.warning('ticket_cache_decode_error', ticket_id=ticket_id)

            span.set_attribute("cache.hit", False)

            # Verificar disponibilidade do MongoDB
            if not app_state.mongodb_client:
                logger.error(
                    'ticket_query_rejected',
                    reason='mongodb_unavailable',
                    ticket_id=ticket_id
                )
                raise HTTPException(
                    status_code=503,
                    detail='MongoDB not available'
                )

            # Buscar ticket no MongoDB
            ticket = await app_state.mongodb_client.get_ticket(ticket_id)

            if not ticket:
                logger.warning(
                    'ticket_not_found',
                    ticket_id=ticket_id
                )
                span.set_attribute("ticket.found", False)
                raise HTTPException(
                    status_code=404,
                    detail=f'Ticket {ticket_id} not found'
                )

            # Remover _id do MongoDB para serialização JSON
            if '_id' in ticket:
                del ticket['_id']

            ticket['cached'] = False

            logger.info(
                'ticket_retrieved',
                ticket_id=ticket_id,
                status=ticket.get('status'),
                plan_id=ticket.get('plan_id')
            )
            span.set_attribute("ticket.found", True)
            span.set_attribute("ticket.status", ticket.get('status', 'unknown'))

            # Cachear resultado (fail-open - não bloqueia se Redis falhar)
            try:
                await redis_setex_safe(cache_key, 300, json.dumps(ticket))  # 5 minutos
            except Exception as cache_err:
                logger.warning('ticket_cache_write_error', ticket_id=ticket_id, error=str(cache_err))

            return JSONResponse(status_code=200, content=ticket)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                'ticket_query_error',
                ticket_id=ticket_id,
                error=str(e),
                error_type=type(e).__name__
            )
            span.record_exception(e)
            raise HTTPException(
                status_code=500,
                detail=f'Error retrieving ticket: {str(e)}'
            )


@app.get('/api/v1/tickets/by-plan/{plan_id}')
async def get_tickets_by_plan(
    plan_id: str,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Listar tickets de execução de um plano cognitivo.

    Suporta filtragem por status e paginação. Utiliza cache Redis
    para reduzir carga no MongoDB.

    Args:
        plan_id: ID do plano cognitivo
        status: Filtro opcional de status (PENDING, RUNNING, COMPLETED, FAILED)
        limit: Número máximo de resultados (default: 100, max: 500)
        offset: Offset para paginação (default: 0)

    Returns:
        JSON com lista de tickets e metadados de paginação

    Raises:
        HTTPException 400: Parâmetros inválidos
        HTTPException 503: MongoDB não disponível
        HTTPException 500: Erro interno
    """
    from opentelemetry import trace as otel_trace
    import json

    tracer = otel_trace.get_tracer(__name__)

    # Validar parâmetros
    if limit > 500:
        raise HTTPException(
            status_code=400,
            detail='Limit cannot exceed 500'
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail='Offset must be non-negative'
        )

    with tracer.start_as_current_span(
        "orchestrator.get_tickets_by_plan",
        attributes={
            "plan.id": plan_id,
            "filter.status": status or "all",
            "pagination.limit": limit,
            "pagination.offset": offset,
        }
    ) as span:
        try:
            # Construir cache key baseado em filtros
            cache_key_parts = [plan_id]
            if status:
                cache_key_parts.append(status)
            cache_key_parts.extend([str(limit), str(offset)])
            cache_key = f"tickets:plan:{':'.join(cache_key_parts)}"

            # Verificar cache Redis primeiro (fail-open)
            cached_data = await redis_get_safe(cache_key)
            if cached_data:
                try:
                    cached_result = json.loads(cached_data)
                    logger.info(
                        'tickets_list_cache_hit',
                        plan_id=plan_id,
                        status=status,
                        count=len(cached_result.get('tickets', []))
                    )
                    span.set_attribute("cache.hit", True)
                    cached_result['cached'] = True
                    return JSONResponse(status_code=200, content=cached_result)
                except json.JSONDecodeError:
                    logger.warning('tickets_list_cache_decode_error', plan_id=plan_id)

            span.set_attribute("cache.hit", False)

            # Verificar disponibilidade do MongoDB
            if not app_state.mongodb_client:
                logger.error(
                    'tickets_list_query_rejected',
                    reason='mongodb_unavailable',
                    plan_id=plan_id
                )
                raise HTTPException(
                    status_code=503,
                    detail='MongoDB not available'
                )

            # Construir query MongoDB
            query = {'plan_id': plan_id}
            if status:
                # Validar status
                valid_statuses = ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'REJECTED', 'COMPENSATING', 'COMPENSATED']
                if status.upper() not in valid_statuses:
                    raise HTTPException(
                        status_code=400,
                        detail=f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
                    )
                query['status'] = status.upper()

            # Buscar tickets com paginação
            collection = app_state.mongodb_client.execution_tickets

            # Count total (para metadata de paginação)
            total = await collection.count_documents(query)

            # Buscar tickets
            cursor = collection.find(query).sort('created_at', -1).skip(offset).limit(limit)
            tickets = await cursor.to_list(length=limit)

            # Remover _id do MongoDB para serialização JSON
            for ticket in tickets:
                if '_id' in ticket:
                    del ticket['_id']

            result = {
                'tickets': tickets,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + len(tickets)) < total,
                'cached': False
            }

            logger.info(
                'tickets_list_retrieved',
                plan_id=plan_id,
                status=status,
                count=len(tickets),
                total=total
            )
            span.set_attribute("tickets.count", len(tickets))
            span.set_attribute("tickets.total", total)

            # Cachear resultado (fail-open - não bloqueia se Redis falhar)
            # TTL menor para listas (2 minutos) pois podem mudar frequentemente
            try:
                await redis_setex_safe(cache_key, 120, json.dumps(result))
            except Exception as cache_err:
                logger.warning('tickets_list_cache_write_error', plan_id=plan_id, error=str(cache_err))

            return JSONResponse(status_code=200, content=result)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                'tickets_list_query_error',
                plan_id=plan_id,
                status=status,
                error=str(e),
                error_type=type(e).__name__
            )
            span.record_exception(e)
            raise HTTPException(
                status_code=500,
                detail=f'Error retrieving tickets: {str(e)}'
            )


@app.get('/api/v1/flow-c/status')
async def get_flow_c_status():
    """
    Retorna estatísticas de execução do Flow C agregadas do MongoDB.

    Utiliza cache Redis para reduzir carga no MongoDB (TTL: 60s).
    """
    try:
        # Verificar cache primeiro
        cached_status = await get_cached_flow_c_status()
        if cached_status:
            cached_status['cached'] = True
            return JSONResponse(status_code=200, content=cached_status)

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

            status_data = {
                'total_processed': total,
                'success_rate': round(success_rate, 2),
                'average_latency_ms': avg_latency,
                'p95_latency_ms': p95_latency,
                'active_executions': active,
                'cached': False
            }

            # Cachear resultado (fail-open - não bloqueia se Redis indisponível)
            await cache_flow_c_status(status_data, ttl=60)

            return JSONResponse(status_code=200, content=status_data)
        else:
            status_data = {
                'total_processed': 0,
                'success_rate': 0.0,
                'average_latency_ms': 0,
                'p95_latency_ms': 0,
                'active_executions': 0,
                'cached': False
            }

            # Cachear resultado vazio também
            await cache_flow_c_status(status_data, ttl=60)

            return JSONResponse(status_code=200, content=status_data)

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


class WorkflowStartRequest(BaseModel):
    """Request para iniciar workflow Temporal."""
    cognitive_plan: Dict[str, Any] = Field(..., description="Plano cognitivo a ser executado")
    correlation_id: str = Field(..., description="ID de correlação para rastreabilidade")
    priority: int = Field(default=5, ge=1, le=10, description="Prioridade do workflow (1-10)")
    sla_deadline_seconds: int = Field(default=14400, description="Deadline SLA em segundos (default: 4h)")


class WorkflowStartResponse(BaseModel):
    """Response do início de workflow."""
    workflow_id: str = Field(..., description="ID do workflow iniciado")
    status: str = Field(..., description="Status do workflow")
    correlation_id: str = Field(..., description="ID de correlação")


class WorkflowQueryRequest(BaseModel):
    """Request para query de workflow Temporal."""
    query_name: str = Field(..., description="Nome da query a executar (ex: get_tickets, get_status)")
    args: List[Any] = Field(default_factory=list, description="Argumentos opcionais da query")


class WorkflowQueryResponse(BaseModel):
    """Response de query de workflow Temporal."""
    workflow_id: str = Field(..., description="ID do workflow consultado")
    query_name: str = Field(..., description="Nome da query executada")
    result: Dict[str, Any] = Field(..., description="Resultado da query")


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
    """
    Consultar status de workflow Temporal via describe.

    Este endpoint retorna informações básicas do workflow incluindo
    status de execução, timestamps e metadata. Para queries mais
    específicas (como tickets gerados), use o endpoint de query.

    Args:
        workflow_id: ID do workflow Temporal

    Returns:
        JSON com status do workflow

    Raises:
        HTTPException 503: Temporal client não disponível
        HTTPException 404: Workflow não encontrado
        HTTPException 500: Erro ao consultar workflow
    """
    from opentelemetry import trace as otel_trace
    import json

    tracer = otel_trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "orchestrator.get_workflow_status",
        attributes={
            "workflow.id": workflow_id,
        }
    ) as span:
        # Validar disponibilidade do Temporal client
        if not app_state.temporal_client:
            logger.warning(
                'workflow_status_rejected',
                reason='temporal_client_unavailable',
                workflow_id=workflow_id
            )
            raise HTTPException(
                status_code=503,
                detail='Temporal client not available. Service running in degraded mode.'
            )

        # Verificar cache Redis primeiro (fail-open)
        cache_key = f"workflow:status:{workflow_id}"
        cached_data = await redis_get_safe(cache_key)
        if cached_data:
            try:
                cached_status = json.loads(cached_data)
                logger.info(
                    'workflow_status_cache_hit',
                    workflow_id=workflow_id
                )
                span.set_attribute("cache.hit", True)
                cached_status['cached'] = True
                return JSONResponse(status_code=200, content=cached_status)
            except json.JSONDecodeError:
                logger.warning('workflow_status_cache_decode_error', workflow_id=workflow_id)

        span.set_attribute("cache.hit", False)

        logger.info(
            'workflow_status_query',
            workflow_id=workflow_id
        )

        try:
            # Obter handle do workflow
            handle = app_state.temporal_client.get_workflow_handle(workflow_id)

            # Describe workflow para obter status
            description = await handle.describe()

            # Extrair informações relevantes
            workflow_info = description.workflow_execution_info if hasattr(description, 'workflow_execution_info') else description

            status_data = {
                'workflow_id': workflow_id,
                'status': workflow_info.status.name if hasattr(workflow_info, 'status') else 'UNKNOWN',
                'start_time': workflow_info.start_time.isoformat() if hasattr(workflow_info, 'start_time') and workflow_info.start_time else None,
                'close_time': workflow_info.close_time.isoformat() if hasattr(workflow_info, 'close_time') and workflow_info.close_time else None,
                'execution_time': workflow_info.execution_time.isoformat() if hasattr(workflow_info, 'execution_time') and workflow_info.execution_time else None,
                'workflow_type': workflow_info.type.name if hasattr(workflow_info, 'type') and workflow_info.type else None,
                'task_queue': workflow_info.task_queue if hasattr(workflow_info, 'task_queue') else None,
                'cached': False
            }

            # Adicionar informações de resultado se workflow completou
            if hasattr(workflow_info, 'close_time') and workflow_info.close_time:
                try:
                    result = await handle.result()
                    if result:
                        status_data['result_summary'] = {
                            'status': result.get('status') if isinstance(result, dict) else 'completed',
                            'tickets_generated': result.get('metrics', {}).get('total_tickets') if isinstance(result, dict) else None
                        }
                except Exception as e:
                    logger.warning(
                        'workflow_result_unavailable',
                        workflow_id=workflow_id,
                        error=str(e)
                    )

            logger.info(
                'workflow_status_retrieved',
                workflow_id=workflow_id,
                status=status_data['status']
            )
            span.set_attribute("workflow.status", status_data['status'])

            # Cachear resultado (fail-open)
            # TTL baseado no status: workflows em execução = 30s, completados = 5min
            ttl = 30 if status_data['status'] in ['RUNNING', 'PENDING'] else 300
            try:
                await redis_setex_safe(cache_key, ttl, json.dumps(status_data))
            except Exception as cache_err:
                logger.warning('workflow_status_cache_write_error', workflow_id=workflow_id, error=str(cache_err))

            return JSONResponse(status_code=200, content=status_data)

        except Exception as e:
            error_str = str(e)
            span.record_exception(e)

            # Verificar se é erro de workflow não encontrado
            if 'not found' in error_str.lower() or 'does not exist' in error_str.lower():
                logger.warning(
                    'workflow_not_found',
                    workflow_id=workflow_id,
                    error=error_str
                )
                raise HTTPException(
                    status_code=404,
                    detail=f'Workflow {workflow_id} not found'
                )

            logger.error(
                'workflow_status_query_error',
                workflow_id=workflow_id,
                error=error_str
            )
            raise HTTPException(
                status_code=500,
                detail=f'Error retrieving workflow status: {error_str}'
            )


@app.post('/api/v1/workflows/start')
async def start_workflow(request: WorkflowStartRequest):
    """
    Iniciar workflow Temporal para execução de plano cognitivo.

    Este endpoint é chamado pelo FlowCOrchestrator via OrchestratorClient
    para iniciar a execução do Fluxo C (geração de execution tickets).

    Args:
        request: WorkflowStartRequest com cognitive_plan, correlation_id, priority

    Returns:
        WorkflowStartResponse com workflow_id, status e correlation_id

    Raises:
        HTTPException 503: Temporal client não disponível
        HTTPException 500: Erro ao iniciar workflow
    """
    # Validar disponibilidade do Temporal client
    if not app_state.temporal_client:
        logger.warning(
            'workflow_start_rejected',
            reason='temporal_client_unavailable',
            correlation_id=request.correlation_id
        )
        raise HTTPException(
            status_code=503,
            detail='Temporal client not available. Service running in degraded mode.'
        )

    config = get_settings()

    # Gerar workflow_id usando prefixo configurado
    workflow_id = f"{config.temporal_workflow_id_prefix}flow-c-{request.correlation_id}"

    # Extrair dados do plano cognitivo
    plan_id = request.cognitive_plan.get('plan_id', 'unknown')
    intent_id = request.cognitive_plan.get('intent_id', 'unknown')

    # Extrair decision_id do cognitive_plan se disponível, senão usar correlation_id como fallback
    decision_id = request.cognitive_plan.get('decision_id')
    if not decision_id:
        decision_id = request.correlation_id
        logger.debug(
            'decision_id_fallback_used',
            correlation_id=request.correlation_id,
            plan_id=plan_id,
            reason='decision_id not found in cognitive_plan, using correlation_id as fallback'
        )

    # Criar consolidated_decision mínimo para o workflow
    # O workflow espera consolidated_decision com decision_id para as activities
    consolidated_decision = {
        'decision_id': decision_id,  # Usa decision_id do plano ou correlation_id como fallback
        'plan_id': plan_id,
        'intent_id': intent_id,
        'final_decision': 'approve',
        'correlation_id': request.correlation_id,
        'priority': request.priority,
        'sla_deadline_seconds': request.sla_deadline_seconds
    }

    # Construir input_data conforme esperado pelo OrchestrationWorkflow
    input_data = {
        'consolidated_decision': consolidated_decision,
        'cognitive_plan': request.cognitive_plan
    }

    logger.info(
        'workflow_start_attempt',
        workflow_id=workflow_id,
        plan_id=plan_id,
        intent_id=intent_id,
        correlation_id=request.correlation_id,
        priority=request.priority
    )

    try:
        # Iniciar workflow no Temporal
        await app_state.temporal_client.start_workflow(
            OrchestrationWorkflow.run,
            input_data,
            id=workflow_id,
            task_queue=config.temporal_task_queue
        )

        logger.info(
            'workflow_started',
            workflow_id=workflow_id,
            plan_id=plan_id,
            correlation_id=request.correlation_id
        )

        return JSONResponse(
            status_code=200,
            content=WorkflowStartResponse(
                workflow_id=workflow_id,
                status='started',
                correlation_id=request.correlation_id
            ).model_dump()
        )

    except Exception as e:
        logger.error(
            'workflow_start_failed',
            workflow_id=workflow_id,
            plan_id=plan_id,
            correlation_id=request.correlation_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f'Failed to start workflow: {str(e)}'
        )


@app.post('/api/v1/workflows/{workflow_id}/query')
async def query_workflow(workflow_id: str, request: WorkflowQueryRequest):
    """
    Executa query no workflow Temporal para consultar estado.

    Queries disponíveis:
    - get_tickets: Retorna lista de tickets gerados pelo workflow
    - get_status: Retorna status atual do workflow

    Args:
        workflow_id: ID do workflow Temporal
        request: WorkflowQueryRequest com query_name e args opcionais

    Returns:
        WorkflowQueryResponse com resultado da query

    Raises:
        HTTPException 503: Temporal client não disponível
        HTTPException 404: Workflow não encontrado
        HTTPException 500: Erro ao executar query
    """
    from opentelemetry import trace as otel_trace

    tracer = otel_trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "orchestrator.query_workflow",
        attributes={
            "workflow.id": workflow_id,
            "query.name": request.query_name,
        }
    ) as span:
        # Validar disponibilidade do Temporal client
        if not app_state.temporal_client:
            logger.warning(
                'workflow_query_rejected',
                reason='temporal_client_unavailable',
                workflow_id=workflow_id,
                query_name=request.query_name
            )
            raise HTTPException(
                status_code=503,
                detail='Temporal client not available. Service running in degraded mode.'
            )

        # Verificar cache primeiro (para queries de tickets)
        if request.query_name == 'get_tickets':
            cached_tickets = await get_cached_tickets_by_workflow(workflow_id)
            if cached_tickets is not None:
                logger.info(
                    'workflow_query_cache_hit',
                    workflow_id=workflow_id,
                    query_name=request.query_name,
                    tickets_count=len(cached_tickets)
                )
                span.set_attribute("cache.hit", True)
                return JSONResponse(
                    status_code=200,
                    content=WorkflowQueryResponse(
                        workflow_id=workflow_id,
                        query_name=request.query_name,
                        result={"tickets": cached_tickets, "cached": True}
                    ).model_dump()
                )

        logger.info(
            'workflow_query_attempt',
            workflow_id=workflow_id,
            query_name=request.query_name
        )

        try:
            # Obter handle do workflow
            handle = app_state.temporal_client.get_workflow_handle(workflow_id)

            # Executar query
            if request.query_name == 'get_tickets':
                result = await handle.query("get_tickets")
                # Normalizar resultado para dict
                if isinstance(result, list):
                    query_result = {"tickets": result}
                else:
                    query_result = {"tickets": result} if result else {"tickets": []}

                # Cachear resultado (fail-open)
                await cache_tickets_by_workflow(workflow_id, query_result.get("tickets", []))

            elif request.query_name == 'get_status':
                result = await handle.query("get_status")
                query_result = result if isinstance(result, dict) else {"status": result}

            else:
                # Query genérica
                result = await handle.query(request.query_name, *request.args)
                query_result = result if isinstance(result, dict) else {"result": result}

            logger.info(
                'workflow_query_success',
                workflow_id=workflow_id,
                query_name=request.query_name
            )
            span.set_attribute("query.success", True)

            return JSONResponse(
                status_code=200,
                content=WorkflowQueryResponse(
                    workflow_id=workflow_id,
                    query_name=request.query_name,
                    result=query_result
                ).model_dump()
            )

        except Exception as e:
            error_str = str(e)
            span.record_exception(e)

            # Verificar se é erro de workflow não encontrado
            if 'not found' in error_str.lower() or 'does not exist' in error_str.lower():
                logger.warning(
                    'workflow_query_not_found',
                    workflow_id=workflow_id,
                    query_name=request.query_name,
                    error=error_str
                )
                raise HTTPException(
                    status_code=404,
                    detail=f'Workflow {workflow_id} not found'
                )

            logger.error(
                'workflow_query_failed',
                workflow_id=workflow_id,
                query_name=request.query_name,
                error=error_str
            )
            raise HTTPException(
                status_code=500,
                detail=f'Failed to query workflow: {error_str}'
            )


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
