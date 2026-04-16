"""Aplicação principal Test Generation."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from src.config.settings import get_settings
from src.api.routers.tests import router as tests_router

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    logger.info(
        "starting_service",
        service=settings.service_name,
        version=settings.service_version,
    )
    yield
    logger.info("shutting_down_service")


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
    """Health check simplificado."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
