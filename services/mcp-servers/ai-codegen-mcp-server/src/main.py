"""
Entry point do AI CodeGen MCP Server.

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
from .clients import OpenAIClient, CopilotClient

# Adicionar path do shared module
sys.path.insert(0, "/app")
from shared.mcp_base import BaseMCPServer

logger = structlog.get_logger(__name__)
settings = get_settings()


class AICodeGenMCPServer(BaseMCPServer):
    """Servidor MCP para geração de código com IA."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._openai_client: OpenAIClient | None = None
        self._copilot_client: CopilotClient | None = None

    async def initialize(self) -> None:
        """Inicializa recursos do servidor."""
        self._openai_client = OpenAIClient()
        self._copilot_client = CopilotClient()

        # Log disponibilidade dos providers
        providers = []
        if self._openai_client.is_available():
            providers.append("openai")
        if self._copilot_client.is_available():
            providers.append("copilot")

        logger.info(
            "ai_codegen_mcp_server_resources_initialized",
            available_providers=providers
        )

    async def cleanup(self) -> None:
        """Libera recursos do servidor."""
        if self._openai_client:
            await self._openai_client.close()
        if self._copilot_client:
            await self._copilot_client.close()
        logger.info("ai_codegen_mcp_server_cleanup_complete")


# Instância do servidor
server = AICodeGenMCPServer(
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
        "ai_codegen_mcp_server_started",
        host=settings.http_host,
        port=settings.http_port
    )

    yield

    # Shutdown
    server.set_ready(False)
    await server.cleanup()
    logger.info("ai_codegen_mcp_server_stopped")


# Criar aplicação FastAPI
app = FastAPI(
    title="AI Code Generation MCP Server",
    version=settings.service_version,
    description="Servidor MCP para geração de código com GitHub Copilot e OpenAI",
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
