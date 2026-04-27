"""Aplicação principal Test Generation."""

import asyncio
from contextlib import asynccontextmanager

import structlog
from api.routers.tests import router as tests_router
from config.settings import get_settings
from consumers.requirements_consumer import RequirementsConsumer
from database.mongodb_client import MongoDBClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from producers.tests_producer import TestsProducer

settings = get_settings()

# Configurar structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Kafka components (globais para lifespan)
_kafka_consumer: RequirementsConsumer | None = None
_kafka_producer: TestsProducer | None = None
_consumer_task: asyncio.Task | None = None

# MongoDB client (global para lifespan)
_mongodb_client: MongoDBClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    global _kafka_consumer, _kafka_producer, _consumer_task, _mongodb_client

    logger.info(
        "starting_service",
        service=settings.service_name,
        version=settings.service_version,
    )

    # Inicializar MongoDB
    try:
        _mongodb_client = MongoDBClient()
        await _mongodb_client.connect()
        logger.info("mongodb_ready")
    except Exception as e:
        logger.warning("mongodb_start_failed", error=str(e))
        _mongodb_client = None

    # Inicializar Kafka producer
    try:
        _kafka_producer = TestsProducer()
        await _kafka_producer.start()
        logger.info("kafka_producer_ready")
    except Exception as e:
        logger.warning("kafka_producer_start_failed", error=str(e))
        _kafka_producer = None

    # Inicializar Kafka consumer
    try:
        _kafka_consumer = RequirementsConsumer(
            test_generator=None,
            producer=_kafka_producer,
        )
        await _kafka_consumer.start()

        # Iniciar task de consumo em background
        _consumer_task = asyncio.create_task(_kafka_consumer.consume())
        logger.info("kafka_consumer_ready")
    except Exception as e:
        logger.warning("kafka_consumer_start_failed", error=str(e))
        _kafka_consumer = None
        _consumer_task = None

    yield

    # Shutdown
    logger.info("shutting_down_service")

    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass

    if _kafka_consumer:
        await _kafka_consumer.stop()

    if _kafka_producer:
        await _kafka_producer.stop()

    if _mongodb_client:
        await _mongodb_client.disconnect()

    logger.info("service_shutdown_complete")


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router
app.include_router(tests_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Endpoint raiz."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "description": "Automated test generation from requirements and user stories",
    }


@app.get("/health")
async def health():
    """Health check com status do Kafka e MongoDB."""
    health_status = {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
    }

    # Verificar MongoDB
    if _mongodb_client:
        mongo_health = await _mongodb_client.health_check()
        health_status["mongodb"] = mongo_health
    else:
        health_status["mongodb"] = {"mongodb_connected": False}

    # Verificar Kafka consumer
    if _kafka_consumer:
        consumer_health = await _kafka_consumer.health_check()
        health_status["kafka_consumer"] = consumer_health
    else:
        health_status["kafka_consumer"] = {"kafka_connected": False}

    # Verificar Kafka producer
    if _kafka_producer:
        producer_health = await _kafka_producer.health_check()
        health_status["kafka_producer"] = producer_health
    else:
        health_status["kafka_producer"] = {"kafka_connected": False}

    return health_status


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
