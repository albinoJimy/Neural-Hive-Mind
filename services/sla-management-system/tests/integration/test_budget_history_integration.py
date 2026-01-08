"""Testes de integração para funcionalidades de histórico de budget."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.budgets import router, get_postgresql_client
from src.models.error_budget import ErrorBudget, BudgetStatus, BurnRate, BurnRateLevel
from src.models.slo_definition import SLODefinition, SLOType, SLIQuery


@pytest.fixture
def mock_slo():
    """Fixture com SLO válido."""
    return SLODefinition(
        slo_id="slo-test-001",
        name="Test SLO",
        description="Test SLO description",
        slo_type=SLOType.LATENCY,
        service_name="test-service",
        layer="orchestration",
        target=99.0,
        window_days=30,
        sli_query=SLIQuery(
            metric_name="http_request_duration_seconds",
            query="histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            aggregation="avg"
        ),
        enabled=True,
        metadata={}
    )


@pytest.fixture
def mock_budget_history_data():
    """Fixture com dados de histórico de budgets simulando cenário real."""
    budgets = []
    base_time = datetime.utcnow()

    # Simular 50 budgets ao longo de 7 dias
    for i in range(50):
        hours_offset = i * 3.36  # ~50 budgets em 7 dias
        budget = ErrorBudget(
            budget_id=f"budget-{i:04d}",
            slo_id="slo-test-001",
            service_name="test-service",
            calculated_at=base_time - timedelta(hours=hours_offset),
            window_start=base_time - timedelta(days=30, hours=hours_offset),
            window_end=base_time - timedelta(hours=hours_offset),
            sli_value=99.5 - (i * 0.02),
            slo_target=99.0,
            error_budget_total=1.0,
            error_budget_consumed=50.0 + (i * 0.5),
            error_budget_remaining=50.0 - (i * 0.5),
            status=BudgetStatus.WARNING if i < 30 else BudgetStatus.CRITICAL,
            burn_rates=[
                BurnRate(window_hours=1, rate=1.0 + (i * 0.05), level=BurnRateLevel.NORMAL),
                BurnRate(window_hours=6, rate=0.8 + (i * 0.03), level=BurnRateLevel.NORMAL)
            ],
            violations_count=i // 10,
            metadata={"slo_type": "LATENCY"}
        )
        budgets.append(budget)

    return budgets


@pytest.fixture
def mock_pg_client(mock_slo, mock_budget_history_data):
    """Fixture com mock completo do PostgreSQL client."""
    client = MagicMock()
    client.get_slo = AsyncMock(return_value=mock_slo)
    client.get_budget_history = AsyncMock(return_value=mock_budget_history_data)
    client.get_budget_trends = AsyncMock(return_value={
        'trend_direction': 'degrading',
        'average_remaining': 35.0,
        'min_remaining': 25.0,
        'max_consumed': 75.0,
        'volatility': 8.5,
        'violations_frequency': 0.7,
        'burn_rate_avg': 2.2
    })
    return client


@pytest.fixture
def test_app(mock_pg_client):
    """Fixture com aplicação FastAPI de teste."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_postgresql_client] = lambda: mock_pg_client
    return app


@pytest.fixture
def client(test_app):
    """Fixture com cliente de teste."""
    return TestClient(test_app)


class TestBudgetHistoryEndToEnd:
    """Testes de integração end-to-end para histórico de budgets."""

    def test_get_budget_history_basic(self, client, mock_pg_client, mock_budget_history_data):
        """Testa requisição básica de histórico."""
        response = client.get("/api/v1/budgets/slo-test-001/history?days=7")

        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 50
        assert data['period_days'] == 7
        assert data['aggregation'] is None
        assert data['trends'] is None
        assert len(data['budgets']) == 50

        # Verificar que chamou o método correto
        mock_pg_client.get_budget_history.assert_called_once_with("slo-test-001", 7, None)

    def test_get_budget_history_with_daily_aggregation(self, client, mock_pg_client):
        """Testa requisição com agregação diária."""
        # Configurar mock para retornar 7 registros (um por dia)
        daily_budgets = [
            ErrorBudget(
                budget_id=f"daily-{i}",
                slo_id="slo-test-001",
                service_name="test-service",
                calculated_at=datetime.utcnow() - timedelta(days=i),
                window_start=datetime.utcnow() - timedelta(days=i),
                window_end=datetime.utcnow() - timedelta(days=i-1),
                sli_value=99.0,
                slo_target=99.0,
                error_budget_total=1.0,
                error_budget_consumed=50.0,
                error_budget_remaining=50.0,
                status=BudgetStatus.WARNING,
                burn_rates=[],
                violations_count=0,
                metadata={}
            )
            for i in range(7)
        ]
        mock_pg_client.get_budget_history = AsyncMock(return_value=daily_budgets)

        response = client.get("/api/v1/budgets/slo-test-001/history?days=7&aggregation=daily")

        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 7
        assert data['aggregation'] == 'daily'
        mock_pg_client.get_budget_history.assert_called_once_with("slo-test-001", 7, 'daily')

    def test_get_budget_history_with_hourly_aggregation(self, client, mock_pg_client):
        """Testa requisição com agregação por hora."""
        hourly_budgets = [
            ErrorBudget(
                budget_id=f"hourly-{i}",
                slo_id="slo-test-001",
                service_name="test-service",
                calculated_at=datetime.utcnow() - timedelta(hours=i),
                window_start=datetime.utcnow() - timedelta(hours=i),
                window_end=datetime.utcnow() - timedelta(hours=i-1),
                sli_value=99.0,
                slo_target=99.0,
                error_budget_total=1.0,
                error_budget_consumed=50.0,
                error_budget_remaining=50.0,
                status=BudgetStatus.WARNING,
                burn_rates=[],
                violations_count=0,
                metadata={}
            )
            for i in range(24)
        ]
        mock_pg_client.get_budget_history = AsyncMock(return_value=hourly_budgets)

        response = client.get("/api/v1/budgets/slo-test-001/history?days=1&aggregation=hourly")

        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 24
        assert data['aggregation'] == 'hourly'

    def test_get_budget_history_with_trends(self, client, mock_pg_client):
        """Testa requisição incluindo análise de tendências."""
        response = client.get("/api/v1/budgets/slo-test-001/history?days=7&include_trends=true")

        assert response.status_code == 200
        data = response.json()

        assert data['trends'] is not None
        assert data['trends']['trend_direction'] == 'degrading'
        assert data['trends']['average_remaining'] == 35.0
        assert data['trends']['min_remaining'] == 25.0
        assert data['trends']['max_consumed'] == 75.0
        assert data['trends']['volatility'] == 8.5
        assert data['trends']['violations_frequency'] == 0.7
        assert data['trends']['burn_rate_avg'] == 2.2

        # Verificar que ambos métodos foram chamados
        mock_pg_client.get_budget_history.assert_called_once()
        mock_pg_client.get_budget_trends.assert_called_once_with("slo-test-001", 7)

    def test_get_budget_history_all_options(self, client, mock_pg_client):
        """Testa requisição com todas as opções."""
        response = client.get(
            "/api/v1/budgets/slo-test-001/history"
            "?days=30&aggregation=daily&include_trends=true"
        )

        assert response.status_code == 200
        data = response.json()

        assert data['period_days'] == 30
        assert data['aggregation'] == 'daily'
        assert data['trends'] is not None


