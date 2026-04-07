"""
Entry point do Queen MCP Server.

Inicializa o servidor HTTP com FastAPI + FastMCP,
configurando observability e graceful shutdown.
"""

import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI

from queen_mcp_server.config import get_settings
from queen_mcp_server.server import mcp

# Adicionar path do shared module
sys.path.insert(0, "/app")
from shared.mcp_base import BaseMCPServer

logger = structlog.get_logger(__name__)
settings = get_settings()


class QueenMCPServer(BaseMCPServer):
    """Servidor MCP para Queen Agents."""

    async def initialize(self) -> None:
        """Inicializa recursos do servidor."""
        logger.info("queen_mcp_server_resources_initialized")

    async def cleanup(self) -> None:
        """Libera recursos do servidor."""
        logger.info("queen_mcp_server_cleanup_complete")


# Instância do servidor
server = QueenMCPServer(
    name=settings.service_name, version=settings.service_version, allowed_origins=["*"]
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    await server.initialize()
    server.set_ready(True)
    logger.info("queen_mcp_server_started", host="0.0.0.0", port=settings.port)

    yield

    # Shutdown
    server.set_ready(False)
    await server.cleanup()
    logger.info("queen_mcp_server_stopped")


# Criar aplicação FastAPI
app = FastAPI(
    title="Queen MCP Server",
    version=settings.service_version,
    description="Servidor MCP para decisões estratégicas e orquestração",
    lifespan=lifespan,
)

# Configurar CORS e health checks
server.setup_cors(app)
server.setup_health_checks(app)

# Montar servidor MCP no endpoint raiz
# FastMCP expõe endpoint JSON-RPC em /
app.mount("/mcp", mcp.get_app())


@app.post("/")
async def jsonrpc_endpoint(request: dict) -> dict:
    """Endpoint JSON-RPC 2.0 para protocolo MCP."""
    return await mcp.handle_jsonrpc(request)


def main() -> None:
    """Função principal para executar o servidor."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
