"""FastAPI HTTP server for MCP Tool Catalog."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.config import get_settings


def create_app(lifespan: Optional[asynccontextmanager] = None) -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="MCP Tool Catalog Service",
        description="Intelligent tool selection via genetic algorithms for Neural Hive-Mind",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OpenTelemetry instrumentation
    FastAPIInstrumentor.instrument_app(app)

    # Health endpoints
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready():
        return {"status": "ready"}

    # Include routers
    from src.api.tools import router as tools_router
    from src.api.selections import router as selections_router
    app.include_router(tools_router)
    app.include_router(selections_router)

    return app
