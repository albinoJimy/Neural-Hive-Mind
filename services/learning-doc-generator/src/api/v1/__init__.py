"""API v1 routers"""

from fastapi import APIRouter

from .docs import router as docs_router

router = APIRouter()
router.include_router(docs_router, prefix="/docs", tags=["documents"])

__all__ = ["router"]
