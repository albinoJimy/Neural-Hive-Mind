"""
Health Router - Gateway de Intenções

Endpoints de health check para Kubernetes probes e monitorização.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


class HealthResponse(BaseModel):
    """Resposta padrão de health check."""

    status: str
    timestamp: str
    version: str = "1.0.0"
    service_name: str = "gateway-intencoes"
    neural_hive_component: str = "gateway"
    neural_hive_layer: str = "experiencia"


class ReadinessResponse(BaseModel):
    """Resposta de readiness probe."""

    status: str
    timestamp: str
    service_name: str = "gateway-intencoes"
    checks: dict[str, str] = {}


# Health manager global (será injetado pelo main.py)
_health_manager: Any = None


def set_health_manager(health_manager: Any) -> None:
    """Define o health manager global (injetado pelo main.py)."""
    global _health_manager
    _health_manager = health_manager


def get_health_manager() -> Any:
    """Retorna o health manager global."""
    return _health_manager


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint para Kubernetes liveness probe.

    Verifica o estado geral do serviço e retorna:
    - status: healthy, degraded ou unhealthy
    - Componentes verificados (redis, kafka, etc.)
    - Timestamp atual
    """
    health_manager = get_health_manager()

    if not health_manager:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "message": "Health manager not initialized",
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "1.0.0",
            },
        )

    try:
        # Run all health checks
        health_results = await health_manager.check_all()
        overall_status = health_manager.get_overall_status()

        # Format results for response
        component_statuses = {}
        if isinstance(health_results, dict) and "checks" in health_results:
            # Stub mode
            component_statuses = health_results.get("checks", {})
        else:
            # Production mode com neural_hive_observability
            for name, result in health_results.items():
                component_statuses[name] = {
                    "status": result.status.value
                    if hasattr(result, "status")
                    else result.get("status", "unknown"),
                    "message": result.message
                    if hasattr(result, "message")
                    else result.get("message", ""),
                    "duration_seconds": result.duration_seconds
                    if hasattr(result, "duration_seconds")
                    else 0,
                    "timestamp": result.timestamp
                    if hasattr(result, "timestamp")
                    else datetime.now(UTC).isoformat(),
                    "details": result.details
                    if hasattr(result, "details")
                    else result.get("details", {}),
                }

        # Overall status handling
        status_value = (
            overall_status
            if isinstance(overall_status, str)
            else (overall_status.value if hasattr(overall_status, "value") else "unknown")
        )

        response_data = {
            "status": status_value,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0.0",
            "service_name": "gateway-intencoes",
            "neural_hive_component": "gateway",
            "neural_hive_layer": "experiencia",
            "components": component_statuses,
        }

        # Return appropriate HTTP status code based on health
        from neural_hive_observability.health import HealthStatus

        if overall_status in [HealthStatus.UNHEALTHY]:
            return JSONResponse(status_code=503, content=response_data)
        if overall_status in [HealthStatus.DEGRADED]:
            return JSONResponse(status_code=200, content=response_data)
        return response_data

    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "message": f"Health check error: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "1.0.0",
                "service_name": "gateway-intencoes",
            },
        )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    """
    Readiness probe endpoint para Kubernetes.

    Verifica apenas componentes críticos para aceitar tráfego:
    - Redis (cache)
    - Kafka producer (mensageria)
    - OTEL pipeline (se habilitado)
    """
    health_manager = get_health_manager()

    if not health_manager:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "message": "Health manager not initialized",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    try:
        # Check critical components for readiness
        critical_checks = ["redis", "kafka_producer"]
        overall_ready = True
        check_results = {}

        for check_name in critical_checks:
            result = await health_manager.check_single(check_name)
            if result:
                check_results[check_name] = (
                    result.status.value if hasattr(result.status, "value") else str(result.status)
                )
                from neural_hive_observability.health import HealthStatus

                if result.status != HealthStatus.HEALTHY:
                    overall_ready = False
            else:
                check_results[check_name] = "not_configured"

        response_data = {
            "status": "ready" if overall_ready else "not_ready",
            "timestamp": datetime.now(UTC).isoformat(),
            "service_name": "gateway-intencoes",
            "neural_hive_component": "gateway",
            "checks": check_results,
        }

        return JSONResponse(status_code=200 if overall_ready else 503, content=response_data)

    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "message": f"Readiness check error: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )


@router.get("/live")
async def liveness_check():
    """
    Liveness probe endpoint para Kubernetes.

    Retorna se o serviço está em execução (sem verificar dependências externas).
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat(),
        "service_name": "gateway-intencoes",
    }
