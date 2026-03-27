"""Routers API REST para Architect Agent."""

from src.api.routers.architecture import router as architecture_router
from src.api.routers.validation import router as validation_router

__all__ = ["architecture_router", "validation_router"]
