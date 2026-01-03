import asyncio
import signal
import sys
from threading import Thread

import structlog
import uvicorn
from fastapi import FastAPI
from neural_hive_observability import (
    init_observability,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)

from src.clients import (
    MongoDBClient,
    RedisClient,
    ServiceRegistryClient,
    MLflowClient,
    ArgoWorkflowsClient,
    ConsensusEngineGrpcClient,
    OrchestratorGrpcClient,
    AnalystAgentsGrpcClient,
    QueenAgentGrpcClient,
)
from src.clients.clickhouse_client import ClickHouseClient
# Import centralized LoadPredictor
try:
    from neural_hive_ml.predictive_models import LoadPredictor
    from neural_hive_ml.predictive_models.model_registry import ModelRegistry as CentralizedModelRegistry
    ML_CENTRALIZED = True
except ImportError:
    from src.ml import LoadPredictor, ModelRegistry as CentralizedModelRegistry
    ML_CENTRALIZED = False

from src.ml import SchedulingOptimizer, TrainingPipeline
from src.consumers import InsightsConsumer, TelemetryConsumer, ExperimentsConsumer
from src.producers import OptimizationProducer, ExperimentProducer
from src.grpc_service import OptimizerServicer, GrpcServer
from src.config.settings import get_settings
from src.observability.metrics import setup_metrics
from src.services.experiment_manager import ExperimentManager
from src.services.optimization_engine import OptimizationEngine
from src.services.weight_recalibrator import WeightRecalibrator
from src.services.slo_adjuster import SLOAdjuster
from src.api import api_router

logger = structlog.get_logger()

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()

# Global service instances
mongodb_client = None
redis_client = None
service_registry_client = None
mlflow_client = None
argo_client = None
clickhouse_client = None

# gRPC clients
consensus_engine_client = None
orchestrator_client = None
analyst_agents_client = None
queen_agent_client = None

# Kafka consumers and producers
insights_consumer = None
telemetry_consumer = None
experiments_consumer = None
optimization_producer = None
experiment_producer = None

# Services
optimization_engine = None
experiment_manager = None
weight_recalibrator = None
slo_adjuster = None

# ML Subsystem
model_registry = None
load_predictor = None
scheduling_optimizer = None
training_pipeline = None
metrics_instance = None

# gRPC server
grpc_server = None
grpc_task = None

# Background tasks
background_tasks = []
consumer_tasks = []


