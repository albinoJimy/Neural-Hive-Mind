"""
Configuração para testes E2E da FASE 4.

Provê fixtures para levantar serviços com docker-compose.
"""

import asyncio
import os
import pytest
import subprocess
from typing import AsyncGenerator
import httpx
from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture(scope="session")
def event_loop():
    """Loop de eventos para testes assíncronos."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def docker_compose_up():
    """
    Levanta serviços com docker-compose para testes E2E.

    Levanta: hypothesis-library, learning-doc-generator, experiment-impact-analyzer
    """
    compose_file = "tests/e2e/docker-compose.fase4.yml"

    # Verificar se docker-compose existe
    if not os.path.exists(compose_file):
        pytest.skip(f"Docker compose file not found: {compose_file}")

    # Levantar serviços
    subprocess.run(
        ["docker-compose", "-f", compose_file, "up", "-d"],
        check=True,
    )

    # Aguardar serviços ficarem healthy
    await asyncio.sleep(10)

    yield

    # Derrubar serviços
    subprocess.run(
        ["docker-compose", "-f", compose_file, "down", "-v"],
        check=False,
    )


@pytest.fixture
async def mongodb_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    """
    Client MongoDB assíncrono para testes.

    Cria database temporária para testes.
    """
    client = AsyncIOMotorClient("mongodb://localhost:27017")

    yield client

    # Cleanup: remover database de teste
    await client.drop_database("test_neural_hive")
    client.close()


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Client HTTP assíncrono."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture
def wait_for_service():
    """
    Helper para aguardar serviço ficar disponível.

    Uso:
        await wait_for_service("http://localhost:8010/health")
    """

    async def _wait(url: str, timeout: int = 30) -> bool:
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        return True
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    return _wait


@pytest.fixture
def test_experiment_data():
    """Dados de experimento para testes."""
    return {
        "experiment_id": "test-e2e-001",
        "experiment_name": "E2E Test Experiment",
        "experiment_type": "A_B_TEST",
        "baseline_metrics": {
            "accuracy": 0.85,
            "latency_p95": 120,
            "throughput": 1000,
        },
        "treatment_metrics": {
            "accuracy": 0.88,
            "latency_p95": 115,
            "throughput": 1050,
        },
        "start_time": "2026-04-09T00:00:00Z",
        "end_time": "2026-04-09T01:00:00Z",
    }


@pytest.fixture
def test_hypothesis_data():
    """Dados de hipótese para testes."""
    return {
        "title": "E2E Test Hypothesis",
        "description": "Hipótese para teste E2E",
        "background": "Validar componentes FASE 4",
        "expected_outcome": "Componentes funcionando corretamente",
        "metrics": ["accuracy", "latency_p95", "throughput"],
        "author": "e2e-test",
        "priority": "high",
        "tags": ["e2e", "fase4"],
    }
