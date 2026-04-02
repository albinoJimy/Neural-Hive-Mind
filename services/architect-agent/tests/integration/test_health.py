"""Testes de integração para endpoints de health do Architect Agent."""

import pytest

from neural_hive_api.health import BaseHealthCheck, CheckResult, HealthStatus


class MongoDBCheck(BaseHealthCheck):
    """Check de conectividade MongoDB."""

    def __init__(self, mongo_client):
        super().__init__("mongodb", critical=True)
        self.mongo_client = mongo_client

    async def check(self):
        try:
            await self.mongo_client.admin.command("ping")
            return CheckResult(name="mongodb", status=HealthStatus.HEALTHY)
        except Exception as e:
            return CheckResult(name="mongodb", status=HealthStatus.UNHEALTHY, message=str(e))


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(test_app):
    """Health endpoint deve retornar 200."""
    response = test_app.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "architect-agent"
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
    assert data["service"] == "architect-agent"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_200(test_app):
    """Readiness endpoint deve retornar 200."""
    response = test_app.get("/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "architect-agent"
    assert "timestamp" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_health_response_includes_service_name(test_app):
    """Health response deve incluir nome do serviço."""
    response = test_app.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "architect-agent"


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
