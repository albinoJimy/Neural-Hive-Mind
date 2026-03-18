# Optimizer MCP Server - Entry Point

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Criar aplicação FastAPI
app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "healthy",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "message": "Optimizer MCP Server running",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3011,
        reload=True,
        log_level=settings.log_level.lower(),
    )
