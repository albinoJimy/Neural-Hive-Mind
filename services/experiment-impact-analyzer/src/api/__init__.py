"""API package."""

from fastapi import APIRouter

from src.api.impact_handlers import router as impact_router

api_router = APIRouter()

# Include sub-routers
api_router.include_router(impact_router)

__all__ = ["api_router"]
