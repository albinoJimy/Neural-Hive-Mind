from fastapi import APIRouter

from src.api.health import router as health_router
from src.api.optimizations import router as optimizations_router
from src.api.experiments import router as experiments_router
from src.api.metrics_api import router as metrics_router

# Create main router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(health_router)
api_router.include_router(optimizations_router)
api_router.include_router(experiments_router)
api_router.include_router(metrics_router)

__all__ = ["api_router"]
