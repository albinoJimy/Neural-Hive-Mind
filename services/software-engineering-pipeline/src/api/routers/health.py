"""Router para health check e status do serviço."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from src.config.settings import settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response de health check."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str
    environment: str


class StatusResponse(BaseModel):
    """Response de status detalhado."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str
    environment: str
    components: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check básico do serviço.

    Retorna status do serviço, nome e versão.
    """
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """
    Status detalhado do serviço e componentes.

    Retorna status de cada componente integrado.
    """
    components = {
        "api": "healthy",
        "mongodb": "unknown",  # TODO: implementar check real
        "kafka": "unknown",  # TODO: implementar check real
        "github": "configured" if settings.github_token else "not_configured",
        "gitlab": "configured" if settings.gitlab_token else "not_configured",
        "argocd": "configured" if settings.argocd_token else "not_configured",
    }

    # Se algum componente crítico estiver down, status = degraded
    overall_status = "healthy"
    if components.get("mongodb") == "down" or components.get("kafka") == "down":
        overall_status = "degraded"

    return StatusResponse(
        status=overall_status,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        components=components,
    )


@router.get("/ping")
async def ping() -> dict[str, str]:
    """
    Endpoint simples para verificar se o serviço está respondendo.
    """
    return {"ping": "pong"}
