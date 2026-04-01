# Optimizer MCP Server - Entry Point

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings
from src.server import mcp

logger = logging.getLogger(__name__)
settings = get_settings()

# Criar aplicação FastAPI
app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
)

# Configurar CORS - usa configuração segura por ambiente via neural_hive_security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
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


# Montar servidor MCP
app.mount("/mcp", mcp.get_app())


@app.post("/")
async def jsonrpc_endpoint(request: dict) -> dict:
    """Endpoint JSON-RPC 2.0 para protocolo MCP."""
    return await mcp.handle_jsonrpc(request)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3011,
        reload=True,
        log_level=settings.log_level.lower(),
    )
