"""
Ponto de entrada principal do ML Inference API.
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from neural_hive_observability import init_observability

from .api import api_router
from .config import get_settings
from .observability import MLInferenceMetrics
from .services import get_predictor_service, get_batch_engine


# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
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
        "starting_ml_inference_api",
        version="1.0.0",
        environment=settings.environment,
    )

    # Inicializar métricas
    app.state.metrics = MLInferenceMetrics()
    logger.info("metrics_initialized", prometheus_port=settings.prometheus_port)

    # Inicializar predictor service
    try:
        predictor_service = await get_predictor_service(app.state.metrics)
        app.state.predictor_service = predictor_service
        logger.info(
            "predictor_service_initialized",
            model_version=predictor_service.model_info.get("version"),
        )
    except Exception as e:
        logger.error(
            "predictor_service_init_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        # Não é fatal - serviço pode operar sem modelo
        app.state.predictor_service = None

    # Inicializar batch engine
    try:
        app.state.batch_engine = get_batch_engine(
            predictor_service=app.state.predictor_service,
            metrics=app.state.metrics,
        )
        logger.info("batch_engine_initialized")
    except Exception as e:
        logger.warning(
            "batch_engine_init_failed_non_critical",
            error=str(e),
        )
        app.state.batch_engine = None

    # Configurar rate limiter
    if settings.enable_rate_limiting:
        app.state.limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[f"{settings.rate_limit_requests_per_minute}/minute"],
            storage_uri="memory://",
        )
        logger.info(
            "rate_limiter_initialized",
            requests_per_minute=settings.rate_limit_requests_per_minute,
        )
    else:
        app.state.limiter = None

    logger.info("ml_inference_api_started")

    yield

    # Shutdown
    logger.info("shutting_down_service")

    # Fechar batch engine
    if hasattr(app.state, "batch_engine") and app.state.batch_engine:
        try:
            app.state.batch_engine.close()
        except Exception as e:
            logger.warning("batch_engine_shutdown_failed", error=str(e))

    logger.info("service_shutdown_complete")


def create_app() -> FastAPI:
    """Cria e configura aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="ML Inference API",
        description="API de inferência ML para predição de aprovação de planos cognitivos",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware CORS - usa configuração segura por ambiente
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    # Rate limiting middleware
    if settings.enable_rate_limiting:
        from slowapi.middleware import SlowAPIMiddleware

        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[f"{settings.rate_limit_requests_per_minute}/minute"],
            storage_uri="memory://",
        )
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)
        app.state.limiter = limiter

    # Exception handler para rate limit
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """Handler customizado para rate limit exceeded."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "rate_limit_exceeded",
                "message": "Too many requests - please try again later",
                "detail": str(exc),
            },
        )

    # Registrar routers
    app.include_router(api_router)

    # Configurar tracing
    try:
        init_observability(
            service_name=settings.service_name,
            service_version=settings.service_version,
            neural_hive_component="ml-inference",
            neural_hive_layer="ml",
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
            prometheus_port=settings.prometheus_port,
        )

    logger.info("fastapi_application_created")

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