async def startup():
    """Tarefas de inicialização."""
    global mongodb_client, redis_client, service_registry_client
    global mlflow_client, argo_client, clickhouse_client
    global consensus_engine_client, orchestrator_client, analyst_agents_client, queen_agent_client
    global insights_consumer, telemetry_consumer, experiments_consumer
    global optimization_producer, experiment_producer
    global optimization_engine, experiment_manager, weight_recalibrator, slo_adjuster
    global model_registry, load_predictor, scheduling_optimizer, training_pipeline, metrics_instance
    global grpc_server, grpc_task
    global background_tasks, consumer_tasks

    settings = get_settings()
    logger.info("optimizer_agents_starting", service=settings.service_name, version=settings.service_version)

    # Inicializar observabilidade
    init_observability(
        service_name='optimizer-agents',
        service_version=settings.service_version,
        neural_hive_component='optimizer-agent',
        neural_hive_layer='otimizacao',
        neural_hive_domain='continuous-improvement',
        otel_endpoint=settings.otel_endpoint,
    )
    setup_metrics()
    # Criar instância de métricas para ML subsystem
    from src.observability.metrics import OptimizerMetrics
    metrics_instance = OptimizerMetrics()
    logger.info("observability_initialized")

    # Inicializar clientes de armazenamento
    try:
        # MongoDB
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.connect()
        logger.info("mongodb_client_initialized")

        # Redis
        redis_client = RedisClient(settings)
        await redis_client.connect()
        logger.info("redis_client_initialized")

    except Exception as e:
        logger.error("storage_clients_initialization_failed", error=str(e))
        raise

    # ClickHouse (optional - may not be deployed)
    try:
        clickhouse_client = ClickHouseClient(
            redis_client=redis_client,
            config=settings.model_dump()
        )
        await clickhouse_client.initialize()
        logger.info("clickhouse_client_initialized")
    except Exception as e:
        logger.warning("clickhouse_client_initialization_failed_continuing_without", error=str(e))
        clickhouse_client = None

    # Inicializar clientes gRPC
    try:
        # Consensus Engine
        consensus_engine_client = ConsensusEngineGrpcClient(settings=settings)
        await consensus_engine_client.connect()
        logger.info("consensus_engine_client_initialized")

        # Orchestrator
        orchestrator_client = OrchestratorGrpcClient(settings=settings)
        await orchestrator_client.connect()
        logger.info("orchestrator_client_initialized")

        # Analyst Agents
        analyst_agents_client = AnalystAgentsGrpcClient(settings=settings)
        await analyst_agents_client.connect()
        logger.info("analyst_agents_client_initialized")

        # Queen Agent
        queen_agent_client = QueenAgentGrpcClient(settings=settings)
        await queen_agent_client.connect()
        logger.info("queen_agent_client_initialized")

        # Service Registry
        service_registry_client = ServiceRegistryClient(settings=settings)
        await service_registry_client.connect()
        logger.info("service_registry_client_initialized")

    except Exception as e:
        logger.error("grpc_clients_initialization_failed", error=str(e))
        raise

    # Inicializar clientes de integração
    try:
        # MLflow
        mlflow_client = MLflowClient(settings=settings)
        mlflow_client.connect()
        logger.info("mlflow_client_initialized")

        # Argo Workflows
        argo_client = ArgoWorkflowsClient(settings=settings)
        await argo_client.connect()
        logger.info("argo_client_initialized")

    except Exception as e:
        logger.error("integration_clients_initialization_failed", error=str(e))
        raise

    # Registrar no Service Registry
    if service_registry_client:
        try:
            capabilities = [
                "optimization",
                "experiment_management",
                "reinforcement_learning",
                "causal_analysis",
            ]
            agent_id = await service_registry_client.register(
                capabilities=capabilities,
                metadata={
                    "version": settings.service_version,
                    "environment": settings.environment,
                },
            )
            logger.info("agent_registered", agent_id=agent_id)
        except Exception as e:
            logger.error("agent_registration_failed", error=str(e))

    # Inicializar serviços
    try:
        # NOTA: OptimizationEngine será inicializado APÓS load_predictor para injetá-lo
        optimization_engine = None

        # Experiment Manager
        experiment_manager = ExperimentManager(
            settings=settings,
            argo_client=argo_client,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
        )
        logger.info("experiment_manager_initialized")

        # Weight Recalibrator
        weight_recalibrator = WeightRecalibrator(
            settings=settings,
            consensus_client=consensus_engine_client,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            optimization_producer=None,  # Será definido após inicialização do producer
            metrics=None,  # Será definido após inicialização de métricas
        )
        logger.info("weight_recalibrator_initialized")

        # SLO Adjuster
        slo_adjuster = SLOAdjuster(
            settings=settings,
            orchestrator_client=orchestrator_client,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            optimization_producer=None,  # Será definido após inicialização do producer
            metrics=None,  # Será definido após inicialização de métricas
        )
        logger.info("slo_adjuster_initialized")

        # ML Subsystem initialization
        # ModelRegistry (usando centralizado)
        model_registry = CentralizedModelRegistry(
            tracking_uri=settings.mlflow_tracking_uri,
            experiment_prefix="neural-hive-ml"
        )
        logger.info("model_registry_initialized")

        # LoadPredictor (configurar para centralizado se disponível)
        if ML_CENTRALIZED:
            load_predictor_config = {
                'model_name': 'load-predictor',
                'model_type': 'prophet',
                'forecast_horizons': [60, 360, 1440],
                'seasonality_mode': 'additive',
                'use_synthetic_data': False  # Usar dados reais em produção
            }
            load_predictor = LoadPredictor(
                config=load_predictor_config,
                model_registry=model_registry,
                metrics=metrics_instance,
                data_source=clickhouse_client  # Passa ClickHouse para dados reais
            )
            await load_predictor.initialize()
            logger.info("load_predictor_initialized (centralized with real data)")
        else:
            # Fallback para versão antiga do optimizer
            load_predictor = LoadPredictor(
                clickhouse_client=clickhouse_client,
                redis_client=redis_client,
                model_registry=model_registry,
                metrics=metrics_instance,
                config=settings.model_dump()
            )
            await load_predictor.initialize()
            logger.info("load_predictor_initialized (legacy)")

        # Optimization Engine (agora com load_predictor)
        optimization_engine = OptimizationEngine(
            settings=settings,
            load_predictor=load_predictor,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            consensus_engine_client=consensus_engine_client,
            queen_agent_client=queen_agent_client,
        )
        logger.info("optimization_engine_initialized")

        # SchedulingOptimizer
        scheduling_optimizer = SchedulingOptimizer(
            optimization_engine=optimization_engine,
            experiment_manager=experiment_manager,
            orchestrator_client=orchestrator_client,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            model_registry=model_registry,
            metrics=metrics_instance,
            config=settings.model_dump()
        )
        await scheduling_optimizer.initialize()
        logger.info("scheduling_optimizer_initialized")

        # TrainingPipeline
        training_pipeline = TrainingPipeline(
            load_predictor=load_predictor,
            scheduling_optimizer=scheduling_optimizer,
            model_registry=model_registry,
            clickhouse_client=clickhouse_client,
            mongodb_client=mongodb_client,
            metrics=metrics_instance,
            config=settings.model_dump()
        )
        logger.info("training_pipeline_initialized")

    except Exception as e:
        logger.error("services_initialization_failed", error=str(e))
        raise

    # Inicializar Kafka producers
    try:
        # Optimization Producer
        optimization_producer = OptimizationProducer(settings=settings)
        optimization_producer.start()
        optimization_producer = instrument_kafka_producer(optimization_producer)
        logger.info("optimization_producer_initialized")

        # Experiment Producer
        experiment_producer = ExperimentProducer(settings=settings)
        experiment_producer.start()
        experiment_producer = instrument_kafka_producer(experiment_producer)
        logger.info("experiment_producer_initialized")

        # Atualizar WeightRecalibrator e SLOAdjuster com producer e métricas
        if weight_recalibrator:
            weight_recalibrator.optimization_producer = optimization_producer
            weight_recalibrator.metrics = metrics_instance
        if slo_adjuster:
            slo_adjuster.optimization_producer = optimization_producer
            slo_adjuster.metrics = metrics_instance

    except Exception as e:
        logger.error("kafka_producers_initialization_failed", error=str(e))
        raise

    # Inicializar Kafka consumers
    try:
        # Insights Consumer
        insights_consumer = InsightsConsumer(
            settings=settings,
            optimization_engine=optimization_engine,
        )
        insights_consumer.start()
        insights_consumer = instrument_kafka_consumer(insights_consumer)
        logger.info("insights_consumer_initialized")

        # Telemetry Consumer
        telemetry_consumer = TelemetryConsumer(
            settings=settings,
            optimization_engine=optimization_engine,
        )
        telemetry_consumer.start()
        telemetry_consumer = instrument_kafka_consumer(telemetry_consumer)
        logger.info("telemetry_consumer_initialized")

        # Experiments Consumer
        experiments_consumer = ExperimentsConsumer(
            settings=settings,
            experiment_manager=experiment_manager,
        )
        experiments_consumer.start()
        experiments_consumer = instrument_kafka_consumer(experiments_consumer)
        logger.info("experiments_consumer_initialized")

        logger.info("kafka_consumers_initialized")

    except Exception as e:
        logger.error("kafka_consumers_initialization_failed", error=str(e))
        raise

    # Inicializar servidor gRPC
    try:
        servicer = OptimizerServicer(
            optimization_engine=optimization_engine,
            experiment_manager=experiment_manager,
            weight_recalibrator=weight_recalibrator,
            slo_adjuster=slo_adjuster,
            mongodb_client=mongodb_client,
            load_predictor=load_predictor,
            scheduling_optimizer=scheduling_optimizer,
            settings=settings
        )
        grpc_server = GrpcServer(servicer=servicer, settings=settings)
        grpc_task = asyncio.create_task(grpc_server.start())
        logger.info("grpc_server_started")

    except Exception as e:
        logger.error("grpc_server_initialization_failed", error=str(e))
        # Não falhar se gRPC não estiver disponível

    # Iniciar tarefas em background
    if optimization_engine and experiment_manager:
        # Loop de otimização
        optimization_task = asyncio.create_task(optimization_loop())
        background_tasks.append(optimization_task)
        logger.info("optimization_loop_started")

        # Monitor de experimentos
        experiment_task = asyncio.create_task(experiment_monitor_loop())
        background_tasks.append(experiment_task)
        logger.info("experiment_monitor_loop_started")

        # Heartbeat do Service Registry
        if service_registry_client:
            heartbeat_task = asyncio.create_task(heartbeat_loop())
            background_tasks.append(heartbeat_task)
            logger.info("heartbeat_loop_started")

        # ML Training Pipeline
        if training_pipeline:
            training_task = asyncio.create_task(training_pipeline.start_periodic_training())
            background_tasks.append(training_task)
            logger.info("training_pipeline_started")

    logger.info("optimizer_agents_started")


