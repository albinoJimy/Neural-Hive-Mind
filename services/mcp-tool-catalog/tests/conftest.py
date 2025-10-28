"""
Configuração de fixtures pytest para testes do MCP Tool Catalog.
"""

import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock de configurações."""
    from unittest.mock import MagicMock
    settings = MagicMock()
    settings.GA_POPULATION_SIZE = 10  # Reduzido para testes
    settings.GA_MAX_GENERATIONS = 5
    settings.GA_CROSSOVER_PROB = 0.7
    settings.GA_MUTATION_PROB = 0.2
    settings.GA_TOURNAMENT_SIZE = 3
    settings.GA_CONVERGENCE_THRESHOLD = 0.01
    settings.GA_TIMEOUT_SECONDS = 5
    settings.CACHE_TTL_SECONDS = 60
    return settings
