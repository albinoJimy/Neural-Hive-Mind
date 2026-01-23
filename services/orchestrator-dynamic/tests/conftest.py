"""
Conftest global para testes do orchestrator-dynamic.

Configura sys.path para permitir imports do src.
"""

import sys
from pathlib import Path

import pytest

# Adicionar src ao path imediatamente
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def pytest_configure(config):
    """Hook para configurar pytest antes da coleta de testes."""
    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