class TestBudgetHistoryInvalidSloId:
    """Testes para requisições com SLO inválido."""

    def test_budget_history_slo_not_found(self, client, mock_pg_client):
        """Verifica retorno 404 para SLO inexistente."""
        mock_pg_client.get_slo = AsyncMock(return_value=None)

        response = client.get("/api/v1/budgets/nonexistent-slo/history")

        assert response.status_code == 404
        data = response.json()
        assert "não encontrado" in data['detail'].lower() or "not found" in data['detail'].lower()


class TestBudgetHistoryValidation:
    """Testes para validação de parâmetros."""

    def test_budget_history_invalid_days_too_low(self, client):
        """Verifica validação de dias mínimo."""
        response = client.get("/api/v1/budgets/slo-test-001/history?days=0")

        assert response.status_code == 422  # Validation error

    def test_budget_history_invalid_days_too_high(self, client):
        """Verifica validação de dias máximo."""
        response = client.get("/api/v1/budgets/slo-test-001/history?days=100")

        assert response.status_code == 422  # Validation error

    def test_budget_history_invalid_aggregation(self, client):
        """Verifica validação de tipo de agregação."""
        response = client.get("/api/v1/budgets/slo-test-001/history?aggregation=invalid")

        assert response.status_code == 422  # Validation error

    def test_budget_history_valid_aggregation_none(self, client, mock_pg_client):
        """Verifica que 'none' é aceito como agregação."""
        response = client.get("/api/v1/budgets/slo-test-001/history?aggregation=none")

        assert response.status_code == 200
        # Agregação 'none' deve ser normalizada para None
        mock_pg_client.get_budget_history.assert_called_once_with("slo-test-001", 7, None)


class TestBudgetHistoryOrdering:
    """Testes para verificação de ordenação."""

    def test_budget_history_ordered_by_calculated_at(self, client, mock_pg_client, mock_budget_history_data):
        """Verifica que budgets estão ordenados corretamente."""
        response = client.get("/api/v1/budgets/slo-test-001/history?days=7")

        assert response.status_code == 200
        data = response.json()

        budgets = data['budgets']
        # Verificar que estão em ordem decrescente de calculated_at
        for i in range(len(budgets) - 1):
            curr_time = datetime.fromisoformat(budgets[i]['calculated_at'].replace('Z', '+00:00'))
            next_time = datetime.fromisoformat(budgets[i + 1]['calculated_at'].replace('Z', '+00:00'))
            assert curr_time >= next_time, "Budgets devem estar ordenados DESC por calculated_at"


class TestBudgetHistoryResponseStructure:
    """Testes para estrutura de response."""

    def test_budget_history_response_has_required_fields(self, client, mock_pg_client):
        """Verifica campos obrigatórios na resposta."""
        response = client.get("/api/v1/budgets/slo-test-001/history")

        assert response.status_code == 200
        data = response.json()

        assert 'budgets' in data
        assert 'total' in data
        assert 'period_days' in data
        assert 'aggregation' in data
        assert 'trends' in data

    def test_budget_item_has_required_fields(self, client, mock_pg_client, mock_budget_history_data):
        """Verifica campos obrigatórios em cada budget."""
        response = client.get("/api/v1/budgets/slo-test-001/history")

        assert response.status_code == 200
        data = response.json()

        if data['budgets']:
            budget = data['budgets'][0]
            required_fields = [
                'budget_id', 'slo_id', 'service_name',
                'calculated_at', 'window_start', 'window_end',
                'sli_value', 'slo_target', 'error_budget_total',
                'error_budget_consumed', 'error_budget_remaining',
                'status', 'burn_rates', 'violations_count'
            ]
            for field in required_fields:
                assert field in budget, f"Campo {field} não encontrado no budget"
