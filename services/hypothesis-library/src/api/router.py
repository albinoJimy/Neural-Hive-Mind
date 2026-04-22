"""Router principal da API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.hypotheses_routes import router as hypotheses_router
from src.config.settings import Settings, get_settings
from src.services.hypothesis_service import HypothesisService

# Router principal
api_router = APIRouter()

# Router de hipóteses
api_router.include_router(
    hypotheses_router,
    prefix="/hypotheses",
    tags=["hypotheses"],
)


# Dependency para obter service
async def get_hypothesis_service() -> HypothesisService:
    """Obtém instância do HypothesisService."""
    from src.main import hypothesis_service

    return hypothesis_service


# Endpoint raiz da API
@api_router.get("/")
async def api_root(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Endpoint raiz da API."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "api_version": "v1",
        "endpoints": {
            "hypotheses": "/hypotheses",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
    }


# Endpoint de health da API
@api_router.get("/health")
async def api_health() -> JSONResponse:
    """Health check da API."""
    return JSONResponse({"status": "healthy"})


# Endpoint de métricas de hipóteses
@api_router.get("/metrics/aggregations")
async def get_aggregations(
    service: Annotated[HypothesisService, Depends(get_hypothesis_service)],
) -> dict[str, Any]:
    """Retorna agregações para dashboard."""
    return await service.get_aggregations()
