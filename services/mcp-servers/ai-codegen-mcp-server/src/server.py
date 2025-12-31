"""
Servidor MCP para geração de código com IA usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de geração de código via GitHub Copilot e OpenAI.
"""

import structlog
from fastmcp import FastMCP

from .config import get_settings
from .tools import register_codegen_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="AI Code Generation MCP Server",
    version=settings.service_version,
    description="Geração e explicação de código via GitHub Copilot e OpenAI"
)


@mcp.resource("codegen://info")
def get_codegen_info() -> str:
    """Retorna informações sobre o servidor AI CodeGen MCP."""
    return """
    AI Code Generation MCP Server
    ==============================

    Servidor MCP que fornece ferramentas para geração de código usando IA.

    Ferramentas disponíveis:
    - generate_code: Gera código a partir de descrição
    - complete_code: Autocomplete de código
    - explain_code: Explica trechos de código

    Providers suportados:
    - OpenAI (GPT-4 Turbo)
    - GitHub Copilot

    Configuração:
    - OPENAI_API_KEY: Chave de API da OpenAI
    - GITHUB_TOKEN: Token do GitHub com acesso ao Copilot
    - DEFAULT_PROVIDER: Provider padrão (auto, openai, copilot)
    """


# Registrar ferramentas
register_codegen_tools(mcp)

logger.info(
    "ai_codegen_mcp_server_initialized",
    name=mcp.name,
    version=settings.service_version
)