async def shutdown():
    """Tarefas de encerramento."""
    global mongodb_client, redis_client, service_registry_client
    global mlflow_client, argo_client, clickhouse_client
    global consensus_engine_client, orchestrator_client, analyst_agents_client, queen_agent_client
    global insights_consumer, telemetry_consumer, experiments_consumer
    global optimization_producer, experiment_producer
    global weight_recalibrator, slo_adjuster
    global training_pipeline
    global grpc_server, grpc_task
    global background_tasks, consumer_tasks

    settings = get_settings()
    logger.info("optimizer_agents_shutting_down")

    # Sinalizar shutdown
    shutdown_event.set()

    # Parar TrainingPipeline
    if training_pipeline:
        try:
            await training_pipeline.stop()
            logger.info("training_pipeline_stopped")
        except Exception as e:
            logger.error("training_pipeline_stop_failed", error=str(e))

    # Cancelar tarefas em background
    for task in background_tasks:
        task.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
        logger.info("background_tasks_cancelled")

    # Parar servidor gRPC
    if grpc_server:
        try:
            await grpc_server.stop()
            logger.info("grpc_server_stopped")
        except Exception as e:
            logger.error("grpc_server_stop_failed", error=str(e))

    if grpc_task:
        grpc_task.cancel()
        try:
            await grpc_task
        except asyncio.CancelledError:
            pass

    # Parar Kafka consumers
    if insights_consumer:
        try:
            insights_consumer.stop()
            logger.info("insights_consumer_stopped")
        except Exception as e:
            logger.error("insights_consumer_stop_failed", error=str(e))

    if telemetry_consumer:
        try:
            telemetry_consumer.stop()
            logger.info("telemetry_consumer_stopped")
        except Exception as e:
            logger.error("telemetry_consumer_stop_failed", error=str(e))

    if experiments_consumer:
        try:
            experiments_consumer.stop()
            logger.info("experiments_consumer_stopped")
        except Exception as e:
            logger.error("experiments_consumer_stop_failed", error=str(e))

    # Fechar Kafka producers
    if optimization_producer:
        try:
            optimization_producer.stop()
            logger.info("optimization_producer_stopped")
        except Exception as e:
            logger.error("optimization_producer_stop_failed", error=str(e))

    if experiment_producer:
        try:
            experiment_producer.stop()
            logger.info("experiment_producer_stopped")
        except Exception as e:
            logger.error("experiment_producer_stop_failed", error=str(e))

    # Desregistrar do Service Registry
    if service_registry_client:
        try:
            await service_registry_client.deregister()
            logger.info("agent_deregistered")
        except Exception as e:
            logger.error("agent_deregistration_failed", error=str(e))

    # Fechar clientes gRPC
    if consensus_engine_client:
        try:
            await consensus_engine_client.disconnect()
            logger.info("consensus_engine_client_disconnected")
        except Exception as e:
            logger.error("consensus_engine_client_disconnect_failed", error=str(e))

    if orchestrator_client:
        try:
            await orchestrator_client.disconnect()
            logger.info("orchestrator_client_disconnected")
        except Exception as e:
            logger.error("orchestrator_client_disconnect_failed", error=str(e))

    if analyst_agents_client:
        try:
            await analyst_agents_client.disconnect()
            logger.info("analyst_agents_client_disconnected")
        except Exception as e:
            logger.error("analyst_agents_client_disconnect_failed", error=str(e))

    if queen_agent_client:
        try:
            await queen_agent_client.disconnect()
            logger.info("queen_agent_client_disconnected")
        except Exception as e:
            logger.error("queen_agent_client_disconnect_failed", error=str(e))

    if service_registry_client:
        try:
            await service_registry_client.disconnect()
            logger.info("service_registry_client_disconnected")
        except Exception as e:
            logger.error("service_registry_client_disconnect_failed", error=str(e))

    # Fechar clientes de integração
    if mlflow_client:
        # MLflow não requer desconexão explícita
        logger.info("mlflow_client_closed")

    if argo_client:
        try:
            await argo_client.disconnect()
            logger.info("argo_client_disconnected")
        except Exception as e:
            logger.error("argo_client_disconnect_failed", error=str(e))

    # Fechar conexões de armazenamento
    if clickhouse_client:
        try:
            await clickhouse_client.close()
            logger.info("clickhouse_client_disconnected")
        except Exception as e:
            logger.error("clickhouse_client_disconnect_failed", error=str(e))

    if mongodb_client:
        try:
            await mongodb_client.disconnect()
            logger.info("mongodb_client_disconnected")
        except Exception as e:
            logger.error("mongodb_client_disconnect_failed", error=str(e))

    if redis_client:
        try:
            await redis_client.disconnect()
            logger.info("redis_client_disconnected")
        except Exception as e:
            logger.error("redis_client_disconnect_failed", error=str(e))

    logger.info("optimizer_agents_shutdown_complete")


