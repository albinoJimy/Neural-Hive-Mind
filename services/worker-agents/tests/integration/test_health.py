"""Testes de integração para endpoints de health do Worker Agents."""

import pytest

from neural_hive_api.health import BaseHealthCheck, CheckResult, HealthStatus


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(test_app):
    """Health endpoint deve retornar 200."""
    response = test_app.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "worker-agents"
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "timestamp" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_liveness_endpoint_returns_200(test_app):
    """Liveness endpoint deve sempre retornar 200 com status healthy."""
    response = test_app.get("/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "worker-agents"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_200(test_app):
    """Readiness endpoint deve retornar 200."""
    response = test_app.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "worker-agents"
    assert "timestamp" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_health_response_includes_service_name(test_app):
    """Health response deve incluir nome do serviço."""
    response = test_app.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "worker-agents"


@pytest.mark.asyncio
async def test_legacy_live_endpoint_backward_compat(test_app):
    """Endpoint /live deve funcionar para backward compatibility."""
    response = test_app.get("/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_legacy_ready_endpoint_backward_compat(test_app):
    """Endpoint /ready deve funcionar para backward compatibility."""
    response = test_app.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "service" in data
