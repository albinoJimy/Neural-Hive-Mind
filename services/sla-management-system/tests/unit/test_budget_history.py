"""Testes unitários para funcionalidades de histórico de budget."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.models.error_budget import ErrorBudget, BudgetStatus, BurnRate, BurnRateLevel
from src.clients.postgresql_client import PostgreSQLClient
from src.api.budgets import BudgetTrends, BudgetHistoryResponse


@pytest.fixture
def mock_error_budget():
    """Fixture com ErrorBudget válido."""
    return ErrorBudget(
        budget_id="budget-123",
        slo_id="slo-test-001",
        service_name="test-service",
        calculated_at=datetime.utcnow(),
        window_start=datetime.utcnow() - timedelta(days=7),
        window_end=datetime.utcnow(),
        sli_value=99.5,
        slo_target=99.0,
        error_budget_total=1.0,
        error_budget_consumed=50.0,
        error_budget_remaining=50.0,
        status=BudgetStatus.WARNING,
        burn_rates=[
            BurnRate(window_hours=1, rate=1.5, level=BurnRateLevel.NORMAL),
            BurnRate(window_hours=6, rate=1.2, level=BurnRateLevel.NORMAL)
        ],
        violations_count=2,
        metadata={"slo_type": "LATENCY"}
    )


@pytest.fixture
def mock_budget_list(mock_error_budget):
    """Fixture com lista de ErrorBudgets."""
    budgets = []
    base_time = datetime.utcnow()
    for i in range(10):
        budget = ErrorBudget(
            budget_id=f"budget-{i}",
            slo_id="slo-test-001",
            service_name="test-service",
            calculated_at=base_time - timedelta(hours=i),
            window_start=base_time - timedelta(days=7, hours=i),
            window_end=base_time - timedelta(hours=i),
            sli_value=99.5 - (i * 0.1),
            slo_target=99.0,
            error_budget_total=1.0,
            error_budget_consumed=50.0 + (i * 2),
            error_budget_remaining=50.0 - (i * 2),
            status=BudgetStatus.WARNING if i < 5 else BudgetStatus.CRITICAL,
            burn_rates=[],
            violations_count=i,
            metadata={}
        )
        budgets.append(budget)
    return budgets


@pytest.fixture
def mock_postgresql_client():
    """Fixture com mock do PostgreSQL client."""
    client = MagicMock(spec=PostgreSQLClient)
    client.pool = MagicMock()
    client.logger = MagicMock()
    return client


class TestGetBudgetHistoryNoAggregation:
    """Testes para get_budget_history sem agregação."""

    @pytest.mark.asyncio
    async def test_get_budget_history_returns_list(
        self,
        mock_postgresql_client,
        mock_budget_list
    ):
        """Verifica que get_budget_history retorna lista de ErrorBudget."""
        # Configurar mock para retornar dados
        mock_conn = AsyncMock()
        mock_rows = [
            {
                'budget_id': b.budget_id,
                'slo_id': b.slo_id,
                'service_name': b.service_name,
                'calculated_at': b.calculated_at,
                'window_start': b.window_start,
                'window_end': b.window_end,
                'sli_value': b.sli_value,
                'slo_target': b.slo_target,
                'error_budget_total': b.error_budget_total,
                'error_budget_consumed': b.error_budget_consumed,
                'error_budget_remaining': b.error_budget_remaining,
                'status': b.status.value,
                'burn_rates': [],
                'violations_count': b.violations_count,
                'last_violation_at': None,
                'metadata': {}
            }
            for b in mock_budget_list
        ]
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        # Configurar context manager
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        # Importar a classe real e instanciar
        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        # Executar
        result = await client.get_budget_history("slo-test-001", days=7, aggregation=None)

        # Verificar
        assert len(result) == 10
        assert all(isinstance(b, ErrorBudget) for b in result)
        mock_conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_budget_history_orders_by_calculated_at_desc(
        self,
        mock_postgresql_client,
        mock_budget_list
    ):
        """Verifica ordenação DESC por calculated_at."""
        mock_conn = AsyncMock()
        mock_rows = [
            {
                'budget_id': b.budget_id,
                'slo_id': b.slo_id,
                'service_name': b.service_name,
                'calculated_at': b.calculated_at,
                'window_start': b.window_start,
                'window_end': b.window_end,
                'sli_value': b.sli_value,
                'slo_target': b.slo_target,
                'error_budget_total': b.error_budget_total,
                'error_budget_consumed': b.error_budget_consumed,
                'error_budget_remaining': b.error_budget_remaining,
                'status': b.status.value,
                'burn_rates': [],
                'violations_count': b.violations_count,
                'last_violation_at': None,
                'metadata': {}
            }
            for b in mock_budget_list
        ]
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        result = await client.get_budget_history("slo-test-001", days=7)

        # Verificar que a query contém ORDER BY DESC
        call_args = mock_conn.fetch.call_args[0][0]
        assert 'ORDER BY' in call_args
        assert 'DESC' in call_args


class TestGetBudgetHistoryDailyAggregation:
    """Testes para get_budget_history com agregação diária."""

    @pytest.mark.asyncio
    async def test_get_budget_history_daily_uses_materialized_view(
        self,
        mock_postgresql_client
    ):
        """Verifica que agregação diária usa view materializada."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        await client.get_budget_history("slo-test-001", days=7, aggregation='daily')

        call_args = mock_conn.fetch.call_args[0][0]
        assert 'error_budgets_daily_summary' in call_args


