"""
Entry point do SonarQube MCP Server.

Inicializa o servidor HTTP com FastAPI + FastMCP,
configurando observability e graceful shutdown.
"""

import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI

from .config import get_settings
from .server import mcp
from .clients import SonarQubeClient

# Adicionar path do shared module
sys.path.insert(0, "/app")
from shared.mcp_base import BaseMCPServer

logger = structlog.get_logger(__name__)
settings = get_settings()


class SonarQubeMCPServer(BaseMCPServer):
    """Servidor MCP para SonarQube."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client: SonarQubeClient | None = None

    async def initialize(self) -> None:
        """Inicializa recursos do servidor."""
        self._client = SonarQubeClient()
        logger.info("sonarqube_mcp_server_resources_initialized")

    async def cleanup(self) -> None:
        """Libera recursos do servidor."""
        if self._client:
            await self._client.close()
        logger.info("sonarqube_mcp_server_cleanup_complete")


# Instância do servidor
server = SonarQubeMCPServer(
    name=settings.service_name,
    version=settings.service_version,
    allowed_origins=settings.cors_origins.split(",")
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    await server.initialize()
    server.set_ready(True)
    logger.info(
        "sonarqube_mcp_server_started",
        host=settings.http_host,
        port=settings.http_port
    )

    yield

    # Shutdown
    server.set_ready(False)
    await server.cleanup()
    logger.info("sonarqube_mcp_server_stopped")


# Criar aplicação FastAPI
app = FastAPI(
    title="SonarQube MCP Server",
    version=settings.service_version,
    description="Servidor MCP para análise de qualidade de código com SonarQube",
    lifespan=lifespan
)

# Configurar CORS e health checks
server.setup_cors(app)
server.setup_health_checks(app)

# Montar servidor MCP
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
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    uvicorn.run(
        "src.main:app",
        host=settings.http_host,
        port=settings.http_port,
        log_level=settings.log_level.lower(),
        access_log=True
    )


if __name__ == "__main__":
    main()
