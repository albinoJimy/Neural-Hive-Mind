"""
Conftest para testes do neural_hive_agent_sdk.
"""

import pytest
import sys
import os

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================================
# Configuração pytest
# ============================================================================


def pytest_configure(config):
    """Configuração adicional do pytest."""
    config.addinivalue_line(
        "markers",
        "unit: Testes unitários (sem dependências externas)"
    )
    config.addinivalue_line(
        "markers",
        "integration: Testes de integração (requer serviços externos)"
    )
    config.addinivalue_line(
        "markers",
        "asyncio: Testes assíncronos"
    )


@pytest.fixture(autouse=True)
def reset_event_loop_policy():
    """Reseta política de loop de eventos entre testes."""
    yield
    # Limpeza após teste