class TestGetBudgetHistoryHourlyAggregation:
    """Testes para get_budget_history com agregação por hora."""

    @pytest.mark.asyncio
    async def test_get_budget_history_hourly_uses_window_functions(
        self,
        mock_postgresql_client
    ):
        """Verifica que agregação horária usa window functions."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        await client.get_budget_history("slo-test-001", days=7, aggregation='hourly')

        call_args = mock_conn.fetch.call_args[0][0]
        assert "date_trunc('hour'" in call_args
        assert 'AVG' in call_args


class TestGetBudgetTrendsCalculation:
    """Testes para cálculo de tendências."""

    @pytest.mark.asyncio
    async def test_get_budget_trends_returns_correct_structure(
        self,
        mock_postgresql_client
    ):
        """Verifica estrutura do retorno de trends."""
        mock_conn = AsyncMock()
        mock_row = {
            'trend_slope': -0.8,
            'average_remaining': 45.5,
            'min_remaining': 20.0,
            'max_consumed': 80.0,
            'volatility': 5.5,
            'violations_frequency': 0.5,
            'burn_rate_avg': 1.8,
            'total_days': 30
        }
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        result = await client.get_budget_trends("slo-test-001", days=30)

        assert result['trend_direction'] == 'degrading'
        assert result['average_remaining'] == 45.5
        assert result['min_remaining'] == 20.0
        assert result['max_consumed'] == 80.0
        assert result['volatility'] == 5.5
        assert result['violations_frequency'] == 0.5
        assert result['burn_rate_avg'] == 1.8

    @pytest.mark.asyncio
    async def test_get_budget_trends_improving(
        self,
        mock_postgresql_client
    ):
        """Verifica detecção de tendência de melhoria."""
        mock_conn = AsyncMock()
        mock_row = {
            'trend_slope': 1.5,  # Positivo = melhorando
            'average_remaining': 75.0,
            'min_remaining': 60.0,
            'max_consumed': 40.0,
            'volatility': 3.0,
            'violations_frequency': 0.1,
            'burn_rate_avg': 0.8,
            'total_days': 30
        }
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        result = await client.get_budget_trends("slo-test-001", days=30)

        assert result['trend_direction'] == 'improving'

    @pytest.mark.asyncio
    async def test_get_budget_trends_stable(
        self,
        mock_postgresql_client
    ):
        """Verifica detecção de tendência estável."""
        mock_conn = AsyncMock()
        mock_row = {
            'trend_slope': 0.2,  # Próximo de zero = estável
            'average_remaining': 50.0,
            'min_remaining': 48.0,
            'max_consumed': 52.0,
            'volatility': 1.0,
            'violations_frequency': 0.0,
            'burn_rate_avg': 1.0,
            'total_days': 30
        }
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        result = await client.get_budget_trends("slo-test-001", days=30)

        assert result['trend_direction'] == 'stable'

    @pytest.mark.asyncio
    async def test_get_budget_trends_no_data(
        self,
        mock_postgresql_client
    ):
        """Verifica comportamento com dados insuficientes."""
        mock_conn = AsyncMock()
        mock_row = {
            'trend_slope': None,
            'average_remaining': None,
            'min_remaining': None,
            'max_consumed': None,
            'volatility': None,
            'violations_frequency': None,
            'burn_rate_avg': None,
            'total_days': 0
        }
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        result = await client.get_budget_trends("slo-test-001", days=30)

        # Deve retornar valores default
        assert result['trend_direction'] == 'stable'
        assert result['average_remaining'] == 100.0
        assert result['min_remaining'] == 100.0
        assert result['max_consumed'] == 0.0


class TestBudgetHistoryApiEndpoint:
    """Testes para endpoint da API de histórico."""

    def test_budget_history_response_model(self):
        """Verifica estrutura do modelo de response."""
        response = BudgetHistoryResponse(
            budgets=[],
            total=0,
            period_days=7,
            aggregation='daily',
            trends=BudgetTrends(
                trend_direction='stable',
                average_remaining=50.0,
                min_remaining=40.0,
                max_consumed=60.0,
                volatility=5.0,
                violations_frequency=0.1,
                burn_rate_avg=1.2
            )
        )

        assert response.total == 0
        assert response.period_days == 7
        assert response.aggregation == 'daily'
        assert response.trends.trend_direction == 'stable'

    def test_budget_trends_model(self):
        """Verifica estrutura do modelo BudgetTrends."""
        trends = BudgetTrends(
            trend_direction='degrading',
            average_remaining=30.0,
            min_remaining=10.0,
            max_consumed=90.0,
            volatility=15.0,
            violations_frequency=2.5,
            burn_rate_avg=3.0
        )

        assert trends.trend_direction == 'degrading'
        assert trends.average_remaining == 30.0
        assert trends.violations_frequency == 2.5


class TestBudgetHistoryErrorHandling:
    """Testes para tratamento de erros."""

    @pytest.mark.asyncio
    async def test_get_budget_history_handles_db_error(
        self,
        mock_postgresql_client
    ):
        """Verifica tratamento de erro do banco de dados."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=Exception("Database error"))
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        with pytest.raises(Exception) as exc_info:
            await client.get_budget_history("slo-test-001", days=7)

        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_budget_trends_handles_db_error(
        self,
        mock_postgresql_client
    ):
        """Verifica tratamento de erro ao calcular trends."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=Exception("Query failed"))
        mock_postgresql_client.pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        client = PostgreSQLClient.__new__(PostgreSQLClient)
        client.pool = mock_postgresql_client.pool
        client.logger = mock_postgresql_client.logger

        with pytest.raises(Exception) as exc_info:
            await client.get_budget_trends("slo-test-001", days=30)

        assert "Query failed" in str(exc_info.value)
