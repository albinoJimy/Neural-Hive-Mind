"""Pytest configuration e fixtures para testes de integração do Worker Agents.

Este módulo fornece fixtures para testes E2E e health endpoints.
"""
import asyncio
import os
import pytest
from typing import AsyncGenerator, Generator

from fastapi.testclient import TestClient

from src.api.http_server import create_http_server
from src.config.settings import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def worker_config():
    """Configuração para testes."""
    return get_settings()


@pytest.fixture
async def test_app(worker_config):
    """Aplicação FastAPI configurada para testes."""
    app_state = {}
    app = create_http_server(worker_config, app_state)
    client = TestClient(app)
    yield client
