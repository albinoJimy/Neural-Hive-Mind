"""Testes de integração para health check com neural_hive_api."""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from src.main import app, app_state
from neural_hive_api.health import HealthRouter


@pytest.mark.asyncio
class TestHealthRouterIntegration:
    """Testa integração do HealthRouter com analyst-agents."""

    async def test_health_router_exists(self):
        """Verifica que health_router existe em app_state."""
        assert hasattr(app_state, "health_router")
        assert isinstance(app_state.health_router, HealthRouter)
        assert app_state.health_router.service_name == "analyst-agents"

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self):
        """Endpoint /health deve retornar 200."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "service" in data
            assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_health_live_endpoint_returns_200(self):
        """Endpoint /health/live deve retornar 200."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/live")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("healthy", "degraded", "unhealthy")

    @pytest.mark.asyncio
    async def test_health_ready_endpoint_returns_200(self):
        """Endpoint /health/ready deve retornar 200."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "checks" in data

    @pytest.mark.asyncio
    async def test_legacy_ready_endpoint_still_works(self):
        """Endpoint legado /ready deve continuar funcionando."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")
            # Pode retornar 200 ou 503 dependendo do estado dos clientes
            assert response.status_code in (200, 503)
            data = response.json()
            assert "ready" in data or "status" in data

    @pytest.mark.asyncio
    async def test_legacy_live_endpoint_still_works(self):
        """Endpoint legado /live deve continuar funcionando."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/live")
            assert response.status_code == 200
            data = response.json()
            assert "alive" in data or "status" in data
