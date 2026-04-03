"""
Main entry point para Execution MCP Server.

Este módulo fornece o ponto de entrada para executar o servidor MCP
standalone via stdio.
"""

import asyncio
import sys

# Adicionar path do shared module
sys.path.insert(0, "/app")

from execution_mcp_server.config import get_settings
from execution_mcp_server.server import mcp


async def main() -> None:
    """Função principal para executar o servidor MCP."""
    settings = get_settings()

    # Executar servidor MCP via stdio
    await mcp.run(transport="stdio")


if __name__ == "__main__":
    asyncio.run(main())
