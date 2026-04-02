"""Testes de integração para health API do specialist-architecture."""

import pytest


@pytest.mark.asyncio
class TestArchitectureSpecialistHealth:
    """Testes de health check do Architecture Specialist."""

    @pytest.mark.skip(reason="Requires running FastAPI server")
    async def test_health_endpoint(self, http_client):
        """Testa endpoint /health básico."""
        response = await http_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]

    @pytest.mark.skip(reason="Requires running FastAPI server")
    async def test_ready_endpoint(self, http_client):
        """Testa endpoint /ready (readiness)."""
        response = await http_client.get("/ready")

        assert response.status_code in (200, 503)
        data = response.json()
        assert "ready" in data or "status" in data
