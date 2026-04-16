"""Main application for Documentation Generation service."""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from structlog import get_logger

from src.config.settings import get_settings
from src.api.routers.documentation import router as docs_router

logger = get_logger(__name__)

settings = get_settings()

# Criar aplicação FastAPI
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Documentation Generation API for Neural Hive-Mind"
)

# Incluir routers
app.include_router(docs_router, prefix=settings.api_prefix)

# Middleware
@app.middleware("http")
async def log_requests(request, call_next):
    """Middleware para logging de requests."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        request_id=request_id
    )
    response = await call_next(request)
    logger.info(
        "request_completed",
        status_code=response.status_code,
        request_id=request_id
    )
    return response


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": settings.service_name,
        "status": "healthy",
        "version": settings.service_version
    }


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global de exceções."""
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
