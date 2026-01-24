import asyncio
import signal
import structlog
import uvicorn
from contextlib import asynccontextmanager

from neural_hive_observability import (
    get_tracer,
    init_observability,
    instrument_grpc_channel,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)
from .config import get_settings
from .clients import (
    ServiceRegistryClient,
    ExecutionTicketClient,
    KafkaTicketConsumer,
    KafkaDLQConsumer,
    KafkaResultProducer,
    MongoDBClient,
    DLQAlertManager
)
from .engine import ExecutionEngine, DependencyCoordinator
from .clients.redis_client import get_redis_client, close_redis_client
from .executors import (
    TaskExecutorRegistry,
    BuildExecutor,
    DeployExecutor,
    TestExecutor,
    ValidateExecutor,
    ExecuteExecutor,
    CompensateExecutor
)
from .api import create_http_server
from .observability import init_metrics
from neural_hive_integration import ServiceRegistryClient as IntegrationServiceRegistry
from neural_hive_integration.clients.code_forge_client import CodeForgeClient

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

        init_observability(
            service_name='worker-agents',
            service_version='1.0.0',
            neural_hive_component='worker-agent',
            neural_hive_layer='execucao',
            neural_hive_domain='task-execution',
            otel_endpoint=config.otel_exporter_endpoint,
        )

        # Inicializar métricas
        metrics = init_metrics(config)
        metrics.startup_total.inc()
        app_state['metrics'] = metrics

        # Inicializar SPIFFE Manager (independente de Vault)
        spiffe_manager = None
        if config.spiffe_enabled:
            try:
                from neural_hive_security import SPIFFEManager, SPIFFEConfig
                logger.info('Inicializando SPIFFE integration')
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=config.spiffe_socket_path,
                    trust_domain=config.spiffe_trust_domain,
                    jwt_audience=config.spiffe_jwt_audience,
                    jwt_ttl_seconds=config.spiffe_jwt_ttl_seconds,
                )
                spiffe_manager = SPIFFEManager(spiffe_config)
                await spiffe_manager.initialize()
                app_state['spiffe_manager'] = spiffe_manager
                logger.info('SPIFFE integration inicializada com sucesso')
            except ImportError:
                logger.warning('SPIFFE habilitado mas biblioteca neural-hive-security não disponível')
            except Exception as e:
                logger.error('Erro ao inicializar SPIFFE integration', error=str(e))
                raise
        else:
            logger.info('SPIFFE integration desabilitada')

        # Inicializar Vault integration se habilitado
        vault_client = None
        if config.vault_enabled:
            try:
                from .clients.vault_integration import WorkerVaultClient
                logger.info('Inicializando Vault integration')
                vault_client = WorkerVaultClient(config, spiffe_manager=spiffe_manager)
                await vault_client.initialize()
                app_state['vault_client'] = vault_client
                logger.info('Vault integration inicializado com sucesso')
            except ImportError:
                logger.warning('Vault habilitado mas biblioteca neural-hive-security não disponível')
            except Exception as e:
                logger.error('Erro ao inicializar Vault integration', error=str(e))
                if not config.vault_fail_open:
                    raise
        else:
            logger.info('Vault integration desabilitada')

        # Inicializar clientes
        registry_client = ServiceRegistryClient(config)
        await registry_client.initialize()
        app_state['registry_client'] = registry_client

        ticket_client = ExecutionTicketClient(config, metrics=metrics)
        await ticket_client.initialize()
        app_state['ticket_client'] = ticket_client

        # Inicializar Code Forge client se habilitado
        code_forge_client = None
        if config.code_forge_enabled:
            try:
                code_forge_client = CodeForgeClient(
                    base_url=config.code_forge_url,
                    timeout=config.code_forge_timeout_seconds
                )
                app_state['code_forge_client'] = code_forge_client
                logger.info('code_forge_client_initialized', url=config.code_forge_url)
            except Exception as e:
                logger.warning('code_forge_client_init_failed', error=str(e))

        # Inicializar ArgoCD client se habilitado
        argocd_client = None
        if getattr(config, 'argocd_enabled', False) and config.argocd_url:
            try:
                from .clients.argocd_client import ArgoCDClient
                argocd_client = ArgoCDClient(
                    base_url=config.argocd_url,
                    token=config.argocd_token,
                    timeout=600
                )
                app_state['argocd_client'] = argocd_client
                logger.info('argocd_client_initialized', url=config.argocd_url)
            except Exception as e:
                logger.warning('argocd_client_init_failed', error=str(e))

        # Inicializar Flux client se habilitado
        flux_client = None
        if getattr(config, 'flux_enabled', False):
            try:
                from .clients.flux_client import FluxClient
                flux_client = FluxClient(
                    kubeconfig_path=getattr(config, 'flux_kubeconfig_path', None),
                    namespace=getattr(config, 'flux_namespace', 'flux-system'),
                    timeout=getattr(config, 'flux_timeout_seconds', 600)
                )
                await flux_client.initialize()
                app_state['flux_client'] = flux_client
                logger.info('flux_client_initialized', namespace=config.flux_namespace)
            except ImportError:
                logger.warning('flux_client_init_failed', error='kubernetes-asyncio not installed')
            except Exception as e:
                logger.warning('flux_client_init_failed', error=str(e))

        # Get Kafka credentials from Vault se habilitado
        kafka_username = None
        kafka_password = None
        kafka_creds = None
        if vault_client:
            logger.info('Buscando credenciais Kafka do Vault')
            kafka_creds = await vault_client.get_kafka_credentials()
            kafka_username = kafka_creds.get('username')
            kafka_password = kafka_creds.get('password')

        result_producer = KafkaResultProducer(
            config,
            sasl_username_override=kafka_username,
            sasl_password_override=kafka_password,
            metrics=metrics
        )
        await result_producer.initialize()
        result_producer = instrument_kafka_producer(result_producer)
        app_state['result_producer'] = result_producer

        # Registrar callback para rotação de credenciais Kafka
        if vault_client and kafka_creds and kafka_creds.get('ttl', 0) > 0:
            async def _kafka_credential_update_callback(new_creds):
                """Callback para recriar KafkaResultProducer com novas credenciais."""
                try:
                    logger.info(
                        'Recriando KafkaResultProducer com novas credenciais',
                        ttl=new_creds.get('ttl', 0)
                    )
                    # Parar producer antigo
                    old_producer = app_state.get('result_producer')
                    if old_producer:
                        await old_producer.stop()

                    # Criar novo producer com credenciais atualizadas
                    new_producer = KafkaResultProducer(
                        config,
                        sasl_username_override=new_creds.get('username'),
                        sasl_password_override=new_creds.get('password'),
                        metrics=metrics
                    )
                    await new_producer.initialize()
                    new_producer = instrument_kafka_producer(new_producer)
                    app_state['result_producer'] = new_producer

                    # Atualizar referência no execution engine
                    if 'execution_engine' in app_state:
                        app_state['execution_engine'].result_producer = new_producer

                    logger.info('KafkaResultProducer recriado com sucesso')
                except Exception as e:
                    logger.error(
                        'Falha ao recriar KafkaResultProducer',
                        error=str(e)
                    )
                    raise

            vault_client.set_kafka_credential_callback(_kafka_credential_update_callback)
            logger.info('Callback de rotação de credenciais Kafka registrado')

        # Inicializar GitHub Actions client se habilitado
        github_actions_client = None
        if getattr(config, 'github_actions_enabled', False) and config.github_token:
            try:
                from .clients.github_actions_client import GitHubActionsClient
                github_actions_client = GitHubActionsClient.from_env(config)
                await github_actions_client.start()
                app_state['github_actions_client'] = github_actions_client
                logger.info('github_actions_client_initialized')
            except Exception as e:
                logger.warning('github_actions_client_init_failed', error=str(e))

        # Inicializar GitLab CI client se habilitado
        gitlab_ci_client = None
        if getattr(config, 'gitlab_ci_enabled', False) and config.gitlab_token:
            try:
                from .clients.gitlab_ci_client import GitLabCIClient
                gitlab_ci_client = GitLabCIClient.from_env(config)
                await gitlab_ci_client.start()
                app_state['gitlab_ci_client'] = gitlab_ci_client
                logger.info('gitlab_ci_client_initialized')
            except Exception as e:
                logger.warning('gitlab_ci_client_init_failed', error=str(e))

        # Inicializar Jenkins client se habilitado
        jenkins_client = None
        if getattr(config, 'jenkins_enabled', False) and config.jenkins_url and config.jenkins_token:
            try:
                from .clients.jenkins_client import JenkinsClient
                jenkins_client = JenkinsClient.from_env(config)
                await jenkins_client.start()
                app_state['jenkins_client'] = jenkins_client
                logger.info('jenkins_client_initialized', url=config.jenkins_url)
            except Exception as e:
                logger.warning('jenkins_client_init_failed', error=str(e))

        # Inicializar Redis Client para deduplicação de tickets (fail-open)
        redis_client = None
        try:
            logger.info('Inicializando Redis Client para deduplicação de tickets')
            redis_client = await get_redis_client(config)
            if redis_client:
                app_state['redis_client'] = redis_client
                logger.info('Redis Client inicializado com sucesso')
            else:
                logger.warning('Redis Client retornou None - operando sem deduplicação')
        except Exception as redis_error:
            logger.warning(
                'Falha ao inicializar Redis Client, continuando sem deduplicação',
                error=str(redis_error)
            )
            redis_client = None

        # Criar componentes de execução
        dependency_coordinator = DependencyCoordinator(config, ticket_client, metrics=metrics)
        app_state['dependency_coordinator'] = dependency_coordinator

        # Inicializar OPA client se habilitado
        opa_client = None
        if getattr(config, 'opa_enabled', False) and config.opa_url:
            try:
                from .clients.opa_client import OPAClient
                opa_client = OPAClient(
                    base_url=config.opa_url,
                    token=getattr(config, 'opa_token', None),
                    timeout=getattr(config, 'opa_timeout_seconds', 30),
                    verify_ssl=getattr(config, 'opa_verify_ssl', True),
                    retry_attempts=getattr(config, 'opa_retry_attempts', 3),
                    retry_backoff_base=getattr(config, 'opa_retry_backoff_base_seconds', 2),
                    retry_backoff_max=getattr(config, 'opa_retry_backoff_max_seconds', 60),
                )
                app_state['opa_client'] = opa_client
                logger.info('opa_client_initialized', url=config.opa_url)
            except Exception as e:
                logger.warning('opa_client_init_failed', error=str(e))

        # Inicializar Docker Runtime client se habilitado
        docker_client = None
        if getattr(config, 'docker_enabled', False):
            try:
                from .clients.docker_runtime_client import DockerRuntimeClient
                docker_client = DockerRuntimeClient(
                    base_url=config.docker_base_url,
                    timeout=config.docker_timeout_seconds,
                    verify_ssl=config.docker_verify_ssl,
                    default_cpu_limit=config.docker_default_cpu_limit,
                    default_memory_limit=config.docker_default_memory_limit,
                    cleanup_containers=config.docker_cleanup_containers,
                )
                await docker_client.initialize()
                app_state['docker_client'] = docker_client
                logger.info('docker_client_initialized', base_url=config.docker_base_url)
            except ImportError:
                logger.warning('docker_client_init_failed', error='aiodocker não instalado')
            except Exception as e:
                logger.warning('docker_client_init_failed', error=str(e))

        # Inicializar K8s Jobs client se habilitado
        k8s_jobs_client = None
        if getattr(config, 'k8s_jobs_enabled', False):
            try:
                from .clients.k8s_jobs_client import KubernetesJobsClient
                k8s_jobs_client = KubernetesJobsClient(
                    kubeconfig_path=config.k8s_jobs_kubeconfig_path,
                    namespace=config.k8s_jobs_namespace,
                    timeout=config.k8s_jobs_timeout_seconds,
                    poll_interval=config.k8s_jobs_poll_interval_seconds,
                    cleanup_jobs=config.k8s_jobs_cleanup,
                    service_account=config.k8s_jobs_service_account,
                )
                await k8s_jobs_client.initialize()
                app_state['k8s_jobs_client'] = k8s_jobs_client
                logger.info('k8s_jobs_client_initialized', namespace=config.k8s_jobs_namespace)
            except ImportError:
                logger.warning('k8s_jobs_client_init_failed', error='kubernetes-asyncio não instalado')
            except Exception as e:
                logger.warning('k8s_jobs_client_init_failed', error=str(e))

        # Inicializar Lambda Runtime client se habilitado
        lambda_client = None
        if getattr(config, 'lambda_enabled', False):
            try:
                from .clients.lambda_runtime_client import LambdaRuntimeClient
                lambda_client = LambdaRuntimeClient(
                    region=config.lambda_region,
                    access_key=config.lambda_access_key,
                    secret_key=config.lambda_secret_key,
                    timeout=config.lambda_timeout_seconds,
                    function_name=config.lambda_function_name,
                )
                await lambda_client.initialize()
                app_state['lambda_client'] = lambda_client
                logger.info('lambda_client_initialized', region=config.lambda_region)
            except ImportError:
                logger.warning('lambda_client_init_failed', error='aioboto3 não instalado')
            except Exception as e:
                logger.warning('lambda_client_init_failed', error=str(e))

        # Inicializar Local Runtime client (sempre habilitado como fallback)
        local_client = None
        if getattr(config, 'local_runtime_enabled', True):
            try:
                from .clients.local_runtime_client import LocalRuntimeClient
                local_client = LocalRuntimeClient(
                    allowed_commands=config.local_runtime_allowed_commands,
                    timeout=config.local_runtime_timeout_seconds,
                    enable_sandbox=config.local_runtime_enable_sandbox,
                    working_dir=config.local_runtime_working_dir,
                )
                app_state['local_client'] = local_client
                logger.info('local_client_initialized', working_dir=config.local_runtime_working_dir)
            except Exception as e:
                logger.warning('local_client_init_failed', error=str(e))

        # Criar e configurar registry de executores com Vault client
        executor_registry = TaskExecutorRegistry(config, metrics=metrics)
        executor_registry.register_executor(BuildExecutor(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics))
        executor_registry.register_executor(DeployExecutor(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics, argocd_client=argocd_client, flux_client=flux_client))
        executor_registry.register_executor(TestExecutor(
            config,
            vault_client=vault_client,
            code_forge_client=code_forge_client,
            metrics=metrics,
            github_actions_client=github_actions_client,
            gitlab_ci_client=gitlab_ci_client,
            jenkins_client=jenkins_client
        ))
        executor_registry.register_executor(ValidateExecutor(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics, opa_client=opa_client))
        executor_registry.register_executor(ExecuteExecutor(
            config,
            vault_client=vault_client,
            code_forge_client=code_forge_client,
            metrics=metrics,
            docker_client=docker_client,
            k8s_jobs_client=k8s_jobs_client,
            lambda_client=lambda_client,
            local_client=local_client
        ))
        executor_registry.register_executor(CompensateExecutor(
            config,
            vault_client=vault_client,
            code_forge_client=code_forge_client,
            metrics=metrics,
            argocd_client=argocd_client,
            flux_client=flux_client,
            k8s_jobs_client=k8s_jobs_client
        ))
        executor_registry.validate_configuration()
        app_state['executor_registry'] = executor_registry

        # Criar execution engine
        execution_engine = ExecutionEngine(
            config,
            ticket_client,
            result_producer,
            dependency_coordinator,
            executor_registry,
            redis_client=redis_client,
            metrics=metrics
        )
        app_state['execution_engine'] = execution_engine

        # Criar Kafka consumer com Redis para DLQ retry tracking
        kafka_consumer = KafkaTicketConsumer(config, execution_engine, metrics=metrics)
        await kafka_consumer.initialize(redis_client=redis_client)
        kafka_consumer = instrument_kafka_consumer(kafka_consumer)
        app_state['kafka_consumer'] = kafka_consumer

        # Inicializar MongoDB client para persistência de DLQ (Comment 2)
        mongodb_client = None
        if getattr(config, 'mongodb_enabled', True):
            try:
                logger.info('Inicializando MongoDB Client para persistência de DLQ')
                mongodb_client = MongoDBClient(config)
                await mongodb_client.initialize()
                app_state['mongodb_client'] = mongodb_client
                logger.info('MongoDB Client inicializado com sucesso')
            except ImportError:
                logger.warning('MongoDB habilitado mas motor não instalado')
            except Exception as mongo_error:
                logger.warning(
                    'MongoDB Client init falhou, continuando sem persistência DLQ',
                    error=str(mongo_error)
                )
                mongodb_client = None

        # Inicializar DLQ Alert Manager para alertas SRE (Comment 2)
        dlq_alert_manager = None
        if getattr(config, 'dlq_alert_enabled', True):
            try:
                logger.info('Inicializando DLQ Alert Manager')
                dlq_alert_manager = DLQAlertManager(config, metrics=metrics)
                await dlq_alert_manager.initialize()
                app_state['dlq_alert_manager'] = dlq_alert_manager
                logger.info('DLQ Alert Manager inicializado com sucesso')
            except Exception as alert_error:
                logger.warning(
                    'DLQ Alert Manager init falhou, continuando sem alertas',
                    error=str(alert_error)
                )
                dlq_alert_manager = None

        # Inicializar DLQ consumer com MongoDB e AlertManager reais (Comment 2)
        if getattr(config, 'kafka_dlq_enabled', True):
            try:
                dlq_consumer = KafkaDLQConsumer(
                    config=config,
                    mongodb_client=mongodb_client,
                    alert_manager=dlq_alert_manager,
                    metrics=metrics
                )
                await dlq_consumer.initialize()
                app_state['dlq_consumer'] = dlq_consumer
                logger.info(
                    'dlq_consumer_initialized',
                    mongodb_enabled=mongodb_client is not None,
                    alerts_enabled=dlq_alert_manager is not None
                )
            except Exception as dlq_error:
                logger.warning(
                    'dlq_consumer_init_failed_continuing_without',
                    error=str(dlq_error)
                )

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

        # Iniciar DLQ consumer em background
        if 'dlq_consumer' in app_state:
            app_state['dlq_consumer_task'] = asyncio.create_task(app_state['dlq_consumer'].start())
            logger.info('dlq_consumer_started')

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

        if 'dlq_consumer_task' in app_state:
            app_state['dlq_consumer_task'].cancel()

        # Fechar Vault client
        if 'vault_client' in app_state and app_state['vault_client']:
            logger.info('Fechando Vault client')
            await app_state['vault_client'].close()
            logger.info('Vault client fechado')

        # Shutdown execution engine
        if 'execution_engine' in app_state:
            await app_state['execution_engine'].shutdown(timeout_seconds=30)

        # Fechar SPIFFE manager independente do Vault
        if 'spiffe_manager' in app_state and app_state['spiffe_manager']:
            await app_state['spiffe_manager'].close()

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

        if 'dlq_consumer' in app_state:
            await app_state['dlq_consumer'].stop()

        if 'result_producer' in app_state:
            await app_state['result_producer'].stop()

        if 'ticket_client' in app_state:
            await app_state['ticket_client'].close()

        if 'code_forge_client' in app_state and app_state['code_forge_client']:
            await app_state['code_forge_client'].close()

        if 'argocd_client' in app_state and app_state['argocd_client']:
            await app_state['argocd_client'].close()

        if 'flux_client' in app_state and app_state['flux_client']:
            await app_state['flux_client'].close()

        if 'github_actions_client' in app_state and app_state['github_actions_client']:
            await app_state['github_actions_client'].close()

        if 'gitlab_ci_client' in app_state and app_state['gitlab_ci_client']:
            await app_state['gitlab_ci_client'].close()

        if 'jenkins_client' in app_state and app_state['jenkins_client']:
            await app_state['jenkins_client'].close()

        if 'opa_client' in app_state and app_state['opa_client']:
            await app_state['opa_client'].close()

        # Fechar runtime clients
        if 'docker_client' in app_state and app_state['docker_client']:
            await app_state['docker_client'].close()

        if 'k8s_jobs_client' in app_state and app_state['k8s_jobs_client']:
            await app_state['k8s_jobs_client'].close()

        if 'lambda_client' in app_state and app_state['lambda_client']:
            await app_state['lambda_client'].close()

        if 'local_client' in app_state and app_state['local_client']:
            await app_state['local_client'].close()

        # Fechar Redis client
        if 'redis_client' in app_state and app_state['redis_client']:
            try:
                logger.info('Fechando Redis Client')
                await close_redis_client()
                logger.info('Redis Client fechado com sucesso')
            except Exception as redis_close_error:
                logger.warning('Erro ao fechar Redis Client', error=str(redis_close_error))

        # Fechar MongoDB client (Comment 2)
        if 'mongodb_client' in app_state and app_state['mongodb_client']:
            try:
                logger.info('Fechando MongoDB Client')
                await app_state['mongodb_client'].close()
                logger.info('MongoDB Client fechado com sucesso')
            except Exception as mongo_close_error:
                logger.warning('Erro ao fechar MongoDB Client', error=str(mongo_close_error))

        # Fechar DLQ Alert Manager (Comment 2)
        if 'dlq_alert_manager' in app_state and app_state['dlq_alert_manager']:
            try:
                logger.info('Fechando DLQ Alert Manager')
                await app_state['dlq_alert_manager'].close()
                logger.info('DLQ Alert Manager fechado com sucesso')
            except Exception as alert_close_error:
                logger.warning('Erro ao fechar DLQ Alert Manager', error=str(alert_close_error))

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