async def optimization_loop():
    """Tarefa em background para otimização contínua."""
    settings = get_settings()
    while not shutdown_event.is_set():
        try:
            if not optimization_engine or not mongodb_client:
                await asyncio.sleep(10)
                continue

            # Buscar insights recentes do MongoDB
            recent_insights = await mongodb_client.find_recent_insights(
                limit=50,
                priority=["HIGH", "CRITICAL"]
            )

            for insight in recent_insights:
                try:
                    # Gerar hipóteses de otimização
                    hypotheses = await optimization_engine.analyze_opportunity(insight)

                    if hypotheses:
                        logger.info(
                            "optimization_hypotheses_generated",
                            insight_id=insight.get("insight_id"),
                            count=len(hypotheses)
                        )

                        # Submeter hipóteses para validação via ExperimentManager ou aplicação direta
                        if experiment_manager:
                            for hypothesis in hypotheses:
                                if hypothesis.expected_improvement >= settings.min_improvement_threshold:
                                    # Rotear hipótese para o serviço apropriado
                                    from src.models.optimization_event import OptimizationType

                                    if hypothesis.optimization_type == OptimizationType.WEIGHT_RECALIBRATION:
                                        if weight_recalibrator:
                                            await weight_recalibrator.apply_weight_recalibration(hypothesis)
                                    elif hypothesis.optimization_type == OptimizationType.SLO_ADJUSTMENT:
                                        if slo_adjuster:
                                            await slo_adjuster.apply_slo_adjustment(hypothesis)
                                    else:
                                        # Outras otimizações vão para validação experimental
                                        await experiment_manager.validate_hypothesis(hypothesis)

                except Exception as e:
                    logger.error("hypothesis_generation_failed", error=str(e))

            # Executar a cada 60 segundos
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("optimization_loop_cancelled")
            break
        except Exception as e:
            logger.error("optimization_loop_error", error=str(e))
            await asyncio.sleep(10)


