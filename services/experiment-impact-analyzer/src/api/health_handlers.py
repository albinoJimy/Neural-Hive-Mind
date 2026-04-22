"""Health check and metrics handlers."""

from datetime import UTC, datetime

from fastapi import Response
from prometheus_client import REGISTRY, Counter, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from src.config.settings import get_settings

# Metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

impact_analysis_total = Counter(
    "impact_analysis_total", "Total impact analyses performed", ["direction", "magnitude"]
)

impact_analysis_duration_seconds = Histogram(
    "impact_analysis_duration_seconds", "Impact analysis duration", ["timeframe"]
)


async def root_handler() -> dict:
    """Root endpoint."""
    settings = get_settings()
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "operational",
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def health_handler() -> dict:
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def metrics_handler() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


async def readiness_handler() -> dict:
    """Readiness check endpoint."""
    from src.main import mongodb_client

    is_ready = mongodb_client is not None and mongodb_client._connected

    return {
        "ready": is_ready,
        "timestamp": datetime.now(UTC).isoformat(),
    }


__all__ = [
    "root_handler",
    "health_handler",
    "metrics_handler",
    "readiness_handler",
    "http_requests_total",
    "http_request_duration_seconds",
    "impact_analysis_total",
    "impact_analysis_duration_seconds",
]
