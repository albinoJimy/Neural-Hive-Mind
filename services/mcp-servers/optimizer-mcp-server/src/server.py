# Optimizer MCP Server

from fastmcp import FastMCP

from src.tools.optimizer_tools import register_optimizer_tools

# Criar servidor MCP
mcp = FastMCP(
    name="Optimizer MCP Server",
    instructions="""
Servidor MCP para otimização de código.

Ferramentas disponíveis:
- suggest_refactors: Sugere refatorações baseado em análise estática
- analyze_performance: Analisa métricas de performance
- optimize_queries: Otimiza queries MongoDB
""",
)

# Registrar ferramentas
register_optimizer_tools(mcp)
