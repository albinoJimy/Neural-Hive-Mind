"""
Feature Store Service - Main Entry Point

Serviço de armazenamento e computação de features para modelos ML.
Fornece API REST para gerenciamento de features com cache Redis.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import features, health
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import get_settings
from src.services.cache_service import RedisCacheService
from src.services.feature_store import FeatureStoreService

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Estado global para clientes
state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação"""
    settings = get_settings()

    logger.info(
        "Starting Feature Store Service",
        version=settings.service_version,
        environment=settings.environment,
    )

    try:
        # Inicializa MongoDB client
        logger.info("Inicializando MongoDB client...")
        mongodb_client = MongoDBClient(settings)
        await mongodb_client.initialize()
        state["mongodb"] = mongodb_client

        # Inicializa Redis cache
        logger.info("Inicializando Redis cache...")
        cache_service = RedisCacheService(settings)
        await cache_service.initialize()
        state["cache"] = cache_service

        # Inicializa Feature Store Service
        logger.info("Inicializando Feature Store Service...")
        feature_store = FeatureStoreService(
            settings=settings, mongodb_client=mongodb_client.client, cache_service=cache_service
        )
        await feature_store.create_indexes()
        state["feature_store"] = feature_store

        # Configura referências nos routers e state
        features.set_feature_store_service(feature_store)
        health.set_app_state(state)

        logger.info("Feature Store Service started successfully")

        yield  # Aplicação rodando

    finally:
        # Cleanup no shutdown
        logger.info("Shutting down Feature Store Service...")

        if "cache" in state:
            await state["cache"].close()

        if "mongodb" in state:
            await state["mongodb"].close()

        logger.info("Shutdown complete")


# Cria aplicação FastAPI
app = FastAPI(
    title="Feature Store Service",
    description="Serviço de Armazenamento e Computação de Features",
    version="1.0.0",
    lifespan=lifespan,
)

# Configura CORS - usa origens do settings por ambiente
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)

# Inclui routers
app.include_router(health.router)
app.include_router(features.router)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "src.main:app", host="0.0.0.0", port=8080, workers=1, log_level=settings.log_level.lower()
    )
