"""
Temporal Worker para executar workflows e activities.
"""
from temporalio.client import Client
from temporalio.worker import Worker
import structlog

from src.scheduler import IntelligentScheduler, PriorityCalculator, ResourceAllocator
from src.scheduler.affinity_tracker import AffinityTracker
from src.clients.service_registry_client import ServiceRegistryClient
from src.observability.metrics import get_metrics
from src.policies import OPAClient, PolicyValidator

logger = structlog.get_logger()


class TemporalWorkerManager:
    """Gerencia o Temporal Worker."""

    def __init__(
        self,
        config,
        temporal_client: Client,
        kafka_producer=None,
        mongodb_client=None,
        registry_client=None,
        vault_client=None,
        optimizer_client=None,
        scheduling_predictor=None,
        load_predictor=None,
        anomaly_detector=None,
        self_healing_client=None
    ):
        """
        Inicializa o worker manager.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal
            kafka_producer: Cliente Kafka Producer (opcional)
            mongodb_client: Cliente MongoDB (opcional)
            registry_client: Cliente do Service Registry (opcional)
            vault_client: Cliente Vault para integração SPIFFE/Vault (opcional)
            optimizer_client: Cliente Optimizer gRPC (opcional)
            scheduling_predictor: Preditor de duração/recursos centralizado (opcional)
            load_predictor: Preditor de carga centralizado (opcional)
            anomaly_detector: Detector de anomalias centralizado (opcional)
        """
        self.config = config
        self.temporal_client = temporal_client
        self.kafka_producer = kafka_producer
        self.mongodb_client = mongodb_client
        self.registry_client = registry_client
        self.vault_client = vault_client
        self.optimizer_client = optimizer_client
        self.scheduling_predictor = scheduling_predictor
        self.load_predictor = load_predictor
        self.anomaly_detector = anomaly_detector
        self.self_healing_client = self_healing_client
        self.intelligent_scheduler = None
        self.opa_client = None
        self.policy_validator = None
        self.ml_predictor = None
        self.training_pipeline = None
        self.promotion_manager = None
        self.worker = None
        self.running = False

    async def initialize(self):
        """Inicializa o Temporal Worker."""
        logger.info('Inicializando Temporal Worker', task_queue=self.config.temporal_task_queue)

        # Inicializar Service Registry Client e Intelligent Scheduler se habilitado
        if self.config.enable_intelligent_scheduler:
            logger.info('Inicializando Service Registry Client para scheduler')

            try:
                # Obter SPIFFE manager do Vault client se disponível
                spiffe_manager = None
                if self.vault_client and hasattr(self.vault_client, 'spiffe_manager'):
                    spiffe_manager = self.vault_client.spiffe_manager
                    logger.info(
                        'SPIFFE manager disponível para Service Registry authentication',
                        spiffe_enabled=self.config.spiffe_enabled
                    )

                # Criar Service Registry Client com SPIFFE manager
                registry_client = ServiceRegistryClient(
                    self.config,
                    spiffe_manager=spiffe_manager
                )
                await registry_client.initialize()
                self.registry_client = registry_client

                # Criar componentes do scheduler
                metrics = get_metrics()
                priority_calculator = PriorityCalculator(self.config)

                # Inicializar SchedulingOptimizer se habilitado
                scheduling_optimizer = None
                if self.config.ml_local_load_prediction_enabled or self.config.enable_optimizer_integration:
                    logger.info('Inicializando ML Scheduling Optimizer')

                    try:
                        from src.ml.load_predictor import LoadPredictor
                        from src.ml.scheduling_optimizer import SchedulingOptimizer
                        from src.clients.redis_client import get_redis_client

                        # Criar Redis client para cache
                        redis_client = await get_redis_client(self.config)

                        # Criar LoadPredictor local (funciona com ou sem MongoDB)
                        load_predictor = LoadPredictor(
                            config=self.config,
                            mongodb_client=self.mongodb_client,  # Pode ser None
                            redis_client=redis_client,
                            metrics=metrics
                        )

                        # Criar SchedulingOptimizer com remote + local
                        scheduling_optimizer = SchedulingOptimizer(
                            config=self.config,
                            optimizer_client=self.optimizer_client,  # Pode ser None
                            local_predictor=load_predictor,
                            kafka_producer=self.kafka_producer,
                            metrics=metrics
                        )

                        # Log de inicialização com status de dependências
                        logger.info(
                            'ML Scheduling Optimizer inicializado',
                            local_enabled=self.config.ml_local_load_prediction_enabled,
                            remote_enabled=self.config.enable_optimizer_integration,
                            mongodb_available=self.mongodb_client is not None,
                            redis_available=redis_client is not None,
                            mode='degraded' if not self.mongodb_client else 'full'
                        )

                        if not self.mongodb_client:
                            logger.warning(
                                'ML Scheduling Optimizer rodando em modo degradado (sem MongoDB)',
                                impact='Predições locais usarão apenas defaults, sem dados históricos'
                            )

                    except Exception as e:
                        logger.warning(
                            'Falha ao inicializar Scheduling Optimizer, usando scheduler sem ML',
                            error=str(e)
                        )
                        scheduling_optimizer = None

                # Criar AffinityTracker se affinity habilitado
                affinity_tracker = None
                if getattr(self.config, 'scheduler_enable_affinity', False) and redis_client:
                    try:
                        affinity_tracker = AffinityTracker(
                            redis_client=redis_client,
                            config=self.config,
                            metrics=metrics
                        )
                        logger.info(
                            'AffinityTracker inicializado',
                            cache_ttl_seconds=getattr(self.config, 'scheduler_affinity_cache_ttl_seconds', 14400)
                        )
                    except Exception as e:
                        logger.warning(
                            'Falha ao inicializar AffinityTracker, continuando sem affinity',
                            error=str(e)
                        )
                        affinity_tracker = None

                # Criar ResourceAllocator com scheduling_optimizer e affinity_tracker
                resource_allocator = ResourceAllocator(
                    registry_client=registry_client,
                    config=self.config,
                    metrics=metrics,
                    scheduling_optimizer=scheduling_optimizer,
                    affinity_tracker=affinity_tracker
                )

                # Criar Intelligent Scheduler (com modelos centralizados se disponíveis)
                self.intelligent_scheduler = IntelligentScheduler(
                    config=self.config,
                    metrics=metrics,
                    priority_calculator=priority_calculator,
                    resource_allocator=resource_allocator,
                    scheduling_optimizer=scheduling_optimizer,
                    scheduling_predictor=self.scheduling_predictor,
                    load_predictor=self.load_predictor,
                    anomaly_detector=self.anomaly_detector
                )

                logger.info('Intelligent Scheduler inicializado')

            except Exception as e:
                logger.warning(
                    'Falha ao inicializar Intelligent Scheduler, scheduler desabilitado',
                    error=str(e)
                )
                self.intelligent_scheduler = None

        # Inicializar OPA Client e PolicyValidator se habilitado
        if self.config.opa_enabled:
            logger.info('Inicializando OPA Policy Engine')

            try:
                # Criar OPA Client
                self.opa_client = OPAClient(self.config)
                await self.opa_client.initialize()

                # Criar PolicyValidator
                self.policy_validator = PolicyValidator(self.opa_client, self.config)

                logger.info('OPA Policy Engine inicializado', opa_host=self.config.opa_host)

            except Exception as e:
                logger.error(f'Falha ao inicializar OPA: {e}', exc_info=True)
                if not self.config.opa_fail_open:
                    raise
                logger.warning('OPA desabilitado devido a erro de inicialização (fail-open)')
                self.policy_validator = None
        else:
            logger.info('OPA Policy Engine desabilitado por configuração')

        # Inicializar ML Predictor se habilitado
        if self.config.ml_predictions_enabled and self.mongodb_client:
            logger.info('Inicializando ML Predictor')

            try:
                from src.ml import ModelRegistry, MLPredictor, TrainingPipeline, ModelPromotionManager

                # Criar Model Registry
                model_registry = ModelRegistry(self.config)
                await model_registry.initialize()

                # Criar ML Predictor
                metrics = get_metrics()
                ml_predictor = MLPredictor(
                    config=self.config,
                    mongodb_client=self.mongodb_client,
                    model_registry=model_registry,
                    metrics=metrics
                )
                await ml_predictor.initialize()
                self.ml_predictor = ml_predictor

                # Criar Model Promotion Manager (Shadow Mode)
                if self.config.ml_shadow_mode_enabled:
                    promotion_manager = ModelPromotionManager(
                        config=self.config,
                        mongodb_client=self.mongodb_client,
                        model_registry=model_registry,
                        metrics=metrics
                    )
                    await promotion_manager.initialize()
                    self.promotion_manager = promotion_manager

                    # Injetar promotion_manager nos predictors para Shadow Mode
                    ml_predictor.duration_predictor.promotion_manager = promotion_manager
                    ml_predictor.anomaly_detector.promotion_manager = promotion_manager

                    logger.info(
                        'ModelPromotionManager inicializado com Shadow Mode',
                        shadow_mode_duration_minutes=self.config.ml_shadow_mode_duration_minutes,
                        shadow_mode_min_predictions=self.config.ml_shadow_mode_min_predictions
                    )
                else:
                    self.promotion_manager = None
                    logger.info('Shadow Mode desabilitado por configuração')

                # Criar Training Pipeline
                training_pipeline = TrainingPipeline(
                    config=self.config,
                    mongodb_client=self.mongodb_client,
                    model_registry=model_registry,
                    duration_predictor=ml_predictor.duration_predictor,
                    anomaly_detector=ml_predictor.anomaly_detector,
                    metrics=metrics
                )
                self.training_pipeline = training_pipeline

                # Agendar treinamento periódico
                await training_pipeline.schedule_periodic_training(
                    interval_hours=self.config.ml_training_interval_hours
                )

                logger.info(
                    'ML Predictor inicializado com sucesso',
                    training_interval_hours=self.config.ml_training_interval_hours
                )

            except Exception as e:
                logger.warning(
                    'Falha ao inicializar ML Predictor (continuando sem predições)',
                    error=str(e)
                )
                self.ml_predictor = None
                self.training_pipeline = None
        else:
            if not self.config.ml_predictions_enabled:
                logger.info('ML Predictions desabilitado por configuração')
            else:
                logger.warning('ML Predictions desabilitado - MongoDB não disponível')

        # Import workflows e activities
        from src.workflows.orchestration_workflow import OrchestrationWorkflow
        from src.activities.plan_validation import (
            validate_cognitive_plan,
            audit_validation,
            optimize_dag,
            set_activity_dependencies as set_validation_deps
        )
        from src.activities.ticket_generation import (
            generate_execution_tickets,
            allocate_resources,
            publish_ticket_to_kafka,
            set_activity_dependencies as set_generation_deps
        )
        from src.activities.result_consolidation import (
            consolidate_results,
            trigger_self_healing,
            publish_telemetry,
            buffer_telemetry,
            set_activity_dependencies as set_consolidation_deps
        )

        # Injetar PolicyValidator e MongoDB nas activities de validação (fail-open)
        if self.policy_validator:
            set_validation_deps(
                policy_validator=self.policy_validator,
                config=self.config,
                mongodb_client=self.mongodb_client
            )
            logger.info('PolicyValidator injetado em plan_validation activities')
        else:
            set_validation_deps(
                policy_validator=None,
                config=self.config,
                mongodb_client=self.mongodb_client
            )
            logger.info('plan_validation activities configuradas sem PolicyValidator')

        # Injetar dependências em ticket_generation (requer Kafka e MongoDB)
        if self.kafka_producer and self.mongodb_client:
            set_generation_deps(
                self.kafka_producer,
                self.mongodb_client,
                self.registry_client,
                self.intelligent_scheduler,
                self.policy_validator,
                self.config,
                self.ml_predictor
            )

            logger.info(
                'Dependências injetadas nas ticket_generation activities',
                kafka_enabled=True,
                mongodb_enabled=True,
                registry_enabled=self.registry_client is not None,
                scheduler_enabled=self.intelligent_scheduler is not None,
                opa_enabled=self.policy_validator is not None,
                ml_predictor_enabled=self.ml_predictor is not None
            )
        else:
            logger.warning('Kafka Producer ou MongoDB Client não fornecidos - ticket_generation activities podem falhar')

        # Injetar dependências em result_consolidation (fail-open)
        set_consolidation_deps(
            scheduling_optimizer=getattr(self.intelligent_scheduler, 'scheduling_optimizer', None)
            if self.intelligent_scheduler else None,
            config=self.config,
            mongodb_client=self.mongodb_client,
            kafka_producer=self.kafka_producer,
            self_healing_client=self.self_healing_client
        )

        # Criar Worker
        self.worker = Worker(
            self.temporal_client,
            task_queue=self.config.temporal_task_queue,
            workflows=[OrchestrationWorkflow],
            activities=[
                validate_cognitive_plan,
                audit_validation,
                optimize_dag,
                generate_execution_tickets,
                allocate_resources,
                publish_ticket_to_kafka,
                consolidate_results,
                trigger_self_healing,
                publish_telemetry,
                buffer_telemetry
            ],
            max_concurrent_workflow_tasks=10,
            max_concurrent_activities=50
        )

        logger.info('Temporal Worker inicializado com sucesso')

    async def start(self):
        """Inicia o worker."""
        if not self.worker:
            raise RuntimeError('Worker não foi inicializado. Chame initialize() primeiro.')

        logger.info('Iniciando Temporal Worker')
        self.running = True

        await self.worker.run()

    async def stop(self):
        """Para o worker gracefully."""
        logger.info('Parando Temporal Worker')
        self.running = False

        # Fechar Service Registry Client se existir
        if self.registry_client:
            logger.info('Fechando Service Registry Client')
            try:
                await self.registry_client.close()
            except Exception as e:
                logger.warning('Erro ao fechar Service Registry Client', error=str(e))

        # Fechar OPA Client se existir
        if self.opa_client:
            logger.info('Fechando OPA Client')
            try:
                await self.opa_client.close()
            except Exception as e:
                logger.warning('Erro ao fechar OPA Client', error=str(e))

        # Fechar Model Promotion Manager se existir
        if self.promotion_manager:
            logger.info('Fechando Model Promotion Manager')
            try:
                await self.promotion_manager.close()
            except Exception as e:
                logger.warning('Erro ao fechar Model Promotion Manager', error=str(e))

        # Parar Training Pipeline se existir
        if self.training_pipeline:
            logger.info('Parando Training Pipeline')
            try:
                await self.training_pipeline.stop_periodic_training()
            except Exception as e:
                logger.warning('Erro ao parar Training Pipeline', error=str(e))

        # Fechar ML Predictor se existir
        if self.ml_predictor:
            logger.info('Fechando ML Predictor')
            try:
                await self.ml_predictor.close()
            except Exception as e:
                logger.warning('Erro ao fechar ML Predictor', error=str(e))

        # Temporal SDK gerencia shutdown automaticamente


