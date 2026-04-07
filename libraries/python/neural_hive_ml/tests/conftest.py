"""Configuração pytest para neural_hive_ml."""

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Configura loop de eventos para testes assíncronos."""
    import asyncio

    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
