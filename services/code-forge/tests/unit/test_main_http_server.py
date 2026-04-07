"""
Testes para os endpoints HTTP principais do Code Forge.

Cobre health, ready, metrics e outros endpoints fundamentais.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from fastapi import FastAPI, Request
from starlette.responses import Response
import os


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock variaveis de ambiente para os testes."""
    env_vars = {
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_DB": "test_db",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_pass",
        "MONGODB_HOST": "localhost",
        "REDIS_HOST": "localhost",
        "SERVICE_REGISTRY_HOST": "localhost",
        "EXECUTION_TICKET_SERVICE_URL": "http://localhost:8000",
        "TEMPLATES_GIT_REPO": "https://github.com/test/repo.git",
    }

    # Salvar valores originais
    original_values = {k: os.environ.get(k) for k in env_vars.keys()}

    # Definir valores mock
    for k, v in env_vars.items():
        os.environ[k] = v

    yield

    # Restaurar valores originais
    for k, v in original_values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.mark.asyncio
async def test_health_endpoint(mock_env_vars):
    """Health check deve retornar status healthy."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "code-forge"


@pytest.mark.asyncio
async def test_ready_endpoint_all_connected(mock_env_vars):
    """Readiness check deve retornar ready quando todas dependencias estao conectadas."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    # Configurar mocks de clientes
    app.state.postgres_client = AsyncMock()
    app.state.mongodb_client = AsyncMock()
    app.state.redis_client = AsyncMock()
    app.state.redis_client.health_check = AsyncMock(return_value=True)
    app.state.kafka_consumer = AsyncMock()
    app.state.kafka_producer = AsyncMock()
    app.state.git_client = AsyncMock()
    app.state.service_registry = AsyncMock()
    app.state.ticket_client = AsyncMock()
    app.state.s3_artifact_client = AsyncMock()
    app.state.s3_artifact_client.health_check = AsyncMock(return_value=True)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["ready"] is True


@pytest.mark.asyncio
async def test_ready_endpoint_missing_dependency(mock_env_vars):
    """Readiness check deve retornar not_ready quando dependencias obrigatorias faltam."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    # Configurar apenas algumas dependencias
    app.state.postgres_client = AsyncMock()
    app.state.mongodb_client = None  # Faltando
    app.state.redis_client = AsyncMock()
    app.state.kafka_consumer = AsyncMock()
    app.state.kafka_producer = AsyncMock()
    app.state.git_client = AsyncMock()
    app.state.service_registry = AsyncMock()
    app.state.ticket_client = AsyncMock()

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["ready"] is False


@pytest.mark.asyncio
async def test_ready_endpoint_optional_clients_disabled(mock_env_vars):
    """Readiness check deve aceitar clientes opcionais como disabled."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    # Configurar clientes obrigatorios
    app.state.postgres_client = AsyncMock()
    app.state.mongodb_client = AsyncMock()
    app.state.redis_client = AsyncMock()
    app.state.redis_client.health_check = AsyncMock(return_value=True)
    app.state.kafka_consumer = AsyncMock()
    app.state.kafka_producer = AsyncMock()
    app.state.git_client = AsyncMock()
    app.state.service_registry = AsyncMock()
    app.state.ticket_client = AsyncMock()

    # Configurar clientes opcionais como disabled
    app.state.snyk_client = MagicMock()
    app.state.snyk_client.enabled = False
    app.state.trivy_client = MagicMock()
    app.state.trivy_client.enabled = False
    app.state.sonarqube_client = MagicMock()
    app.state.sonarqube_client.enabled = False

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["ready"] is True
    assert data["dependencies"]["snyk"] == "disabled"
    assert data["dependencies"]["trivy"] == "disabled"


@pytest.mark.asyncio
async def test_metrics_endpoint(mock_env_vars):
    """Metrics endpoint deve retornar metricas Prometheus."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"


@pytest.mark.asyncio
async def test_ready_endpoint_redis_health_check(mock_env_vars):
    """Readiness check deve verificar health do Redis."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    # Configurar clientes
    app.state.postgres_client = AsyncMock()
    app.state.mongodb_client = AsyncMock()
    app.state.redis_client = AsyncMock()
    app.state.redis_client.health_check = AsyncMock(return_value=False)  # Unhealthy
    app.state.kafka_consumer = AsyncMock()
    app.state.kafka_producer = AsyncMock()
    app.state.git_client = AsyncMock()
    app.state.service_registry = AsyncMock()
    app.state.ticket_client = AsyncMock()

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["dependencies"]["redis"] == "disconnected"


@pytest.mark.asyncio
async def test_ready_endpoint_s3_health_check(mock_env_vars):
    """Readiness check deve verificar health do S3 quando configurado."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    # Configurar clientes
    app.state.postgres_client = AsyncMock()
    app.state.mongodb_client = AsyncMock()
    app.state.redis_client = AsyncMock()
    app.state.redis_client.health_check = AsyncMock(return_value=True)
    app.state.kafka_consumer = AsyncMock()
    app.state.kafka_producer = AsyncMock()
    app.state.git_client = AsyncMock()
    app.state.service_registry = AsyncMock()
    app.state.ticket_client = AsyncMock()
    app.state.s3_artifact_client = AsyncMock()
    app.state.s3_artifact_client.health_check = AsyncMock(return_value=True)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["dependencies"]["s3"] == "connected"


@pytest.mark.asyncio
async def test_ready_endpoint_without_s3(mock_env_vars):
    """Readiness check deve funcionar sem S3 configurado."""
    from src.api.http_server import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    # Configurar clientes obrigatorios (sem S3)
    app.state.postgres_client = AsyncMock()
    app.state.mongodb_client = AsyncMock()
    app.state.redis_client = AsyncMock()
    app.state.redis_client.health_check = AsyncMock(return_value=True)
    app.state.kafka_consumer = AsyncMock()
    app.state.kafka_producer = AsyncMock()
    app.state.git_client = AsyncMock()
    app.state.service_registry = AsyncMock()
    app.state.ticket_client = AsyncMock()

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["s3"] == "disabled"
