from fastapi import APIRouter

# Create main router
api_router = APIRouter()

# Import and include sub-routers
# from src.api import health, optimizations, experiments, metrics_api

__all__ = ["api_router"]
