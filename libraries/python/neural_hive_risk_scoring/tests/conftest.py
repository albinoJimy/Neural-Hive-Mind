"""Configuração pytest para neural_hive_risk_scoring."""

import pytest
import sys
from pathlib import Path

# Adicionar bibliotecas ao path
lib_path = Path(__file__).parent.parent.parent.parent.parent / "libraries" / "python"
sys.path.insert(0, str(lib_path))


@pytest.fixture
def sample_entity():
    """Entidade de exemplo para testes."""
    return {
        "id": "test-entity-123",
        "name": "Test Plan",
        "priority": "high",
        "complexity": "medium",
        "estimated_cost": 50000,
        "security_level": "internal",
        "handles_pii": False,
    }
