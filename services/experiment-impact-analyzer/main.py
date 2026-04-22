"""Experiment Impact Analyzer - Análise de Impacto de Experimentos."""

import asyncio
import signal

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import api_router
from src.api.health_handlers import (
    health_handler,
    metrics_handler,
    readiness_handler,
    root_handler,
)
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import get_settings
from src.consumers import ExperimentCompletedConsumer
from src.producers import ImpactAnalyzedProducer
from src.services.impact_analyzer import ImpactAnalyzer

from neural_hive_observability import init_observability

logger = structlog.get_logger()

# Global instances
mongodb_client: MongoDBClient | None = None
impact_analyzer: ImpactAnalyzer | None = None
kafka_consumer: ExperimentCompletedConsumer | None = None
kafka_producer: ImpactAnalyzedProducer | None = None
consumer_task: asyncio.Task | None = None

app: FastAPI | None = None

# Shutdown event
shutdown_event = asyncio.Event()


def create_app() -> FastAPI:
    """Cria e configura aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="Experiment Impact Analyzer",
        description="Análise de Impacto de Experimentos de Curto e Longo Prazo",
        version=settings.service_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rotas
    app.include_router(api_router, prefix=settings.api_prefix)
    app.get("/")(root_handler)
    app.get("/health")(health_handler)
    app.get("/ready")(readiness_handler)
    app.get("/metrics")(metrics_handler)

    # Eventos de lifecycle
    @app.on_event("startup")
    async def startup():
        """Tarefas de inicialização."""
        global mongodb_client, impact_analyzer, kafka_consumer, kafka_producer, consumer_task

        settings = get_settings()

        logger.info(
            "experiment_impact_analyzer_starting",
            service=settings.service_name,
            version=settings.service_version,
        )

        # Inicializar observabilidade
        init_observability(
            service_name="experiment-impact-analyzer",
            service_version=settings.service_version,
            neural_hive_component="experiment-impact-analyzer",
            neural_hive_layer="analise",
            neural_hive_domain="continuous-improvement",
            otel_endpoint=settings.otel_endpoint,
        )
        logger.info("observability_initialized")

        # Conectar ao MongoDB
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.connect()

        # Inicializar ImpactAnalyzer
        impact_analyzer = ImpactAnalyzer(
            settings=settings,
            mongodb_client=mongodb_client,
        )

        # Inicializar Kafka Consumer e Producer (se habilitado)
        kafka_enabled = getattr(settings, "kafka_enabled", True)
        if kafka_enabled:
            try:
                # Inicializar producer
                kafka_producer = ImpactAnalyzedProducer()
                await kafka_producer.start()

                # Inicializar consumer com producer injetado
                kafka_consumer = ExperimentCompletedConsumer(producer=kafka_producer)
                kafka_consumer.set_impact_analyzer(impact_analyzer)
                consumer_task = asyncio.create_task(kafka_consumer.start())
                logger.info("kafka_consumer_initialized")
            except Exception as e:
                logger.warning("kafka_consumer_failed_to_initialize", error=str(e))

        logger.info("experiment_impact_analyzer_started")

    @app.on_event("shutdown")
    async def shutdown():
        """Tarefas de desligamento."""
        global mongodb_client, kafka_consumer, kafka_producer, consumer_task

        logger.info("experiment_impact_analyzer_shutting_down")

        # Parar Kafka Consumer e Producer
        if kafka_consumer:
            try:
                await kafka_consumer.stop()
            except Exception as e:
                logger.warning("kafka_consumer_failed_to_stop", error=str(e))

        if kafka_producer:
            try:
                await kafka_producer.stop()
            except Exception as e:
                logger.warning("kafka_producer_failed_to_stop", error=str(e))

        # Cancelar task do consumidor
        if consumer_task and not consumer_task.done():
            consumer_task.cancel()

        # Desconectar MongoDB
        if mongodb_client:
            await mongodb_client.disconnect()

        logger.info("experiment_impact_analyzer_stopped")

    return app


async def main():
    """Ponto de entrada principal."""
    global app

    settings = get_settings()
    app = create_app()

    config = uvicorn.Config(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )

    server = uvicorn.Server(config)

    # Setup signal handlers
    def signal_handler(sig: int, frame):
        logger.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()
        server.should_exit = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
