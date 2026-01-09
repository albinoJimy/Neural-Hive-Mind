"""
Ponto de entrada principal do Execution Ticket Service.
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neural_hive_observability import init_observability

from .config import get_settings
from .database import get_postgres_client, get_mongodb_client
from .api import health_router, tickets_router
from .observability import TicketServiceMetrics

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    settings = get_settings()
    logger.info(
        'starting_execution_ticket_service',
        version='1.0.0',
        environment=settings.environment
    )

    # Lista para rastrear falhas em dependências críticas
    critical_failures = []

    # Conectar PostgreSQL (CRÍTICO - serviço não funciona sem ele)
    postgres_client = None
    try:
        postgres_client = await get_postgres_client()
        await postgres_client.start(
            max_retries=settings.max_connection_retries,
            initial_delay=settings.initial_retry_delay_seconds
        )
        logger.info('postgresql_connected')
    except Exception as e:
        logger.error('postgresql_connection_failed_critical', error=str(e))
        critical_failures.append('postgresql')

    # Conectar MongoDB (CRÍTICO - audit trail é essencial)
    mongodb_client = None
    try:
        mongodb_client = await get_mongodb_client()
        await mongodb_client.start(
            max_retries=settings.max_connection_retries,
            initial_delay=settings.initial_retry_delay_seconds
        )
        logger.info('mongodb_connected')
    except Exception as e:
        logger.error('mongodb_connection_failed_critical', error=str(e))
        critical_failures.append('mongodb')

    # Se dependências críticas falharam, não podemos continuar
    if critical_failures:
        raise RuntimeError(f"Dependências críticas falharam: {critical_failures}")

    # Inicializar métricas
    app.state.metrics = TicketServiceMetrics()
    logger.info('metrics_initialized')

    # Initialize state for non-critical components
    app.state.ticket_consumer = None
    app.state.webhook_manager = None
    app.state.grpc_server = None
    app.state.background_init_tasks = []

    # Helper functions to start non-critical components in background
    async def start_kafka_consumer_background():
        """Start Kafka consumer in background (non-blocking)."""
        if not settings.kafka_bootstrap_servers:
            return
        try:
            from .consumers import start_ticket_consumer
            # Passa getter para webhook_manager (permite lazy loading)
            webhook_manager_getter = lambda: app.state.webhook_manager
            app.state.ticket_consumer = await start_ticket_consumer(
                app.state.metrics,
                webhook_manager_getter=webhook_manager_getter
            )
            app.state.consumer_task = asyncio.create_task(app.state.ticket_consumer.consume())
            logger.info('kafka_consumer_started')
        except Exception as e:
            logger.warning('kafka_consumer_failed_non_critical', error=str(e))

    async def start_webhook_manager_background():
        """Start webhook manager in background (non-blocking)."""
        if not settings.enable_webhooks:
            return
        try:
            from .webhooks import start_webhook_manager
            app.state.webhook_manager = await start_webhook_manager(app.state.metrics)
            logger.info('webhook_manager_started')
        except Exception as e:
            logger.warning('webhook_manager_failed_non_critical', error=str(e))

    async def start_grpc_server_background():
        """Start gRPC server in background (non-blocking)."""
        try:
            from .grpc_service import start_grpc_server
            app.state.grpc_server = await start_grpc_server(settings)
            if app.state.grpc_server:
                logger.info('grpc_server_started')
        except Exception as e:
            logger.warning('grpc_server_failed_non_critical', error=str(e))

    # Start non-critical components as background tasks (non-blocking)
    # This allows startup to complete without waiting for Kafka, webhooks, or gRPC
    app.state.background_init_tasks = [
        asyncio.create_task(start_kafka_consumer_background()),
        asyncio.create_task(start_webhook_manager_background()),
        asyncio.create_task(start_grpc_server_background()),
    ]

    logger.info(
        'execution_ticket_service_started',
        critical_components=['postgresql', 'mongodb'],
        optional_components_starting=['kafka', 'webhooks', 'grpc']
    )

    yield

    # Shutdown
    logger.info('shutting_down_service')

    # Cancel any pending background init tasks
    for task in app.state.background_init_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Parar Kafka Consumer
    if app.state.ticket_consumer:
        await app.state.ticket_consumer.stop()
        if hasattr(app.state, 'consumer_task'):
            app.state.consumer_task.cancel()
            try:
                await app.state.consumer_task
            except asyncio.CancelledError:
                pass

    # Parar Webhook Manager
    if app.state.webhook_manager:
        await app.state.webhook_manager.stop()

    # Parar gRPC Server
    if app.state.grpc_server:
        from .grpc_service import stop_grpc_server
        await stop_grpc_server(app.state.grpc_server)

    # Desconectar databases
    if postgres_client:
        await postgres_client.disconnect()
    if mongodb_client:
        await mongodb_client.disconnect()

    logger.info('service_shutdown_complete')


def create_app() -> FastAPI:
    """Cria e configura aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title='Execution Ticket Service',
        description='Serviço de gerenciamento de ciclo de vida de tickets de execução',
        version='1.0.0',
        lifespan=lifespan
    )

    # Middleware CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],  # Configurar adequadamente em produção
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    # Registrar routers
    app.include_router(health_router, tags=['Health'])
    app.include_router(tickets_router, tags=['Tickets'])

    # Configurar tracing
    try:
        init_observability(
            service_name=settings.service_name,
            service_version=settings.service_version,
            neural_hive_component="execution-ticket",
            neural_hive_layer="orchestration",
            environment=settings.environment,
            otel_endpoint=settings.otel_exporter_endpoint,
            prometheus_port=settings.prometheus_port,
            log_level=settings.log_level,
        )
    except Exception as e:
        logger.warning(
            "observability_init_failed",
            error=str(e),
            otel_endpoint=settings.otel_exporter_endpoint,
            prometheus_port=settings.prometheus_port
        )

    logger.info('FastAPI application created')

    return app


app = create_app()


if __name__ == '__main__':
    settings = get_settings()

    uvicorn.run(
        'src.main:app',
        host='0.0.0.0',
        port=8000,
        reload=settings.environment == 'development',
        log_level=settings.log_level.lower()
    )
