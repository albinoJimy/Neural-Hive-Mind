"""
Servidor MCP para Healer Agents usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de detecção de incidentes, execução de playbooks e auto-recuperação.
"""

import structlog
from fastmcp import FastMCP

from healer_mcp_server.config import get_settings
from healer_mcp_server.tools.healer_tools import register_healer_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Healer MCP Server",
    version=settings.service_version,
    instructions="Ferramentas de detecção de incidentes, execução de playbooks e auto-recuperação",
)


@mcp.resource("healer://info")
def get_healer_info() -> str:
    """Retorna informações sobre o servidor Healer MCP."""
    return """
    Healer MCP Server
    =================

    Servidor MCP que fornece ferramentas de auto-recuperação para o Neural Hive Mind.

    Ferramentas disponíveis:
    - detect_incident: Detectar incidentes automaticamente
    - execute_playbook: Executar playbooks de recuperação
    - validate_recovery: Validar sucesso da recuperação
    - monitor_health: Monitorar saúde dos serviços
    - escalate_issue: Escalar incidentes não resolvidos

    Uso:
    - Detectar incidentes automaticamente via métricas
    - Executar playbooks de recuperação automatizada
    - Validar sucesso da recuperação
    - Monitorar saúde dos serviços continuamente
    - Escalar incidentes não resolvidos para times apropriados
    """


# Registrar ferramentas
register_healer_tools(mcp)

logger.info("healer_mcp_server_initialized", name=mcp.name, version=settings.service_version)
