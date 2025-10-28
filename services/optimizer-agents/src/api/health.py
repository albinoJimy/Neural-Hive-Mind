from fastapi import APIRouter, status
from pydantic import BaseModel

from src.config.settings import get_settings

router = APIRouter(prefix="", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str
    ready: bool
    checks: dict


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check."""
    settings = get_settings()
    return HealthResponse(status="healthy", service=settings.service_name, version=settings.service_version)


@router.get("/health/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def readiness_check():
    """Readiness probe for Kubernetes."""
    settings = get_settings()

    # TODO: Check connections (MongoDB, Redis, Kafka, gRPC clients)
    checks = {
        "mongodb": "connected",
        "redis": "connected",
        "kafka": "connected",
        "grpc_clients": "connected",
    }

    all_ready = all(v == "connected" for v in checks.values())

    return ReadinessResponse(status="ready" if all_ready else "not_ready", ready=all_ready, checks=checks)


@router.get("/health/live")
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}
