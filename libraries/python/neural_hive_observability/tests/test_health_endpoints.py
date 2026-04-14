"""
Tests para health endpoints padronizados.

Cobre startup probes para Kubernetes.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from neural_hive_observability.health_endpoints import (
    create_startup_router,
)


def _create_test_app(service_name: str = "test-service", version: str = "1.0.0"):
    """Helper para criar app FastAPI com startup router."""
    app = FastAPI()
    router = create_startup_router(service_name, version)
    app.include_router(router)
    return app


def test_startup_endpoint_returns_200():
    """Testa que /health/startup retorna 200 com campos corretos."""
    app = _create_test_app()
    client = TestClient(app)

    response = client.get("/health/startup")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["service"] == "test-service"
    assert data["version"] == "1.0.0"
    assert "started_at" in data


def test_startup_endpoint_includes_started_at():
    """Testa que /health/startup inclui timestamp ISO 8601."""
    app = _create_test_app()
    client = TestClient(app)

    response = client.get("/health/startup")
    data = response.json()

    # Verifica formato ISO 8601 (contém 'T' e timezone)
    started_at = data["started_at"]
    assert "T" in started_at
    assert "+" in started_at or "Z" in started_at


def test_startup_endpoint_with_custom_service_name():
    """Testa startup endpoint com nome de serviço customizado."""
    app = _create_test_app("my-custom-service", "2.3.4")
    client = TestClient(app)

    response = client.get("/health/startup")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "my-custom-service"
    assert data["version"] == "2.3.4"


def test_startup_endpoint_response_model():
    """Testa que o response model está correto."""
    app = _create_test_app()
    client = TestClient(app)

    response = client.get("/health/startup")

    assert response.status_code == 200
    # Verifica que todos os campos do model estão presentes
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert "version" in data
    assert "started_at" in data


def test_startup_endpoint_with_prefix():
    """Testa startup endpoint com prefixo customizado via include_router."""
    app = FastAPI()
    router = create_startup_router("test-service", "1.0.0")
    app.include_router(router, prefix="/api/v1")

    client = TestClient(app)
    response = client.get("/api/v1/health/startup")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "test-service"
