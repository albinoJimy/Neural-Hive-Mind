"""Routers API do ML Inference API."""
from fastapi import APIRouter

from . import health as health_module
from . import inference as inference_module

# Router principal que inclui todos os sub-routers
api_router = APIRouter()
api_router.include_router(health_module.router, tags=["Health"])
api_router.include_router(inference_module.router, tags=["Inference"])

__all__ = ["api_router"]
