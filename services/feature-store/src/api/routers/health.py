"""
Health Check Endpoint

Endpoint para verificar saúde do serviço e dependências.
"""

from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter
from src.models.feature import HealthResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/health", tags=["health"])

# Estado global
_app_state = {}


def set_app_state(state: dict):
    """Define estado global da aplicação"""
    global _app_state
    _app_state = state


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Health check do Feature Store

    Verifica conectividade com MongoDB e Redis
    """
    state = _app_state

    # Verifica MongoDB
    mongo_healthy: Literal["healthy", "unhealthy", "unknown"] = "unknown"
    if "mongodb" in state and state["mongodb"]:
        try:
            await state["mongodb"].client.admin.command("ping")
            mongo_healthy = "healthy"
        except Exception as e:
            logger.warning("MongoDB health check falhou", error=str(e))
            mongo_healthy = "unhealthy"
    else:
        mongo_healthy = "unhealthy"

    # Verifica Redis
    redis_healthy: Literal["healthy", "unhealthy", "unknown"] = "unknown"
    if "cache" in state and state["cache"]:
        if state["cache"].is_available():
            redis_healthy = "healthy"
        else:
            redis_healthy = "unhealthy"
    else:
        redis_healthy = "unhealthy"

    # Determina status geral
    if mongo_healthy == "healthy":
        overall_status: Literal["healthy", "unhealthy", "degraded"] = "healthy"
        if redis_healthy == "unhealthy":
            overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        service="feature-store",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
        dependencies={"mongodb": mongo_healthy, "redis": redis_healthy},
    )


@router.get("/ready")
async def readiness_check():
    """
    Readiness check - serviço está pronto para receber requests?
    """
    state = _app_state
    feature_store = state.get("feature_store")

    if feature_store is None:
        raise RuntimeError("Feature Store não inicializado")

    return {"ready": True}


@router.get("/live")
async def liveness_check():
    """
    Liveness check - serviço está rodando?
    """
    return {"alive": True}
