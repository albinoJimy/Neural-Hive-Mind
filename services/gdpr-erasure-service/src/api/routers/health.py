"""
Health Check Endpoints
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/health", tags=["health"])

_app_state = None


def set_app_state(state):
    """Define referencia para o app state"""
    global _app_state
    _app_state = state


@router.get("/")
async def health_check():
    """Health check basico"""
    return {
        "status": "healthy",
        "service": "gdpr-erasure-service",
        "version": "1.0.0",
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check - verifica dependencias"""
    ready = True
    checks = {}

    if _app_state:
        # MongoDB
        if "mongodb" in _app_state:
            try:
                await _app_state["mongodb"].client.admin.command("ping")
                checks["mongodb"] = "ready"
            except Exception:
                checks["mongodb"] = "not_ready"
                ready = False
        else:
            checks["mongodb"] = "not_configured"
            ready = False

        # Redis
        if "redis" in _app_state:
            try:
                await _app_state["redis"].client.ping()
                checks["redis"] = "ready"
            except Exception:
                checks["redis"] = "not_ready"
                ready = False
        else:
            checks["redis"] = "not_configured"
            ready = False

        # Kafka Producer
        if "producer" in _app_state and _app_state["producer"].producer:
            checks["kafka_producer"] = "ready"
        else:
            checks["kafka_producer"] = "not_ready"
            ready = False
    else:
        ready = False

    return {"status": "ready" if ready else "not_ready", "checks": checks}
