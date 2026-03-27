from fastapi import APIRouter

from src.api.routers import (
    health_router,
    pipeline_runs_router,
    manifests_router,
    anomalies_router,
    insights_router,
)

api_router = APIRouter()

# Inclui todos os routers
api_router.include_router(health_router)
api_router.include_router(pipeline_runs_router)
api_router.include_router(manifests_router)
api_router.include_router(anomalies_router)
api_router.include_router(insights_router)

__all__ = ["api_router"]
