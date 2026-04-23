"""
Deploy Service - Neural Hive Mind.

Serviço para deployments em Kubernetes.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers.deployments import router as deployments_router
from src.config.settings import settings
from src.models.deployment import DeploymentResponse
from neural_hive_observability import (
    AsyncLoggingMiddleware,
    init_logging,
    init_tracing,
)

# Storage em memória para deployments
_deployments: dict[str, DeploymentResponse] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    # Startup
    init_logging(service_name="deploy-service")
    if settings.enable_tracing:
        init_tracing(
            service_name="deploy-service",
            endpoint=settings.otel_endpoint,
        )
    yield
    # Shutdown
    pass


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

# Logging middleware
app.add_middleware(AsyncLoggingMiddleware)

# Routers
app.include_router(deployments_router, prefix=settings.api_prefix)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "deploy-service"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "deploy-service",
        "version": settings.api_version,
        "description": "Kubernetes deployment service for Neural Hive Mind",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
