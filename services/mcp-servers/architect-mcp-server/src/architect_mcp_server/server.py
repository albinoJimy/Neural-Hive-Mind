"""
Servidor MCP para Architect Agents usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de planejamento arquitetural, validação de design e análise de padrões.
"""

import structlog
from fastmcp import FastMCP

from architect_mcp_server.config import get_settings
from architect_mcp_server.tools.architect_tools import register_architect_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Architect MCP Server",
    version=settings.service_version,
    instructions="Ferramentas de análise arquitetural, validação de design e evolução de sistemas",
)


@mcp.resource("architect://info")
def get_architect_info() -> str:
    """Retorna informações sobre o servidor Architect MCP."""
    return """
    Architect MCP Server
    =====================

    Servidor MCP que fornece ferramentas de análise arquitetural para o Neural Hive Mind.

    Ferramentas disponíveis:
    - plan_architecture: Planejar arquitetura de novas features
    - validate_design: Validar designs contra padrões e best practices
    - track_evolution: Rastrear evolução arquitetural do sistema
    - analyze_patterns: Analisar padrões e anti-patterns no código
    - generate_documentation: Gerar documentação arquitetural automática

    Uso:
    - Planejar arquitetura antes de implementar features
    - Validar designs contra padrões da indústria
    - Rastrear mudanças e versões arquiteturais
    - Identificar anti-patterns e débito técnico
    - Gerar ADRs e documentação automática
    """


# Registrar ferramentas
register_architect_tools(mcp)

logger.info("architect_mcp_server_initialized", name=mcp.name, version=settings.service_version)
