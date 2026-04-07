"""
Conftest para testes de integração do Code Forge.

Importa fixtures do conftest unitário para reutilização.
"""

import sys
from pathlib import Path

# Adicionar caminho para fixtures do unit conftest
sys.path.insert(0, str(Path(__file__).parent.parent / "unit"))

# Importar fixtures do conftest unitário explicitamente
from tests.unit.conftest import (
    event_loop,
    code_forge_settings,
    mock_metrics,
    mock_git_client,
    mock_redis_client,
    mock_mongodb_client,
    mock_mcp_client,
    mock_llm_client,
    mock_analyst_client,
    mock_sonarqube_client,
)

__all__ = [
    "event_loop",
    "code_forge_settings",
    "mock_metrics",
    "mock_git_client",
    "mock_redis_client",
    "mock_mongodb_client",
    "mock_mcp_client",
    "mock_llm_client",
    "mock_analyst_client",
    "mock_sonarqube_client",
]
