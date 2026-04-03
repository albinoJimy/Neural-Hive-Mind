"""
Servidor MCP para Analyst usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de análise de dados e insights.
"""

import structlog
from fastmcp import FastMCP

from analyst_mcp_server.config import get_settings
from analyst_mcp_server.tools.analyst_tools import register_analyst_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Analyst MCP Server",
    version=settings.service_version,
    instructions="Ferramentas para análise de dados e insights",
)


@mcp.resource("analyst://info")
def get_analyst_info() -> str:
    """Retorna informações sobre o servidor Analyst MCP."""
    return """
    Analyst MCP Server
    ==================

    Servidor MCP que fornece ferramentas para análise de dados e insights.

    Ferramentas disponíveis:
    - analyze_insights: Analisar insights de dados
    - detect_anomalies: Detectar anomalias em time-series
    - query_timeseries: Consultar dados de métricas
    - generate_dashboard: Gerar dados para dashboards
    - export_data: Exportar dados em múltiplos formatos

    Uso:
    - Analyst Agents analisam métricas do sistema
    - Scout Agents detectam anomalias em dados
    - Dashboards são gerados para visualização
    - Dados podem ser exportados para análise externa
    """


# Registrar ferramentas
register_analyst_tools(mcp)

logger.info("analyst_mcp_server_initialized", name=mcp.name, version=settings.service_version)
