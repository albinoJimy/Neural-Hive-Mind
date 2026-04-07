"""
Servidor MCP para Queen Agents usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
estratégicas do Queen Agent.
"""

import structlog
from fastmcp import FastMCP

from queen_mcp_server.config import get_settings
from queen_mcp_server.tools.queen_tools import register_queen_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Queen MCP Server",
    version=settings.service_version,
    instructions="Ferramentas estratégicas do Queen Agent para orquestração e decisão",
)


@mcp.resource("queen://info")
def get_queen_info() -> str:
    """Retorna informações sobre o servidor Queen MCP."""
    return """
    Queen MCP Server
    ================

    Servidor MCP que fornece ferramentas estratégicas do Queen Agent.

    Ferramentas disponíveis:
    - make_decision: Tomar decisões estratégicas
    - arbitrate_conflict: Resolver conflitos entre agentes
    - replan_workflow: Replanejar workflows falhados
    - approve_exception: Aprovar exceções à política
    - adjust_qos: Ajustar QoS de serviços
    - health_check: Verificar saúde dos componentes

    Uso:
    - Queen Agent orquestra decisões estratégicas do sistema
    - Outros agentes solicitam arbitragem de conflitos
    - Orchestrator aciona replanejamento de workflows
    - Guard Agents solicitam aprovação de exceções
    - Serviços ajustam QoS baseado em condições operacionais
    - Monitoramento verifica saúde dos componentes
    """


# Registrar ferramentas
register_queen_tools(mcp)

logger.info("queen_mcp_server_initialized", name=mcp.name, version=settings.service_version)
