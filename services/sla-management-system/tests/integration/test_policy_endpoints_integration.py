"""Testes de integração para endpoints de políticas de freeze."""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient

from src.main import app
from src.models.freeze_policy import FreezePolicy, FreezeAction, PolicyScope
from src.models.freeze_policy import FreezeEvent
from src.models.slo_definition import SLODefinition, SLOType, SLIQuery


@pytest.mark.integration
class TestPolicyLifecycleIntegration:
    """Testes de ciclo de vida completo de políticas."""

    @pytest.mark.asyncio
    async def test_create_update_delete_policy(
        self,
        async_client: AsyncClient,
        test_postgresql_client
    ):
        """Testa ciclo completo: criar, atualizar, deletar política."""
        # 1. Criar SLO base para a política
        slo = SLODefinition(
            name="test-slo-for-policy",
            description="SLO for policy testing",
            slo_type=SLOType.AVAILABILITY,
            service_name="test-service-policy",
            layer="orquestracao",
            target=0.999,
            window_days=30,
            sli_query=SLIQuery(
                metric_name="up",
                query="up{job='test-service-policy'}",
                aggregation="avg"
            ),
            enabled=True
        )
        await test_postgresql_client.create_slo(slo)

        # 2. Criar política
        policy = FreezePolicy(
            name="integration-test-policy",
            description="Policy for integration testing",
            scope=PolicyScope.SERVICE,
            target="test-service-policy",
            actions=[FreezeAction.PAUSE_DEPLOYMENTS],
            trigger_threshold_percent=10.0,
            auto_unfreeze=True,
            unfreeze_threshold_percent=50.0,
            enabled=True
        )
        policy_id = await test_postgresql_client.create_policy(policy)

        # 3. Buscar política (GET)
        response = await async_client.get(f"/api/v1/policies/{policy_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["policy_id"] == policy_id
        assert data["name"] == "integration-test-policy"
        assert data["enabled"] is True

        # 4. Atualizar política (PUT)
        response = await async_client.put(
            f"/api/v1/policies/{policy_id}",
            json={"enabled": False, "trigger_threshold_percent": 5.0}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

        # 5. Deletar política (DELETE)
        response = await async_client.delete(f"/api/v1/policies/{policy_id}")
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # 6. Verificar que foi soft deleted (ainda existe mas disabled)
        fetched_policy = await test_postgresql_client.get_policy(policy_id)
        assert fetched_policy is not None
        assert fetched_policy.enabled is False


@pytest.mark.integration
class TestFreezeHistoryIntegration:
    """Testes de integração para histórico de freezes."""

    @pytest.mark.asyncio
    async def test_freeze_history_with_resolved_events(
        self,
        async_client: AsyncClient,
        test_postgresql_client
    ):
        """Testa histórico retornando freezes ativos e resolvidos."""
        # Criar SLO
        slo = SLODefinition(
            name="test-slo-history",
            description="SLO for history testing",
            slo_type=SLOType.AVAILABILITY,
            service_name="test-service-history",
            layer="orquestracao",
            target=0.999,
            window_days=30,
            sli_query=SLIQuery(
                metric_name="up",
                query="up{job='test-service-history'}",
                aggregation="avg"
            ),
            enabled=True
        )
        slo_id = await test_postgresql_client.create_slo(slo)

        # Criar política
        policy = FreezePolicy(
            name="history-test-policy",
            description="Policy for history testing",
            scope=PolicyScope.SERVICE,
            target="test-service-history",
            actions=[FreezeAction.PAUSE_DEPLOYMENTS],
            trigger_threshold_percent=10.0,
            auto_unfreeze=True,
            unfreeze_threshold_percent=50.0,
            enabled=True
        )
        policy_id = await test_postgresql_client.create_policy(policy)

        # Criar freeze events (ativos e resolvidos)
        now = datetime.now(timezone.utc)

        # Evento ativo
        active_event = FreezeEvent(
            event_id="active-event-001",
            policy_id=policy_id,
            slo_id=slo_id,
            service_name="test-service-history",
            action=FreezeAction.PAUSE_DEPLOYMENTS,
            triggered_at=now - timedelta(hours=1),
            trigger_reason="Budget below threshold",
            budget_remaining_percent=5.0,
            burn_rate=2.0,
            active=True,
            metadata={}
        )
        await test_postgresql_client.create_freeze_event(active_event)

        # Evento resolvido
        resolved_event = FreezeEvent(
            event_id="resolved-event-001",
            policy_id=policy_id,
            slo_id=slo_id,
            service_name="test-service-history",
            action=FreezeAction.PAUSE_DEPLOYMENTS,
            triggered_at=now - timedelta(hours=24),
            trigger_reason="Budget below threshold",
            budget_remaining_percent=8.0,
            burn_rate=1.5,
            active=False,
            resolved_at=now - timedelta(hours=23),
            metadata={}
        )
        await test_postgresql_client.create_freeze_event(resolved_event)

        # Buscar histórico
        response = await async_client.get(
            "/api/v1/policies/freezes/history?service_name=test-service-history&days=7"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2

        # Verificar que temos ambos ativos e resolvidos
        event_ids = [e["event_id"] for e in data["freezes"]]
        assert "active-event-001" in event_ids
        assert "resolved-event-001" in event_ids


@pytest.mark.integration
class TestViolationsCountUpdateIntegration:
    """Testes de integração para atualização de contador de violações."""

    @pytest.mark.asyncio
    async def test_update_violations_count_flow(
        self,
        async_client: AsyncClient,
        test_postgresql_client
    ):
        """Testa fluxo de atualização de contador de violações."""
        # Criar SLO
        slo = SLODefinition(
            name="test-slo-violations",
            description="SLO for violations testing",
            slo_type=SLOType.ERROR_RATE,
            service_name="test-service-violations",
            layer="orquestracao",
            target=0.999,
            window_days=30,
            sli_query=SLIQuery(
                metric_name="errors",
                query="rate(errors_total[5m])",
                aggregation="avg"
            ),
            enabled=True
        )
        slo_id = await test_postgresql_client.create_slo(slo)

        # Criar budget inicial
        from src.models.error_budget import ErrorBudget, BudgetStatus, BurnRate, BurnRateLevel
        budget = ErrorBudget(
            slo_id=slo_id,
            service_name="test-service-violations",
            calculated_at=datetime.now(timezone.utc),
            window_start=datetime.now(timezone.utc) - timedelta(days=30),
            window_end=datetime.now(timezone.utc),
            sli_value=0.998,
            slo_target=0.999,
            error_budget_total=0.1,
            error_budget_consumed=20.0,
            error_budget_remaining=80.0,
            status=BudgetStatus.HEALTHY,
            burn_rates=[
                BurnRate(window_hours=1, rate=0.5, level=BurnRateLevel.NORMAL)
            ],
            violations_count=0,
            metadata={}
        )
        await test_postgresql_client.save_budget(budget)

        # Atualizar contador de violações
        success = await test_postgresql_client.update_violations_count(slo_id, 5)
        assert success is True

        # Buscar budget atualizado e verificar contador
        updated_budget = await test_postgresql_client.get_latest_budget(slo_id)
        assert updated_budget.violations_count == 5
        assert updated_budget.last_violation_at is not None


@pytest.fixture
async def async_client(test_postgresql_client):
    """Fixture para cliente HTTP assíncrono."""
    # Sobrescrever clientes no main
    from src import main
    main.postgresql_client = test_postgresql_client

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def test_postgresql_client(postgresql_url):
    """Fixture para cliente PostgreSQL de teste."""
    from src.clients.postgresql_client import PostgreSQLClient
    from src.config.settings import PostgreSQLSettings

    settings = PostgreSQLSettings(
        host=postgresql_url.split("@")[1].split(":")[0] if "@" in postgresql_url else "localhost",
        port=5432,
        database="test_sla",
        user="test",
        password="test",
        pool_min_size=1,
        pool_max_size=5,
        connection_timeout=30
    )

    client = PostgreSQLClient(settings)
    await client.connect()
    yield client
    await client.disconnect()
