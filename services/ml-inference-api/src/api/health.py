"""Health check endpoints."""
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import structlog

from ..config import get_settings
from ..observability.metrics import MLInferenceMetrics


logger = structlog.get_logger()
router = APIRouter()


@router.get("/health", response_model=dict)
async def health():
    """Liveness probe - verifica se serviço está rodando."""
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
    }


@router.get("/ready", response_model=dict)
async def ready(request: Request):
    """
    Readiness probe - verifica dependências críticas.

    Verifica:
    - Modelo ML carregado
    - Circuit breaker estado
    """
    checks = {}
    settings = get_settings()

    # Verificar se predictor service está inicializado
    predictor_available = False
    if hasattr(request.app.state, "predictor_service"):
        predictor_service = request.app.state.predictor_service
        predictor_available = predictor_service is not None
        if predictor_available:
            checks["ml_model"] = predictor_service.approval_predictor is not None
            checks["circuit_breaker_closed"] = (
                predictor_service.get_circuit_breaker_state().get("state") == "CLOSED"
            )
        else:
            checks["ml_model"] = False
            checks["circuit_breaker_closed"] = False
    else:
        checks["ml_model"] = False
        checks["circuit_breaker_closed"] = False

    all_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_healthy else "not_ready", "checks": checks},
    )


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/model-info")
async def model_info(request: Request):
    """Retorna informações sobre o modelo carregado."""
    if not hasattr(request.app.state, "predictor_service"):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Predictor service not initialized"},
        )

    predictor_service = request.app.state.predictor_service
    return predictor_service.get_model_info()


@router.get("/circuit-breaker")
async def circuit_breaker_status(request: Request):
    """Retorna estado atual do circuit breaker."""
    if not hasattr(request.app.state, "predictor_service"):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Predictor service not initialized"},
        )

    predictor_service = request.app.state.predictor_service
    return predictor_service.get_circuit_breaker_state()
