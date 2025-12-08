import asyncio
import signal
import sys
import uvicorn
import structlog

from .config import get_settings
from .observability import setup_logging, CodeForgeMetrics
from .api.http_server import create_app
from .clients.kafka_ticket_consumer import KafkaTicketConsumer
from .clients.kafka_result_producer import KafkaResultProducer
from .clients.service_registry_client import ServiceRegistryClient
from .clients.execution_ticket_client import ExecutionTicketClient
from .clients.git_client import GitClient
from .clients.sonarqube_client import SonarQubeClient
from .clients.snyk_client import SnykClient
from .clients.trivy_client import TrivyClient
from .clients.sigstore_client import SigstoreClient
from .clients.postgres_client import PostgresClient
from .clients.mongodb_client import MongoDBClient
from .clients.redis_client import RedisClient
from .clients.mcp_tool_catalog_client import MCPToolCatalogClient
from .clients.llm_client import LLMClient
from .clients.analyst_agents_client import AnalystAgentsClient
from .services.pipeline_engine import PipelineEngine
from .services.template_selector import TemplateSelector
from .services.code_composer import CodeComposer
from .services.validator import Validator
from .services.test_runner import TestRunner
from .services.packager import Packager
from .services.approval_gate import ApprovalGate
from .integration.generation_webhook import WebhookHandler
from neural_hive_integration import ExecutionTicketClient as IntegrationTicketClient

logger = None
shutdown_event = asyncio.Event()


