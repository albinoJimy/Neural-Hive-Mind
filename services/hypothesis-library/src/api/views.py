"""Views básicas da API."""

from typing import Any

from fastapi import Response
from fastapi.responses import JSONResponse


async def root_handler() -> dict[str, Any]:
    """Handler raiz."""
    from src.config.settings import get_settings

    settings = get_settings()
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "api": "/api/v1",
            "docs": "/docs",
        },
    }


async def health_handler() -> JSONResponse:
    """Handler de health check."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": "hypothesis-library",
        }
    )


async def metrics_handler() -> Response:
    """Handler de métricas Prometheus."""
    # Implementação básica - pode ser expandida com prometheus_client
    return Response(
        content="# Metrics endpoint\n",
        media_type="text/plain",
    )
