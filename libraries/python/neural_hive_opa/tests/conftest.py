"""Configuração de testes para neural_hive_opa."""

import pytest


@pytest.fixture
def anyio_backend():
    """Backend para pytest-asyncio."""
    return "asyncio"
