"""
Servidor MCP para Trivy usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de scanning de vulnerabilidades via Trivy CLI.
"""

import structlog
from fastmcp import FastMCP

from .config import get_settings
from .tools import register_trivy_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Trivy MCP Server",
    version=settings.service_version,
    description="Scanner de vulnerabilidades para containers, filesystems e repositórios"
)


@mcp.resource("trivy://info")
def get_trivy_info() -> str:
    """Retorna informações sobre o servidor Trivy MCP."""
    return """
    Trivy MCP Server
    ================

    Servidor MCP que fornece ferramentas para scanning de segurança usando Trivy.

    Ferramentas disponíveis:
    - scan_image: Escaneia imagens de container
    - scan_filesystem: Escaneia diretórios locais
    - scan_repository: Escaneia repositórios Git

    Para mais informações, consulte a documentação do Trivy:
    https://aquasecurity.github.io/trivy
    """


# Registrar ferramentas
register_trivy_tools(mcp)

logger.info(
    "trivy_mcp_server_initialized",
    name=mcp.name,
    version=settings.service_version
)
