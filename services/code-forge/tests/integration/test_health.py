"""Testes de integração para health check com neural_hive_api."""

import pytest

from neural_hive_api.health import HealthRouter
from neural_hive_api.health.models import HealthStatus


class TestHealthRouterIntegration:
    """Testa integração do HealthRouter com code-forge."""

    def test_health_router_can_be_created(self):
        """Verifica que HealthRouter pode ser instanciado para code-forge."""
        health_router = HealthRouter("code-forge")
        assert isinstance(health_router, HealthRouter)
        assert health_router.service_name == "code-forge"

    def test_health_router_has_checks_list(self):
        """Verifica que HealthRouter tem lista de checks."""
        health_router = HealthRouter("code-forge")
        assert hasattr(health_router, "checks")
        assert isinstance(health_router.checks, list)

    def test_health_router_has_add_route_method(self):
        """Verifica que HealthRouter tem método add_route."""
        health_router = HealthRouter("code-forge")
        assert hasattr(health_router, "add_route")
        assert callable(health_router.add_route)

    @pytest.mark.asyncio
    async def test_health_liveness_returns_healthy(self):
        """Verifica que liveness probe retorna HEALTHY por padrão."""
        health_router = HealthRouter("code-forge")
        response = await health_router._liveness()
        assert response.status == HealthStatus.HEALTHY
        assert response.service == "code-forge"
        assert response.timestamp is not None