async def experiment_monitor_loop():
    """Tarefa em background para monitoramento de experimentos ativos."""
    while not shutdown_event.is_set():
        try:
            if not experiment_manager or not mongodb_client:
                await asyncio.sleep(10)
                continue

            # Buscar experimentos ativos
            active_experiments = await experiment_manager.list_active_experiments()

            for exp in active_experiments:
                try:
                    experiment_id = exp.get("experiment_id")

                    # Monitorar estado do experimento
                    status = await experiment_manager.monitor_experiment(experiment_id)

                    # Pular se monitor_experiment retornou None
                    if not status:
                        logger.debug("experiment_status_unavailable", experiment_id=experiment_id)
                        continue

                    # Verificar timeout
                    if status.get("elapsed_time", 0) > experiment_manager.settings.experiment_timeout_seconds:
                        logger.warning(
                            "experiment_timeout",
                            experiment_id=experiment_id,
                            elapsed=status.get("elapsed_time")
                        )
                        await experiment_manager.abort_experiment(experiment_id, reason="timeout")

                    # Verificar degradação
                    if experiment_manager.settings.rollback_on_degradation:
                        if status.get("performance_degradation", 0) > experiment_manager.settings.degradation_threshold:
                            logger.warning(
                                "experiment_degradation_detected",
                                experiment_id=experiment_id,
                                degradation=status.get("performance_degradation")
                            )

                            # Obter tipo de otimização do MongoDB para rotear rollback
                            experiment_doc = await mongodb_client.get_optimization(experiment_id)
                            if experiment_doc:
                                from src.models.optimization_event import OptimizationType
                                optimization_type = OptimizationType(experiment_doc.get("optimization_type"))

                                # Rotear para o serviço apropriado
                                rollback_success = False
                                if optimization_type == OptimizationType.WEIGHT_RECALIBRATION and weight_recalibrator:
                                    rollback_success = await weight_recalibrator.rollback_weight_recalibration(experiment_id)
                                elif optimization_type == OptimizationType.SLO_ADJUSTMENT and slo_adjuster:
                                    rollback_success = await slo_adjuster.rollback_slo_adjustment(experiment_id)
                                else:
                                    # Rollback padrão via ExperimentManager
                                    rollback_result = await experiment_manager.rollback_experiment(experiment_id)
                                    rollback_success = rollback_result.get("success", False)

                                if rollback_success:
                                    logger.info(
                                        "experiment_rollback_completed",
                                        experiment_id=experiment_id,
                                        optimization_type=optimization_type.value
                                    )
                                else:
                                    logger.error(
                                        "experiment_rollback_failed",
                                        experiment_id=experiment_id,
                                        optimization_type=optimization_type.value
                                    )
                            else:
                                logger.error(
                                    "experiment_not_found_for_rollback",
                                    experiment_id=experiment_id
                                )

                except Exception as e:
                    logger.error("experiment_monitoring_failed", experiment_id=exp.get("experiment_id"), error=str(e))

            # Verificar a cada 30 segundos
            await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("experiment_monitor_loop_cancelled")
            break
        except Exception as e:
            logger.error("experiment_monitor_loop_error", error=str(e))
            await asyncio.sleep(10)


