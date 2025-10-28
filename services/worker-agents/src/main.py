import asyncio
import signal
import structlog
import uvicorn
from contextlib import asynccontextmanager

from .config import get_settings
from .clients import (
    ServiceRegistryClient,
    ExecutionTicketClient,
    KafkaTicketConsumer,
    KafkaResultProducer
)
from .engine import ExecutionEngine, DependencyCoordinator
from .executors import (
    TaskExecutorRegistry,
    BuildExecutor,
    DeployExecutor,
    TestExecutor,
    ValidateExecutor,
    ExecuteExecutor
)
from .api import create_http_server
from .observability import init_metrics
from neural_hive_integration import ServiceRegistryClient as IntegrationServiceRegistry

# Configurar logging estruturado
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# State global
app_state = {}


@asynccontextmanager
async def lifespan(app):
    '''Lifecycle manager para FastAPI'''
    # Startup
    await startup()
    yield
    # Shutdown
    await shutdown()


async def startup():
    '''Inicialização do Worker Agent'''
    try:
        config = get_settings()
        logger.info(
            'worker_agent_starting',
            agent_id=config.agent_id,
            namespace=config.namespace,
            cluster=config.cluster
        )

        # Inicializar métricas
        metrics = init_metrics(config)
        metrics.startup_total.inc()
        app_state['metrics'] = metrics

        # Inicializar clientes
        registry_client = ServiceRegistryClient(config)
        await registry_client.initialize()
        app_state['registry_client'] = registry_client

        ticket_client = ExecutionTicketClient(config)
        await ticket_client.initialize()
        app_state['ticket_client'] = ticket_client

        result_producer = KafkaResultProducer(config)
        await result_producer.initialize()
        app_state['result_producer'] = result_producer

        # Criar componentes de execução
        dependency_coordinator = DependencyCoordinator(config, ticket_client)
        app_state['dependency_coordinator'] = dependency_coordinator

        # Criar e configurar registry de executores
        executor_registry = TaskExecutorRegistry(config)
        executor_registry.register_executor(BuildExecutor(config))
        executor_registry.register_executor(DeployExecutor(config))
        executor_registry.register_executor(TestExecutor(config))
        executor_registry.register_executor(ValidateExecutor(config))
        executor_registry.register_executor(ExecuteExecutor(config))
        executor_registry.validate_configuration()
        app_state['executor_registry'] = executor_registry

        # Criar execution engine
        execution_engine = ExecutionEngine(
            config,
            ticket_client,
            result_producer,
            dependency_coordinator,
            executor_registry
        )
        app_state['execution_engine'] = execution_engine

        # Criar Kafka consumer
        kafka_consumer = KafkaTicketConsumer(config, execution_engine)
        await kafka_consumer.initialize()
        app_state['kafka_consumer'] = kafka_consumer

        # Registrar no Service Registry
        agent_id = await registry_client.register()
        logger.info('worker_agent_registered', agent_id=agent_id)

        # Registrar também via integration library (para descoberta pelo Flow C)
        integration_registry = IntegrationServiceRegistry()
        app_state['integration_registry'] = integration_registry
        from neural_hive_integration import AgentInfo
        await integration_registry.register_agent(AgentInfo(
            agent_id=config.agent_id,
            agent_type="worker",
            capabilities=config.capabilities if hasattr(config, 'capabilities') else ["python", "terraform", "kubernetes"],
            endpoint=f"http://{config.agent_id}.neural-hive-execution:8000",
            metadata={"version": "1.0.0"}
        ))

        # Iniciar background tasks
        app_state['heartbeat_task'] = asyncio.create_task(heartbeat_loop(config, registry_client))
        app_state['consumer_task'] = asyncio.create_task(kafka_consumer.start())

        logger.info('worker_agent_started', agent_id=config.agent_id)

    except Exception as e:
        logger.error('worker_agent_startup_failed', error=str(e), exc_info=True)
        raise


async def shutdown():
    '''Shutdown graceful do Worker Agent'''
    try:
        logger.info('worker_agent_shutting_down')

        config = get_settings()

        # Parar background tasks
        if 'heartbeat_task' in app_state:
            app_state['heartbeat_task'].cancel()

        if 'consumer_task' in app_state:
            app_state['consumer_task'].cancel()

        # Shutdown execution engine
        if 'execution_engine' in app_state:
            await app_state['execution_engine'].shutdown(timeout_seconds=30)

        # Deregistrar do Service Registry
        if 'integration_registry' in app_state:
            await app_state['integration_registry'].deregister_agent(config.agent_id)
            await app_state['integration_registry'].close()

        if 'registry_client' in app_state:
            await app_state['registry_client'].deregister()
            await app_state['registry_client'].close()

        # Fechar clientes
        if 'kafka_consumer' in app_state:
            await app_state['kafka_consumer'].stop()

        if 'result_producer' in app_state:
            await app_state['result_producer'].stop()

        if 'ticket_client' in app_state:
            await app_state['ticket_client'].close()

        logger.info('worker_agent_shutdown_complete')

    except Exception as e:
        logger.error('worker_agent_shutdown_failed', error=str(e), exc_info=True)


async def heartbeat_loop(config, registry_client):
    '''Loop de heartbeat ao Service Registry'''
    while True:
        try:
            await asyncio.sleep(config.heartbeat_interval_seconds)

            # Coletar telemetria
            execution_engine = app_state.get('execution_engine')
            telemetry = {
                'active_tasks': len(execution_engine.active_tasks) if execution_engine else 0,
                'timestamp': asyncio.get_event_loop().time()
            }

            # Enviar heartbeat
            success = await registry_client.heartbeat(telemetry)

            if success:
                logger.debug('heartbeat_sent', telemetry=telemetry)
            else:
                logger.warning('heartbeat_failed')

        except asyncio.CancelledError:
            logger.info('heartbeat_loop_cancelled')
            break
        except Exception as e:
            logger.error('heartbeat_loop_error', error=str(e))
            await asyncio.sleep(5)  # Backoff em caso de erro


def signal_handler(signum, frame):
    '''Handler para sinais de shutdown'''
    logger.info('signal_received', signal=signum)
    # Shutdown será tratado pelo lifespan manager


async def main():
    '''Entry point principal'''
    config = get_settings()

    # Registrar signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Criar HTTP server
    app = create_http_server(config, app_state)
    app.router.lifespan_context = lifespan

    # Iniciar servidor HTTP
    uvicorn_config = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=config.http_port,
        log_level=config.log_level.lower()
    )
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


if __name__ == '__main__':
    asyncio.run(main())
