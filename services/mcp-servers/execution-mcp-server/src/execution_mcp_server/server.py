"""
Servidor MCP para Execution Tickets usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de gerenciamento de Execution Tickets.
"""

import structlog
from fastmcp import FastMCP

from execution_mcp_server.config import get_settings
from execution_mcp_server.tools.execution_tools import register_execution_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Execution MCP Server",
    version=settings.service_version,
    instructions="Ferramentas para gerenciamento de Execution Tickets"
)


@mcp.resource("execution://info")
def get_execution_info() -> str:
    """Retorna informações sobre o servidor Execution MCP."""
    return """
    Execution MCP Server
    =====================

    Servidor MCP que fornece ferramentas para gerenciamento de Execution Tickets.

    Ferramentas disponíveis:
    - create_ticket: Criar novo execution ticket
    - update_status: Atualizar status de um ticket
    - query_ticket: Consultar tickets por ID ou filtros
    - generate_token: Gerar token JWT para autenticação
    - dispatch_webhook: Disparar webhook de notificação

    Uso:
    - Orchestrator cria tickets para tarefas
    - Workers atualizam status durante execução
    - Serviços consultam tickets para rastreamento
    - Webhooks notificam mudanças de status
    """


# Registrar ferramentas
register_execution_tools(mcp)

logger.info(
    "execution_mcp_server_initialized",
    name=mcp.name,
    version=settings.service_version
)
