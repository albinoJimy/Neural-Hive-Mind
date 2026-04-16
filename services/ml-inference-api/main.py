"""ML Inference API - API de Inferência de Modelos ML."""

import asyncio
import signal

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.inference_handlers import (
    batch_predict_handler,
    cache_clear_handler,
    cache_stats_handler,
    models_list_handler,
    predict_handler,
)
from src.consumers import InferenceRequestConsumer
from src.producers import InferenceResultProducer
from src.services import InferenceService

logger = structlog.get_logger(__name__)

# Global instances
inference_service: InferenceService | None = None
kafka_consumer: InferenceRequestConsumer | None = None
kafka_producer: InferenceResultProducer | None = None
consumer_task: asyncio.Task | None = None

shutdown_event = asyncio.Event()


def create_app(inference_service: InferenceService | None = None) -> FastAPI:
    """Cria aplicação FastAPI."""
    app = FastAPI(
        title="ML Inference API",
        description="API de Inferência de Modelos ML",
        version="0.2.0",
    )

    # Injeta serviço de inferência no estado da app
    app.state.inference_service = inference_service

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "ml-inference-api"}

    @app.get("/")
    async def root():
        return {"message": "ML Inference API", "version": "0.2.0"}

    # Endpoints de inferência
    @app.post("/api/v1/predict")
    async def predict(request: Request):
        return await predict_handler(request)

    @app.post("/api/v1/predict/batch")
    async def batch_predict(request: Request):
        return await batch_predict_handler(request)

    @app.get("/api/v1/models")
    async def list_models(request: Request):
        return await models_list_handler(request)

    # Endpoints de cache
    @app.get("/api/v1/cache/stats")
    async def cache_stats(request: Request):
        return await cache_stats_handler(request)

    @app.post("/api/v1/cache/clear")
    async def cache_clear(request: Request):
        return await cache_clear_handler(request)

    return app


async def main():
    """Ponto de entrada principal."""
    global inference_service, kafka_consumer, kafka_producer, consumer_task

    # Inicializar serviço de inferência
    inference_service = InferenceService(cache_ttl_seconds=3600)

    # Conectar ao Redis se disponível
    redis_url = "redis://localhost:6379/0"
    try:
        await inference_service.connect_redis(redis_url)
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e), message="Using memory cache only")

    # Criar app com injeção de dependência
    app = create_app(inference_service)

    # Inicializar producer Kafka
    kafka_producer = InferenceResultProducer()
    await kafka_producer.start()

    # Inicializar consumer Kafka
    kafka_consumer = InferenceRequestConsumer(
        inference_service=inference_service, producer=kafka_producer
    )

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("ml_inference_api_starting")

    # Iniciar consumer em background
    consumer_task = asyncio.create_task(kafka_consumer.start())

    # Configurar Uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8020)
    server = uvicorn.Server(config)

    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        # Graceful shutdown
        logger.info("shutting_down")
        if kafka_consumer:
            await kafka_consumer.stop()
        if kafka_producer:
            await kafka_producer.stop()
        if consumer_task and not consumer_task.done():
            consumer_task.cancel()
        # Desconectar Redis
        await inference_service.disconnect_redis()
        logger.info("ml_inference_api_stopped")


app = create_app()

if __name__ == "__main__":
    asyncio.run(main())
