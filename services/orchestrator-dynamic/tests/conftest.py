"""
Conftest global para testes do orchestrator-dynamic.

Configura sys.path para permitir imports do src e limpa registry do Prometheus.
"""

import sys
from pathlib import Path

import pytest
from prometheus_client import REGISTRY

# Adicionar src ao path imediatamente
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def pytest_configure(config):
    """Hook para configurar pytest antes da coleta de testes."""
    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


@pytest.fixture(autouse=True)
def clean_prometheus_registry():
    """Limpa o registry do Prometheus antes de cada teste para evitar métricas duplicadas."""
    # Coletar todos os collectors antes de limpar
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
    # Limpar novamente após o teste
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass
