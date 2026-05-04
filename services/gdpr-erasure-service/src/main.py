"""
GDPR Erasure Service - Main Entry Point

Servico para gerenciar solicitacoes de exclusao de dados (GDPR Artigo 17).
"""

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.gdpr import router as gdpr_router, set_erasure_service
from src.api.routers.health import router as health_router, set_app_state
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.config.settings import get_settings
from src.consumers.erasure_report_consumer import ErasureReportConsumer
from src.observability.logging import configure_logging_with_pii_masking
from src.producers.erasure_command_producer import ErasureCommandProducer
from src.services.erasure_service import ErasureService

# Configure structured logging
configure_logging_with_pii_masking()

logger = structlog.get_logger()

settings = get_settings()
state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida"""
    logger.info(
        "Starting GDPR Erasure Service",
        version=settings.service_version,
        environment=settings.environment,
    )

    try:
        # Inicializa clientes
        logger.info("Inicializando clientes...")
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.initialize()
        state["mongodb"] = mongodb_client

        redis_client = RedisClient(settings)
        await redis_client.initialize()
        state["redis"] = redis_client

        # Inicializa Kafka producer
        logger.info("Inicializando Kafka producer...")
        command_producer = ErasureCommandProducer(settings)
        await command_producer.initialize()
        state["producer"] = command_producer

        # Inicializa servico de exclusao
        erasure_service = ErasureService(
            settings=settings,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            kafka_producer=command_producer,
        )
        state["erasure_service"] = erasure_service
        set_erasure_service(erasure_service)
        set_app_state(state)

        # Inicializa Kafka consumer
        logger.info("Inicializando Kafka consumer...")
        report_consumer = ErasureReportConsumer(settings)
        await report_consumer.initialize()
        report_consumer.set_erasure_service(erasure_service)
        state["consumer"] = report_consumer

        # Inicia consumer em background
        async def consume_with_error_handling():
            try:
                await report_consumer.start_consuming()
            except Exception as e:
                logger.error("Consumer task falhou", error=str(e))
                if "consumer" in state:
                    state["consumer"].running = False
                state["consumer_error"] = str(e)

        consumer_task = asyncio.create_task(consume_with_error_handling())
        state["consumer_task"] = consumer_task

        logger.info("GDPR Erasure Service started successfully")

        yield

    finally:
        logger.info("Shutting down GDPR Erasure Service...")

        if "consumer" in state:
            await state["consumer"].close()

        if "producer" in state:
            await state["producer"].close()

        if "mongodb" in state:
            await state["mongodb"].close()

        if "redis" in state:
            await state["redis"].close()

        logger.info("Shutdown complete")


# Criar aplicacao FastAPI
app = FastAPI(
    title="GDPR Erasure Service",
    description="Servico de Gerenciamento de Direito ao Apagamento (GDPR Artigo 17)",
    version="1.0.0",
    lifespan=lifespan,
)

# Configura CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)

# Inclui routers
app.include_router(health_router)
app.include_router(gdpr_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=1,
        log_level=settings.log_level.lower(),
    )
