from datetime import datetime, timezone

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from src.config.settings import get_settings
from src.metrics import get_metrics_text

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(
        status="healthy", timestamp=datetime.now(timezone.utc), version=settings.service_version
    )


@router.get("/health/liveness", status_code=status.HTTP_200_OK)
@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict:
    """Liveness probe"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}


@router.get("/health/readiness", status_code=status.HTTP_200_OK)
@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness() -> dict:
    """Readiness probe"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.

    Expõe métricas em formato Prometheus text format.
    """
    metrics_text = get_metrics_text()
    return Response(
        content=metrics_text,
        media_type="text/plain",
        headers={"Content-Type": "text/plain; version=0.0.4"},
    )
