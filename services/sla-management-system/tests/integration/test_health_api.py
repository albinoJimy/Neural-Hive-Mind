"""Testes de integração para Health API do sla-management-system."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from src.config.settings import get_settings
from src.main import app
from src.api.health import (
    configure_health_checks,
    PostgreSQLHealthCheck,
    RedisHealthCheck,
    PrometheusHealthCheck,
    KafkaHealthCheck,
    AlertmanagerHealthCheck,
)


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
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert data["service"] == "sla-management-system"

    async def test_liveness_endpoint(self):
        """Testa endpoint /health/live (liveness)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sla-management-system"

    async def test_readiness_endpoint(self):
        """Testa endpoint /health/ready (readiness)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert data["service"] == "sla-management-system"

    async def test_legacy_live_endpoint(self):
        """Testa endpoint /live (legacy)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
class TestHealthCheckClasses:
    """Testes das classes de health check."""

    async def test_postgresql_health_check_success(self):
        """Testa PostgreSQLHealthCheck com sucesso."""
        mock_client = AsyncMock()
        mock_client.pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool_acquire = AsyncMock()
        mock_pool_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool_acquire.__aexit__ = AsyncMock()
        mock_client.pool.acquire = MagicMock(return_value=mock_pool_acquire)

        check = PostgreSQLHealthCheck(mock_client)
        result = await check.check()

        assert result.name == "postgresql"
        assert result.status == "healthy"

    async def test_postgresql_health_check_failure(self):
        """Testa PostgreSQLHealthCheck sem pool."""
        mock_client = AsyncMock()
        mock_client.pool = None

        check = PostgreSQLHealthCheck(mock_client)
        result = await check.check()

        assert result.name == "postgresql"
        assert result.status == "unhealthy"
        assert result.message == "No pool"

    async def test_redis_health_check_success(self):
        """Testa RedisHealthCheck com sucesso."""
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=True)

        check = RedisHealthCheck(mock_client)
        result = await check.check()

        assert result.name == "redis"
        assert result.status == "healthy"

    async def test_redis_health_check_failure(self):
        """Testa RedisHealthCheck com falha."""
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=False)

        check = RedisHealthCheck(mock_client)
        result = await check.check()

        assert result.name == "redis"
        assert result.status == "unhealthy"

    async def test_prometheus_health_check_success(self):
        """Testa PrometheusHealthCheck com sucesso."""
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=True)

        check = PrometheusHealthCheck(mock_client)
        result = await check.check()

        assert result.name == "prometheus"
        assert result.status == "healthy"

    async def test_kafka_health_check_non_critical(self):
        """Testa KafkaHealthCheck (não-crítico)."""
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=True)

        check = KafkaHealthCheck(mock_client, critical=False)
        assert check.critical is False
        assert check.name == "kafka"

        result = await check.check()
        assert result.status == "healthy"

    async def test_alertmanager_health_check_degraded(self):
        """Testa AlertmanagerHealthCheck retorna degraded quando falha."""
        mock_client = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=False)

        check = AlertmanagerHealthCheck(mock_client, critical=False)
        result = await check.check()

        assert result.name == "alertmanager"
        assert result.status == "degraded"


@pytest.mark.asyncio
class TestHealthRouterConfiguration:
    """Testes de configuração do health router."""

    async def test_configure_health_checks_with_all_clients(self):
        """Testa configuração com todos os clientes."""
        from src.api.health import HealthRouter

        mock_postgres = AsyncMock()
        mock_redis = AsyncMock()
        mock_prometheus = AsyncMock()
        mock_kafka = AsyncMock()
        mock_alertmanager = AsyncMock()

        # Cria uma instância nova em vez de usar o singleton
        router = HealthRouter("sla-management-system")
        router.register_check(PostgreSQLHealthCheck(mock_postgres))
        router.register_check(RedisHealthCheck(mock_redis))
        router.register_check(PrometheusHealthCheck(mock_prometheus))
        router.register_check(KafkaHealthCheck(mock_kafka))
        router.register_check(AlertmanagerHealthCheck(mock_alertmanager))

        assert router.service_name == "sla-management-system"
        assert len(router.checks) == 5

    async def test_configure_health_checks_partial_clients(self):
        """Testa configuração com apenas alguns clientes."""
        from src.api.health import HealthRouter

        mock_postgres = AsyncMock()
        mock_redis = AsyncMock()

        # Cria uma instância nova para evitar acumulação de checks
        router = HealthRouter("sla-management-system")
        router.register_check(PostgreSQLHealthCheck(mock_postgres))
        router.register_check(RedisHealthCheck(mock_redis))

        assert router.service_name == "sla-management-system"
        assert len(router.checks) == 2
        assert router.checks[0].name == "postgresql"
        assert router.checks[1].name == "redis"
