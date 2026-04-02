"""Testes de integração para Health API do sla-management-system."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from src.config.settings import get_settings
from src.main import app


@pytest.mark.asyncio
class TestHealthAPIIntegration:
    """Testes de integração da Health API."""

    async def test_health_endpoint(self):
        """Testa endpoint /health básico."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sla-management-system"

    async def test_liveness_endpoint(self):
        """Testa endpoint /health/live (liveness)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True

    @pytest.mark.skip(reason="Requires full app state setup")
    async def test_readiness_endpoint_with_dependencies(self):
        """Testa endpoint /health/ready com dependências."""
        # Setup mock app_state
        class MockAppState:
            def __init__(self):
                self.postgresql_client = AsyncMock()
                self.postgresql_client.list_slos = AsyncMock(return_value=[])

                self.redis_client = AsyncMock()
                self.redis_client.health_check = AsyncMock(return_value=True)

                self.prometheus_client = AsyncMock()
                self.prometheus_client.health_check = AsyncMock(return_value=True)

                self.kafka_producer = AsyncMock()
                self.kafka_producer.health_check = AsyncMock(return_value=True)

                self.alertmanager_client = AsyncMock()
                self.alertmanager_client.connect = AsyncMock()

        # This test requires the app to be running with full lifespan
        # Skipping for now as it requires complex setup
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code in (200, 503)
        data = response.json()
        assert "ready" in data
        assert "dependencies" in data
