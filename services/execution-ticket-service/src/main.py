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
    logger.info('Starting Execution Ticket Service', version='1.0.0')

    # Conectar PostgreSQL
    try:
        postgres_client = await get_postgres_client()
        logger.info('PostgreSQL connected')
    except Exception as e:
        logger.error(f'Failed to connect to PostgreSQL: {e}')
        raise

    # Conectar MongoDB
    try:
        mongodb_client = await get_mongodb_client()
        logger.info('MongoDB connected')
    except Exception as e:
        logger.error(f'Failed to connect to MongoDB: {e}')
        raise

    # Inicializar métricas
    app.state.metrics = TicketServiceMetrics()
    logger.info('Metrics initialized')

    # Iniciar Kafka Consumer
    app.state.ticket_consumer = None
    if settings.kafka_bootstrap_servers:
        try:
            from .consumers import start_ticket_consumer
            app.state.ticket_consumer = await start_ticket_consumer(app.state.metrics)

            # Iniciar consumo em background
            app.state.consumer_task = asyncio.create_task(app.state.ticket_consumer.consume())
            logger.info('Kafka consumer started')
        except Exception as e:
            logger.error(f'Failed to start Kafka consumer: {e}', exc_info=True)

    # Iniciar Webhook Manager
    app.state.webhook_manager = None
    if settings.enable_webhooks:
        try:
            from .webhooks import start_webhook_manager
            app.state.webhook_manager = await start_webhook_manager(app.state.metrics)
            logger.info('Webhook manager started')
        except Exception as e:
            logger.error(f'Failed to start webhook manager: {e}', exc_info=True)

    # Iniciar gRPC Server
    app.state.grpc_server = None
    try:
        from .grpc_service import start_grpc_server
        app.state.grpc_server = await start_grpc_server(settings)
        if app.state.grpc_server:
            logger.info('gRPC server started')
    except Exception as e:
        logger.warning(f'gRPC server not started: {e}')

    logger.info('Service startup complete')

    yield

    # Shutdown
    logger.info('Shutting down service')

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
    await postgres_client.disconnect()
    await mongodb_client.disconnect()

    logger.info('Service shutdown complete')


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
