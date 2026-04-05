"""
Servidor MCP para Code Forge usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de geração de código/IaC e templates.
"""

import structlog
from fastmcp import FastMCP

from code_forge_mcp_server.config import get_settings
from code_forge_mcp_server.tools.code_forge_tools import register_code_forge_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Code Forge MCP Server",
    version=settings.service_version,
    instructions="Ferramentas para geração de código/IaC e templates",
)


@mcp.resource("http://code_forge/info")
def get_code_forge_info() -> str:
    """Retorna informações sobre o servidor Code Forge MCP."""
    return """
    Code Forge MCP Server
    =====================

    Servidor MCP que fornece ferramentas para geração de código/IaC.

    Ferramentas disponíveis:
    - generate_artifact: Gerar artefatos de código/IaC
    - validate_template: Validar templates de código
    - optimize_generation: Otimizar geração com caching
    - select_template: Selecionar templates baseado em contexto
    - pipeline_execute: Executar pipelines de geração

    Uso:
    - Architect Agents geram código estrutural
    - Code Forge compõe artefatos finais
    - Templates são validados e reutilizados
    - Caching otimiza gerações repetidas
    - Pipelines orquestram workflows complexos
    """


# Registrar ferramentas
register_code_forge_tools(mcp)

logger.info("code_forge_mcp_server_initialized", name=mcp.name, version=settings.service_version)
