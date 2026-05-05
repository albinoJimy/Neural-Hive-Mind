"""Testes unitários para Health Check."""

import pytest
from fastapi.testclient import TestClient


def test_health_check_returns_200(client: TestClient) -> None:
    """Health check deve retornar 200 e status healthy."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "ok"]
    assert "version" in data


def test_health_check_includes_version(client: TestClient) -> None:
    """
    Health check deve incluir versão do serviço (INV-10).

    INV-10: All services respond to GET /health with {status, version} JSON.
    """
    response = client.get("/health")

    data = response.json()
    # INV-10: version field must be present
    assert "version" in data
    assert isinstance(data["version"], str)


def test_health_check_status_field(client: TestClient) -> None:
    """
    Health check deve ter campo status (INV-10).

    INV-10: All services respond to GET /health with {status, version} JSON.
    """
    response = client.get("/health")

    data = response.json()
    # INV-10: status field must be present and be "healthy" or "unhealthy"
    assert "status" in data
    assert data["status"] in ["healthy", "unhealthy", "ok"]


def test_health_check_includes_timestamp(client: TestClient) -> None:
    """Health check detalhado deve incluir timestamp."""
    from datetime import datetime

    response = client.get("/health/detailed")

    data = response.json()
    assert "timestamp" in data
    # Validar formato ISO
    datetime.fromisoformat(data["timestamp"])


@pytest.mark.asyncio
async def test_health_readiness(async_client: TestClient) -> None:
    """Readiness check deve retornar 200 quando serviço está pronto."""
    response = await async_client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True


@pytest.mark.asyncio
async def test_health_liveness(async_client: TestClient) -> None:
    """Liveness check deve retornar 200 quando serviço está vivo."""
    response = await async_client.get("/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["alive"] is True


def test_health_detailed(client: TestClient) -> None:
    """Health check detalhado deve retornar informações adicionais."""
    response = client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()
    # Verificar campos obrigatórios INV-10
    assert "status" in data
    assert "version" in data
    # Campos adicionais na versão detalhada
    assert "service" in data
    assert "environment" in data
    assert "timestamp" in data


def test_health_check_returns_json_content_type(client: TestClient) -> None:
    """Health check deve retornar JSON (INV-10)."""
    response = client.get("/health")

    # INV-10: Response format must be JSON
    assert response.headers["content-type"] == "application/json"


def test_root_endpoint(client: TestClient) -> None:
    """Endpoint raiz deve retornar informações do serviço."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "unified-gateway"
    assert "version" in data
    assert "status" in data
    assert "docs" in data
    assert "health" in data
