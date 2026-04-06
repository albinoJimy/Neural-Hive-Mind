"""
FastAPI application para Guard MCP Server.

Fornece endpoints HTTP para health checks e monitorização.
O servidor MCP principal roda via stdio.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from guard_mcp_server.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Guard MCP Server",
    description="Servidor MCP para validação de segurança",
    version=settings.service_version,
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": settings.service_name,
            "version": settings.service_version,
        }
    )


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    return JSONResponse(
        content={
            "status": "ready",
            "service": settings.service_name,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
