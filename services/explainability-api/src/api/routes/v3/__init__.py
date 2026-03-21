"""
V3 API routes package.
"""

from fastapi import APIRouter
from .hierarchical import router, create_v3_router, V3ExplanationService

__all__ = ["router", "create_v3_router", "V3ExplanationService"]
