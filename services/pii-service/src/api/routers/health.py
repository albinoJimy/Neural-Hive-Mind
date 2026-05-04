"""Router de health check.

Implementa INV-10: All services respond to GET /health with
{status, version} JSON format.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.config.settings import get_settings

health_router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    """Resposta do health check - formato conforme INV-10."""

    status: str = Field(..., description="Status do serviço: 'healthy' ou 'unhealthy'")
    version: str = Field(..., description="Versão do serviço")


class DetailedHealthResponse(HealthResponse):
    """Resposta detalhada do health check."""

    service: str = Field(default="pii-service")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    environment: str = Field(default_factory=lambda: settings.ENVIRONMENT)
    uptime_seconds: float | None = Field(default=None)


class ReadinessResponse(BaseModel):
    """Resposta do readiness check para Kubernetes."""

    ready: bool


class LivenessResponse(BaseModel):
    """Resposta do liveness check para Kubernetes."""

    alive: bool


@health_router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check básico.

    Implementa INV-10: retorna {status, version} JSON.
    """
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
    )


@health_router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check() -> DetailedHealthResponse:
    """Health check detalhado com informações adicionais."""
    import time

    # Calcular uptime se disponível
    uptime = None
    if hasattr(health_check, "_start_time"):
        uptime = time.time() - health_check._start_time

    return DetailedHealthResponse(
        status="healthy",
        version=settings.VERSION,
        uptime_seconds=uptime,
    )


@health_router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness check para Kubernetes.

    Retorna 200 quando o serviço está pronto para receber tráfego.
    """
    # TODO: Adicionar verificações de dependências (MongoDB, etc.)
    return ReadinessResponse(ready=True)


@health_router.get("/health/live", response_model=LivenessResponse)
async def liveness_check() -> LivenessResponse:
    """
    Liveness check para Kubernetes.

    Retorna 200 quando o serviço está vivo (não travado).
    """
    return LivenessResponse(alive=True)


# Guardar tempo de início para cálculo de uptime
health_check._start_time = None


@health_router.on_event("startup")
async def store_start_time():
    """Guarda tempo de início do serviço."""
    import time

    health_check._start_time = time.time()
