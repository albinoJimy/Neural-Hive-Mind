"""
Servidor MCP para Scout Agents usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de descoberta e análise de código.
"""

import structlog
from fastmcp import FastMCP

from scout_mcp_server.config import get_settings
from scout_mcp_server.tools.scout_tools import register_scout_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Scout MCP Server",
    version=settings.service_version,
    instructions="Ferramentas de descoberta e análise de código para Scout Agents",
)


@mcp.resource("scout://info")
def get_scout_info() -> str:
    """Retorna informações sobre o servidor Scout MCP."""
    return """
    Scout MCP Server
    ================

    Servidor MCP que fornece ferramentas para exploração de codebase.

    Ferramentas disponíveis:
    - list_files: Lista arquivos de um diretório
    - search_code: Busca padrões no código
    - analyze_structure: Analisa estrutura de diretórios

    Uso:
    - Scout Agents usam estas tools para analisar codebases
    - Queen Agent orquestra calls para exploração autónoma
    - Resultados enriquecem recomendações de refatoração
    """


# Registrar ferramentas
register_scout_tools(mcp)

logger.info("scout_mcp_server_initialized", name=mcp.name, version=settings.service_version)