async def heartbeat_loop():
    """Tarefa em background para heartbeat do Service Registry."""
    while not shutdown_event.is_set():
        try:
            if not service_registry_client:
                await asyncio.sleep(10)
                continue

            # Coletar métricas atuais
            metrics = {}

            if experiment_manager and mongodb_client:
                try:
                    # Contar experimentos ativos
                    active_experiments = await experiment_manager.list_active_experiments()
                    metrics["active_experiments"] = len(active_experiments)
                except Exception as e:
                    logger.error("failed_to_count_active_experiments", error=str(e))
                    metrics["active_experiments"] = 0

            if optimization_engine and mongodb_client:
                try:
                    # Contar otimizações aplicadas (últimas 24h)
                    optimizations_count = await mongodb_client.count_recent_optimizations(hours=24)
                    metrics["optimizations_applied_24h"] = optimizations_count
                except Exception as e:
                    logger.error("failed_to_count_optimizations", error=str(e))
                    metrics["optimizations_applied_24h"] = 0

            # Enviar heartbeat
            await service_registry_client.heartbeat(
                health_status="HEALTHY",
                metrics=metrics,
            )

            # Heartbeat a cada 30 segundos
            await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("heartbeat_loop_cancelled")
            break
        except Exception as e:
            logger.error("heartbeat_loop_error", error=str(e))
            await asyncio.sleep(10)


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info("shutdown_signal_received", signal=signum)
    shutdown_event.set()
    sys.exit(0)


# Create FastAPI app
app = FastAPI(
    title="Optimizer Agents",
    description="Continuous Improvement and Policy Recalibration",
    version="1.0.0",
)

# Include API routers
app.include_router(api_router)

app.add_event_handler("startup", startup)
app.add_event_handler("shutdown", shutdown)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