async def main():
    """Entry point principal do Code Forge"""
    global logger

    # 1. Carregar configurações
    settings = get_settings()

    # 2. Inicializar logging
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    logger = structlog.get_logger()

    logger.info('code_forge_starting', version='1.0.0')

    # 3. Inicializar métricas
    metrics = CodeForgeMetrics()
    metrics.startup_total.inc()

    # 4. Inicializar clientes
    logger.info('initializing_clients')

    kafka_consumer = KafkaTicketConsumer(
        settings.KAFKA_BOOTSTRAP_SERVERS,
        settings.KAFKA_TICKETS_TOPIC,
        settings.KAFKA_CONSUMER_GROUP_ID,
        settings.KAFKA_AUTO_OFFSET_RESET,
        settings.KAFKA_ENABLE_AUTO_COMMIT
    )

    kafka_producer = KafkaResultProducer(
        settings.KAFKA_BOOTSTRAP_SERVERS,
        settings.KAFKA_RESULTS_TOPIC
    )

    service_registry = ServiceRegistryClient(
        settings.SERVICE_REGISTRY_HOST,
        settings.SERVICE_REGISTRY_PORT
    )

    ticket_client = ExecutionTicketClient(settings.EXECUTION_TICKET_SERVICE_URL)

    git_client = GitClient(
        settings.TEMPLATES_GIT_REPO,
        settings.TEMPLATES_GIT_BRANCH,
        settings.TEMPLATES_LOCAL_PATH
    )

    sonarqube_client = SonarQubeClient(
        settings.SONARQUBE_URL,
        settings.SONARQUBE_TOKEN,
        settings.SONARQUBE_ENABLED
    )

    snyk_client = SnykClient(settings.SNYK_TOKEN, settings.SNYK_ENABLED)

    trivy_client = TrivyClient(settings.TRIVY_ENABLED, settings.TRIVY_SEVERITY)

    sigstore_client = SigstoreClient(
        settings.SIGSTORE_FULCIO_URL,
        settings.SIGSTORE_REKOR_URL,
        settings.SIGSTORE_ENABLED
    )

    postgres_client = PostgresClient(settings.POSTGRES_URL)
    mongodb_client = MongoDBClient(settings.MONGODB_URL, 'code_forge')
    redis_client = RedisClient(settings.REDIS_URL)

    # Novos clientes para integração MCP
    mcp_client = None
    llm_client = None
    analyst_client = None

    if settings.MCP_TOOL_CATALOG_URL:
        mcp_client = MCPToolCatalogClient(
            settings.MCP_TOOL_CATALOG_HOST,
            settings.MCP_TOOL_CATALOG_PORT
        )
        await mcp_client.start()
        logger.info('mcp_client_initialized', url=settings.MCP_TOOL_CATALOG_URL)

    if settings.LLM_ENABLED and settings.LLM_PROVIDER:
        from .clients.llm_client import LLMProvider
        llm_client = LLMClient(
            provider=LLMProvider(settings.LLM_PROVIDER),
            api_key=settings.LLM_API_KEY if settings.LLM_API_KEY else None,
            model_name=settings.LLM_MODEL,
            endpoint_url=settings.LLM_BASE_URL if settings.LLM_BASE_URL else None
        )
        await llm_client.start()
        logger.info('llm_client_initialized', provider=settings.LLM_PROVIDER, model=settings.LLM_MODEL)

    if settings.ANALYST_AGENTS_URL:
        analyst_client = AnalystAgentsClient(
            settings.ANALYST_AGENTS_HOST,
            settings.ANALYST_AGENTS_PORT
        )
        await analyst_client.start()
        logger.info('analyst_client_initialized', url=settings.ANALYST_AGENTS_URL)

    # Iniciar clientes
    await kafka_consumer.start()
    await kafka_producer.start()
    await ticket_client.start()
    await postgres_client.start()
    await mongodb_client.start()
    await redis_client.start()

    # 5. Inicializar pipeline engine e subpipelines
    logger.info('initializing_pipeline_engine')

    template_selector = TemplateSelector(git_client, redis_client, mcp_client, metrics)
    code_composer = CodeComposer(mongodb_client, llm_client, analyst_client, mcp_client)
    validator = Validator(sonarqube_client, snyk_client, trivy_client, mcp_client, metrics)
    test_runner = TestRunner(settings.MIN_TEST_COVERAGE)
    packager = Packager(sigstore_client)
    approval_gate = ApprovalGate(
        git_client,
        settings.AUTO_APPROVAL_THRESHOLD,
        settings.MIN_QUALITY_SCORE
    )

    pipeline_engine = PipelineEngine(
        template_selector,
        code_composer,
        validator,
        test_runner,
        packager,
        approval_gate,
        kafka_producer,
        ticket_client,
        postgres_client,
        mongodb_client,
        settings.MAX_CONCURRENT_PIPELINES,
        settings.PIPELINE_TIMEOUT_SECONDS,
        settings.AUTO_APPROVAL_THRESHOLD,
        settings.MIN_QUALITY_SCORE
    )

    # 5.5. Inicializar webhook handler
    logger.info('initializing_webhook_handler')
    webhook_handler_instance = WebhookHandler()
    await webhook_handler_instance.initialize()
    # Set global instance
    import src.integration.generation_webhook as webhook_module
    webhook_module.webhook_handler = webhook_handler_instance

    # 6. Registrar no Service Registry
    logger.info('registering_service')
    await service_registry.register(
        settings.SERVICE_NAME,
        ['code_generation', 'iac_generation', 'test_generation', 'validation', 'packaging', 'signing'],
        {'version': '1.0.0', 'layer': 'execution'}
    )
    metrics.registered_total.labels(status='success').inc()

    # 7. Iniciar consumer Kafka em background
    async def consume_tickets():
        """Task de consumo de tickets"""
        try:
            async for ticket in kafka_consumer.consume():
                try:
                    metrics.pipelines_started_total.inc()
                    metrics.active_pipelines.inc()

                    result = await pipeline_engine.execute_pipeline(ticket)

                    metrics.pipelines_completed_total.labels(status=result.status.value).inc()
                    metrics.pipelines_duration_seconds.observe(result.total_duration_ms / 1000.0)
                    metrics.active_pipelines.dec()

                    # Commit offset
                    await kafka_consumer.commit()

                except Exception as e:
                    logger.error('pipeline_execution_error', error=str(e))
                    metrics.pipelines_failed_total.labels(error_type=type(e).__name__).inc()
                    metrics.active_pipelines.dec()

        except Exception as e:
            logger.error('kafka_consume_loop_error', error=str(e))

    asyncio.create_task(consume_tickets())

    # 8. Iniciar heartbeat loop
    async def heartbeat_loop():
        """Task de heartbeat periódico"""
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)
                await service_registry.send_heartbeat({
                    'active_pipelines': pipeline_engine.get_active_pipelines_count()
                })
                metrics.heartbeat_total.labels(status='success').inc()
            except Exception as e:
                logger.error('heartbeat_error', error=str(e))
                metrics.heartbeat_total.labels(status='failure').inc()

    asyncio.create_task(heartbeat_loop())

    # 9. Iniciar HTTP server (FastAPI)
    logger.info('starting_http_server', port=settings.HTTP_PORT)
    app = create_app()

    config = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=settings.HTTP_PORT,
        log_config=None
    )
    server = uvicorn.Server(config)

    logger.info('code_forge_started')

    try:
        # 10. Aguardar shutdown
        await server.serve()
    finally:
        # 11. Cleanup: encerrar clientes HTTP
        logger.info('shutting_down_clients')

        if mcp_client:
            try:
                await mcp_client.stop()
                logger.info('mcp_client_stopped')
            except Exception as e:
                logger.error('mcp_client_shutdown_error', error=str(e))

        if llm_client:
            try:
                await llm_client.stop()
                logger.info('llm_client_stopped')
            except Exception as e:
                logger.error('llm_client_shutdown_error', error=str(e))

        if analyst_client:
            try:
                await analyst_client.stop()
                logger.info('analyst_client_stopped')
            except Exception as e:
                logger.error('analyst_client_shutdown_error', error=str(e))

        logger.info('all_clients_stopped')


def signal_handler(sig, frame):
    """Handler de sinais para graceful shutdown"""
    logger.info('shutdown_signal_received', signal=sig)
    shutdown_event.set()
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    asyncio.run(main())
