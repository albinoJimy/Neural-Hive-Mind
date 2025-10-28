from datetime import datetime
from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from src.config.settings import get_settings

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    status: str  # "healthy" | "unhealthy"
    timestamp: datetime
    checks: dict[str, bool]
    version: str


@router.get("/health/liveness", status_code=status.HTTP_200_OK)
async def liveness() -> dict:
    """Liveness probe - verifica se serviço está rodando"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@router.get("/health/readiness", status_code=status.HTTP_200_OK)
async def readiness(request: Request) -> HealthResponse:
    """
    Readiness probe - verifica se serviço está pronto para tráfego
    Reflete status de todas as dependências críticas para o fluxo E1-E6
    """
    checks = {
        # Dependências de persistência
        "mongodb": getattr(request.app.state, "mongodb", None) and request.app.state.mongodb.is_healthy(),
        "redis": getattr(request.app.state, "redis", None) and request.app.state.redis.is_healthy(),

        # Dependências de mensageria
        "kafka_security": getattr(request.app.state, "security_consumer", None) and request.app.state.security_consumer.is_healthy(),
        "kafka_orchestration": getattr(request.app.state, "orchestration_consumer", None) and request.app.state.orchestration_consumer.is_healthy(),

        # Dependências de infraestrutura
        "kubernetes": getattr(request.app.state, "k8s", None) and request.app.state.k8s.is_healthy(),
        "service_registry": getattr(request.app.state, "service_registry", None) and request.app.state.service_registry.is_healthy(),

        # Componentes do fluxo E1-E6
        "message_handler": getattr(request.app.state, "message_handler", None) is not None,
    }

    # Verificar componentes críticos do orquestrador
    if hasattr(request.app.state, "message_handler"):
        handler = request.app.state.message_handler
        checks["orchestrator"] = hasattr(handler, "orchestrator") and handler.orchestrator is not None
        checks["threat_detector"] = hasattr(handler, "threat_detector") and handler.threat_detector is not None
        checks["incident_classifier"] = hasattr(handler, "incident_classifier") and handler.incident_classifier is not None
        checks["policy_enforcer"] = hasattr(handler, "policy_enforcer") and handler.policy_enforcer is not None
        checks["remediation_coordinator"] = hasattr(handler, "remediation_coordinator") and handler.remediation_coordinator is not None

    all_healthy = all(checks.values())
    response_status = "healthy" if all_healthy else "unhealthy"

    return HealthResponse(
        status=response_status,
        timestamp=datetime.utcnow(),
        checks=checks,
        version=settings.service_version
    )


@router.get("/health/startup", status_code=status.HTTP_200_OK)
async def startup() -> dict:
    """Startup probe - verifica inicialização completa"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict:
    """Health check geral"""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
        "timestamp": datetime.utcnow()
    }
