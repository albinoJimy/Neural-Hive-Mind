"""Health check response models."""

from enum import Enum
from pydantic import BaseModel
from datetime import datetime


class HealthStatus(str, Enum):
    """Status de saúde do serviço."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class CheckResult(BaseModel):
    """Resultado de um check individual."""
    name: str
    status: HealthStatus
    message: str | None = None


class HealthResponse(BaseModel):
    """Response padrão do health check."""
    status: HealthStatus
    service: str
    timestamp: datetime
    checks: dict[str, HealthStatus]
