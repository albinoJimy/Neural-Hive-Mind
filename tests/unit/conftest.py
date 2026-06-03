"""
Auto-mark conftest para tests/unit/.

run-tests.sh invoca `pytest tests/unit -m unit`, mas nenhum dos
ficheiros aplica @pytest.mark.unit explicitamente. Sem isto, pytest
deselecciona todos os 1675 testes coletados e retorna exit code 5
(treated as failure by the runner).

Esta hook aplica automaticamente o marker `unit` a qualquer teste
recolhido sob tests/unit/, alinhando localização do ficheiro com
filtro de execução.
"""

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Auto-aplica @pytest.mark.unit a tests sob tests/unit/."""
    unit_marker = pytest.mark.unit
    for item in items:
        if "/tests/unit/" in str(item.path).replace("\\", "/"):
            item.add_marker(unit_marker)
