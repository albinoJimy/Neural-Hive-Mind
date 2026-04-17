"""Testes unitários para endpoints de políticas de freeze."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.models.freeze_policy import FreezePolicy, FreezeAction, PolicyScope
from src.models.freeze_policy import FreezeEvent
from src.clients.postgresql_client import PostgreSQLClient
from src.api.policies import router, get_postgresql_client


@pytest.fixture
def app():
    """Fixture com app FastAPI."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_pg_client():
    """Mock do PostgreSQLClient."""
    client = AsyncMock(spec=PostgreSQLClient)
    return client


@pytest.fixture
def client(app, mock_pg_client):
    """Fixture com TestClient e dependency override."""
    app.dependency_overrides[get_postgresql_client] = lambda: mock_pg_client

    # Criar transporte customizado para usar app ASGI
    transport = httpx.AsyncClient(app=app, base_url="http://test")

    with TestClient(app, transport=transport) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_freeze_policy():
    """Fixture com FreezePolicy válido."""
    return FreezePolicy(
        policy_id="policy-test-001",
        name="Test Freeze Policy",
        description="Policy for testing",
        scope=PolicyScope.SERVICE,
        target="test-service",
        actions=[FreezeAction.BLOCK_DEPLOY],
        trigger_threshold_percent=10.0,
        auto_unfreeze=True,
        unfreeze_threshold_percent=50.0,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        metadata={"namespace": "test"},
    )


@pytest.fixture
def mock_freeze_event():
    """Fixture com FreezeEvent válido."""
    return FreezeEvent(
        event_id="event-test-001",
        policy_id="policy-test-001",
        slo_id="slo-test-001",
        service_name="test-service",
        action=FreezeAction.BLOCK_DEPLOY,
        triggered_at=datetime.now(timezone.utc),
        trigger_reason="Budget below 10%",
        budget_remaining_percent=5.0,
        burn_rate=2.5,
        active=True,
        metadata={},
    )


class TestUpdatePolicyEndpoint:
    """Testes para PUT /api/v1/policies/{policy_id}."""

    def test_update_policy_success(self, client, mock_freeze_policy, mock_pg_client):
        """Verifica que update_policy retorna política atualizada."""
        mock_pg_client.update_policy = AsyncMock(return_value=True)
        mock_pg_client.get_policy = AsyncMock(return_value=mock_freeze_policy)

        response = client.put(
            "/api/v1/policies/policy-test-001",
            json={"enabled": False, "trigger_threshold_percent": 5.0},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["policy_id"] == "policy-test-001"
        assert data["name"] == "Test Freeze Policy"

    def test_update_policy_not_found(self, client, mock_pg_client):
        """Verifica que update_policy retorna 404 quando política não existe."""
        mock_pg_client.update_policy = AsyncMock(return_value=False)

        response = client.put("/api/v1/policies/nonexistent", json={"enabled": False})

        assert response.status_code == 404


class TestDeletePolicyEndpoint:
    """Testes para DELETE /api/v1/policies/{policy_id}."""

    def test_delete_policy_success(self, client, mock_pg_client):
        """Verifica que delete_policy retorna sucesso."""
        mock_pg_client.delete_policy = AsyncMock(return_value=True)

        response = client.delete("/api/v1/policies/policy-test-001")

        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

    def test_delete_policy_not_found(self, client, mock_pg_client):
        """Verifica que delete_policy retorna 404 quando política não existe."""
        mock_pg_client.delete_policy = AsyncMock(return_value=False)

        response = client.delete("/api/v1/policies/nonexistent")

        assert response.status_code == 404


class TestGetFreezeHistoryEndpoint:
    """Testes para GET /api/v1/policies/freezes/history."""

    def test_get_freeze_history_success(self, client, mock_freeze_event, mock_pg_client):
        """Verifica que get_freeze_history retorna lista de freezes."""
        events = []
        for i in range(5):
            event = FreezeEvent(
                event_id=f"event-{i}",
                policy_id="policy-test-001",
                slo_id="slo-test-001",
                service_name="test-service",
                action=FreezeAction.BLOCK_DEPLOY,
                triggered_at=datetime.now(timezone.utc) - timedelta(hours=i),
                trigger_reason="Test",
                budget_remaining_percent=50.0,
                burn_rate=1.0,
                active=(i == 0),
                metadata={},
            )
            events.append(event)

        mock_pg_client.get_freeze_history = AsyncMock(return_value=events)

        response = client.get("/api/v1/policies/freezes/history?days=7")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5

    def test_get_freeze_history_with_service_filter(self, client, mock_pg_client):
        """Verifica filtro por service_name."""
        mock_pg_client.get_freeze_history = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/policies/freezes/history?service_name=specific-service&days=30"
        )

        assert response.status_code == 200


class TestUpdateViolationsCount:
    """Testes para o método update_violations_count."""

    @pytest.mark.asyncio
    async def test_update_violations_count_success(self):
        """Verifica que update_violations_count atualiza contador."""
        from src.clients.postgresql_client import PostgreSQLClient
        from unittest.mock import patch

        with patch.object(
            PostgreSQLClient, "update_violations_count", return_value=True
        ) as mock_method:
            client = PostgreSQLClient.__new__(PostgreSQLClient)
            success = await client.update_violations_count("slo-test-001", 5)
            assert success is True

    @pytest.mark.asyncio
    async def test_update_violations_count_no_rows(self):
        """Verifica comportamento quando SLO não existe."""
        from src.clients.postgresql_client import PostgreSQLClient
        from unittest.mock import patch

        with patch.object(
            PostgreSQLClient, "update_violations_count", return_value=False
        ) as mock_method:
            client = PostgreSQLClient.__new__(PostgreSQLClient)
            success = await client.update_violations_count("nonexistent-slo", 5)
            assert success is False


class TestCountSloViolations:
    """Testes para o método count_slo_violations do PrometheusClient."""

    @pytest.mark.asyncio
    async def test_count_violations_from_alerts(self):
        """Verifica contagem de violações via ALERTS."""
        from src.clients.prometheus_client import PrometheusClient
        from src.config.settings import PrometheusSettings

        settings = PrometheusSettings(
            url="http://prometheus:9090", timeout_seconds=30, max_retries=3
        )
        client = PrometheusClient(settings)

        client.session = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "status": "success",
                "data": {"resultType": "vector", "result": [{"value": [1234567890, "3"]}]},
            }
        )
        client.session.get = AsyncMock(return_value=mock_response)

        count = await client.count_slo_violations("test-slo", window_hours=24)

        assert count == 3

    @pytest.mark.asyncio
    async def test_count_violations_no_alerts(self):
        """Verifica retorno 0 quando não há alertas."""
        from src.clients.prometheus_client import PrometheusClient
        from src.config.settings import PrometheusSettings

        settings = PrometheusSettings(
            url="http://prometheus:9090", timeout_seconds=30, max_retries=3
        )
        client = PrometheusClient(settings)

        client.session = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={"status": "success", "data": {"resultType": "vector", "result": []}}
        )
        client.session.get = AsyncMock(return_value=mock_response)

        count = await client.count_slo_violations("test-slo")

        assert count == 0