def _build_temporal_target(host: str, port: int) -> str:
    """
    Constrói target URL do Temporal de forma robusta.

    Trata casos onde host já contém porta (ex: temporal-frontend:7233)
    para evitar duplicação (temporal-frontend:7233:7233).

    Args:
        host: Hostname do Temporal (pode incluir porta)
        port: Porta do Temporal (usado apenas se host não incluir porta)

    Returns:
        Target URL no formato host:port
    """
    # Se host já contém porta (formato host:port), usar diretamente
    if ':' in host:
        return host

    # Caso contrário, concatenar host e port
    return f'{host}:{port}'


async def create_temporal_client(config, postgres_user=None, postgres_password=None) -> Client:
    """
    Cria cliente Temporal com conexão imediata.

    IMPORTANTE: Workers do Temporal requerem conexão eager (lazy=False).
    Lazy clients não são suportados para workers.

    Args:
        config: Configurações da aplicação
        postgres_user: PostgreSQL user override (ex: de Vault)
        postgres_password: PostgreSQL password override (ex: de Vault)

    Returns:
        Cliente Temporal conectado, ou None se temporal_enabled=False

    Raises:
        Exception: Se conexão falhar e temporal_enabled=True
    """
    # Verificar se Temporal está habilitado
    temporal_enabled = getattr(config, 'temporal_enabled', True)
    if not temporal_enabled:
        logger.info('Temporal desabilitado via configuração (temporal_enabled=False)')
        return None

    # Construir target URL de forma robusta (evita porta duplicada)
    target = _build_temporal_target(config.temporal_host, config.temporal_port)

    logger.info(
        'Conectando ao Temporal Server',
        target=target,
        namespace=config.temporal_namespace
    )

    try:
        # Workers requerem conexão eager (lazy=False é o padrão)
        # lazy=True NÃO é suportado para workers - causa RuntimeError
        client = await Client.connect(
            target,
            namespace=config.temporal_namespace,
            # lazy=False é o padrão - conexão imediata necessária para workers
            # tls=config.temporal_tls_enabled  # Configurar TLS para produção
        )

        logger.info('Cliente Temporal conectado com sucesso', target=target)
        return client

    except Exception as e:
        logger.error('Erro ao conectar ao Temporal Server', error=str(e), target=target, exc_info=True)
        raise
