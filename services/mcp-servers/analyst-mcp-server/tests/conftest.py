"""
Configuração pytest para Analyst MCP Server.
"""

import sys
from pathlib import Path

# Adicionar src ao path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Adicionar shared module
shared_path = Path(__file__).parent.parent.parent / "shared"
if shared_path.exists():
    sys.path.insert(0, str(shared_path))


# Importar módulos para garantir cobertura
def pytest_configure(config):  # noqa: ARG001
    """Configuração do pytest."""
    import analyst_mcp_server.server  # noqa: F401
    import analyst_mcp_server.tools.analyst_tools  # noqa: F401
