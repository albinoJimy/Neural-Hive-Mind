"""
Servidor MCP para SonarQube usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de análise de qualidade de código via SonarQube REST API.
"""

import structlog
from fastmcp import FastMCP

from .config import get_settings
from .tools import register_sonarqube_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="SonarQube MCP Server",
    version=settings.service_version,
    description="Análise de qualidade de código e métricas via SonarQube"
)


@mcp.resource("sonarqube://info")
def get_sonarqube_info() -> str:
    """Retorna informações sobre o servidor SonarQube MCP."""
    return """
    SonarQube MCP Server
    ====================

    Servidor MCP que fornece ferramentas para análise de qualidade de código via SonarQube.

    Ferramentas disponíveis:
    - get_quality_gate: Obtém status do Quality Gate
    - get_issues: Busca issues de código
    - get_metrics: Obtém métricas de qualidade
    - wait_for_analysis: Aguarda conclusão de análise

    Configuração:
    - SONARQUBE_URL: URL do servidor SonarQube
    - SONARQUBE_TOKEN: Token de autenticação
    """


# Registrar ferramentas
register_sonarqube_tools(mcp)

logger.info(
    "sonarqube_mcp_server_initialized",
    name=mcp.name,
    version=settings.service_version
)
