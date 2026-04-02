"""Health check API para sla-management-system."""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from neural_hive_observability.health import HealthStatus

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check básico"""
    return {"status": "healthy", "service": "sla-management-system"}


@router.get("/ready")
async def readiness_check(request: Request):
    """Readiness check - verifica dependências"""
    app_state = request.app.state.app_state
    dependencies = {}

    try:
        # Verificar PostgreSQL
        if app_state.postgresql_client:
            try:
                await app_state.postgresql_client.list_slos()
                dependencies["postgresql"] = "connected"
            except Exception as e:
                dependencies["postgresql"] = f"error: {str(e)}"
        else:
            dependencies["postgresql"] = "disconnected"

        # Verificar Redis
        if app_state.redis_client:
            try:
                redis_ok = await app_state.redis_client.health_check()
                dependencies["redis"] = "connected" if redis_ok else "error"
            except Exception as e:
                dependencies["redis"] = f"error: {str(e)}"
        else:
            dependencies["redis"] = "disconnected"

        # Verificar Prometheus
        if app_state.prometheus_client:
            try:
                prom_ok = await app_state.prometheus_client.health_check()
                dependencies["prometheus"] = "connected" if prom_ok else "error"
            except Exception as e:
                dependencies["prometheus"] = f"error: {str(e)}"
        else:
            dependencies["prometheus"] = "disconnected"

        # Verificar Kafka (opcional)
        if app_state.kafka_producer:
            try:
                kafka_ok = await app_state.kafka_producer.health_check()
                dependencies["kafka"] = "connected" if kafka_ok else "error"
            except Exception as e:
                dependencies["kafka"] = f"error: {str(e)}"
        else:
            dependencies["kafka"] = "disabled"

        # Verificar Alertmanager (opcional)
        if app_state.alertmanager_client:
            try:
                await app_state.alertmanager_client.connect()
                dependencies["alertmanager"] = "connected"
            except Exception as e:
                dependencies["alertmanager"] = f"error: {str(e)}"
        else:
            dependencies["alertmanager"] = "disabled"

        ready = all(
            "connected" in status or "disabled" in status
            for status in dependencies.values()
        )

        if not ready:
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "dependencies": dependencies,
                    "timestamp": int(__import__("time").time() * 1000),
                },
            )

        return {
            "ready": ready,
            "dependencies": dependencies,
            "timestamp": int(__import__("time").time() * 1000),
        }

    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        return {"ready": False, "dependencies": dependencies, "error": str(e)}


@router.get("/live")
async def liveness_check():
    """Liveness check - verifica se serviço está responsivo"""
    return {"alive": True}
