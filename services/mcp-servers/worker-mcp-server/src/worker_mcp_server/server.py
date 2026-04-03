"""
Servidor MCP para Worker Agents usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de execução distribuída, monitoramento e compensações.
"""

import structlog
from fastmcp import FastMCP

from worker_mcp_server.config import get_settings
from worker_mcp_server.tools.worker_tools import register_worker_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Worker MCP Server",
    version=settings.service_version,
    instructions="Ferramentas de execução distribuída, monitoramento e compensações saga",
)


@mcp.resource("worker://info")
def get_worker_info() -> str:
    """Retorna informações sobre o servidor Worker MCP."""
    return """
    Worker MCP Server
    ==================

    Servidor MCP que fornece ferramentas para execução distribuída.

    Ferramentas disponíveis:
    - execute_task: Executar tarefas específicas (query, transform, validate, etc.)
    - check_dependencies: Verificar dependências do workflow
    - monitor_progress: Monitorar progresso de execução
    - handle_compensation: Executar compensações (saga pattern)
    - report_status: Reportar status de execução ao Orchestrator

    Uso:
    - Worker Agents usam estas tools para executar tarefas
    - Orchestrator monitora progresso via monitor_progress
    - Saga compensation pattern para rollbacks distribuídos
    - Status updates via Kafka/HTTP para Orchestrator
    """


# Registrar ferramentas
register_worker_tools(mcp)

logger.info("worker_mcp_server_initialized", name=mcp.name, version=settings.service_version)
