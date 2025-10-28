from datetime import datetime
from fastapi import APIRouter, status
from pydantic import BaseModel

from src.config.settings import get_settings

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version=settings.service_version
    )


@router.get("/health/liveness", status_code=status.HTTP_200_OK)
async def liveness() -> dict:
    """Liveness probe"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@router.get("/health/readiness", status_code=status.HTTP_200_OK)
async def readiness() -> dict:
    """Readiness probe"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}
