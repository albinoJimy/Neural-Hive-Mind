"""
Testes unitários para SLAMonitor.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import httpx

from src.sla.sla_monitor import SLAMonitor
from src.config.settings import OrchestratorSettings


@pytest.fixture
def mock_config():
    """Fixture com configurações mock."""
    config = MagicMock(spec=OrchestratorSettings)
    config.sla_management_host = 'localhost'
    config.sla_management_port = 8000
    config.sla_management_timeout_seconds = 5
    config.sla_management_cache_ttl_seconds = 10
    config.sla_deadline_warning_threshold = 0.8
    config.sla_budget_critical_threshold = 0.2
    return config


@pytest.fixture
def mock_redis():
    """Fixture com cliente Redis mock."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


@pytest.fixture
def mock_metrics():
    """Fixture com métricas mock."""
    metrics = MagicMock()
    metrics.record_sla_check_duration = MagicMock()
    metrics.record_sla_monitor_error = MagicMock()
    return metrics


@pytest.fixture
def ticket_deadline_approaching():
    """Ticket com deadline próximo (>80% consumido)."""
    now = datetime.now().timestamp() * 1000
    deadline = now + 1000  # 1 segundo restante
    created = now - 4000  # criado há 4 segundos (total 5 segundos, 80% consumido)
    return {
        'ticket_id': 'ticket-1',
        'sla': {'deadline': int(deadline), 'timeout_ms': 5000},
        'created_at': int(created)
    }


@pytest.fixture
def ticket_deadline_safe():
    """Ticket com deadline seguro (<80% consumido)."""
    now = datetime.now().timestamp() * 1000
    deadline = now + 4000  # 4 segundos restantes
    created = now - 1000  # criado há 1 segundo (total 5 segundos, 20% consumido)
    return {
        'ticket_id': 'ticket-2',
        'sla': {'deadline': int(deadline), 'timeout_ms': 5000},
        'created_at': int(created)
    }


@pytest.mark.asyncio
async def test_check_ticket_deadline_approaching(
    mock_config, mock_redis, mock_metrics, ticket_deadline_approaching
):
    """Testa detecção de deadline próximo (>80% consumido)."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)

    result = await monitor.check_ticket_deadline(ticket_deadline_approaching)

    assert result['deadline_approaching'] is True
    assert result['percent_consumed'] >= 0.8
    assert result['remaining_seconds'] <= 2
    assert 'sla_deadline' in result
    assert result['sla_deadline'] is not None
    mock_metrics.record_sla_check_duration.assert_called_once()


@pytest.mark.asyncio
async def test_check_ticket_deadline_safe(
    mock_config, mock_redis, mock_metrics, ticket_deadline_safe
):
    """Testa ticket com deadline seguro (<80%)."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)

    result = await monitor.check_ticket_deadline(ticket_deadline_safe)

    assert result['deadline_approaching'] is False
    assert result['percent_consumed'] < 0.8
    assert result['remaining_seconds'] > 2
    mock_metrics.record_sla_check_duration.assert_called_once()


@pytest.mark.asyncio
async def test_check_ticket_deadline_missing_fields(
    mock_config, mock_redis, mock_metrics
):
    """Testa ticket sem campos SLA."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    ticket = {'ticket_id': 'ticket-3'}

    result = await monitor.check_ticket_deadline(ticket)

    assert result['deadline_approaching'] is False
    assert result['remaining_seconds'] == 0
    assert result['percent_consumed'] == 0
    assert result['sla_deadline'] is None


@pytest.mark.asyncio
async def test_check_workflow_sla_multiple_tickets(
    mock_config, mock_redis, mock_metrics, ticket_deadline_approaching, ticket_deadline_safe
):
    """Testa agregação de SLA de múltiplos tickets."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)

    tickets = [
        {'ticket': ticket_deadline_approaching},
        {'ticket': ticket_deadline_safe}
    ]

    result = await monitor.check_workflow_sla('workflow-1', tickets)

    assert result['deadline_approaching'] is True
    assert len(result['critical_tickets']) == 1
    assert 'ticket-1' in result['critical_tickets']
    assert result['remaining_seconds'] <= 2
    assert 'ticket_deadline_data' in result
    assert 'ticket-1' in result['ticket_deadline_data']
    assert result['ticket_deadline_data']['ticket-1']['sla_deadline'] is not None


@pytest.mark.asyncio
async def test_check_workflow_sla_no_critical_tickets(
    mock_config, mock_redis, mock_metrics, ticket_deadline_safe
):
    """Testa workflow sem tickets críticos."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)

    tickets = [
        {'ticket': ticket_deadline_safe}
    ]

    result = await monitor.check_workflow_sla('workflow-2', tickets)

    assert result['deadline_approaching'] is False
    assert len(result['critical_tickets']) == 0


@pytest.mark.asyncio
async def test_get_service_budget_success(mock_config, mock_redis, mock_metrics):
    """Testa consulta bem-sucedida de budget via API."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    await monitor.initialize()

    budget_data = {
        'error_budget_remaining': 0.35,
        'status': 'WARNING',
        'burn_rates': [{'window_hours': 1, 'rate': 4.2}]
    }

    with patch.object(monitor, '_fetch_budget_from_api', return_value=budget_data):
        result = await monitor.get_service_budget('orchestrator-dynamic')

    assert result == budget_data
    mock_redis.setex.assert_called_once()  # Deve cachear

    await monitor.close()


@pytest.mark.asyncio
async def test_get_service_budget_cached(mock_config, mock_redis, mock_metrics):
    """Testa uso de cache Redis."""
    import json

    cached_data = {
        'error_budget_remaining': 0.45,
        'status': 'HEALTHY'
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    await monitor.initialize()

    result = await monitor.get_service_budget('orchestrator-dynamic')

    assert result == cached_data
    mock_redis.get.assert_called_once()

    await monitor.close()


@pytest.mark.asyncio
async def test_get_service_budget_api_failure(mock_config, mock_redis, mock_metrics):
    """Testa fail-open em caso de falha na API."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    await monitor.initialize()

    with patch.object(
        monitor,
        '_fetch_budget_from_api',
        side_effect=httpx.RequestError("Connection failed")
    ):
        result = await monitor.get_service_budget('orchestrator-dynamic')

    assert result is None  # Fail-open
    mock_metrics.record_sla_monitor_error.assert_called_once_with('api_error')

    await monitor.close()


@pytest.mark.asyncio
async def test_check_budget_threshold_critical(mock_config, mock_redis, mock_metrics):
    """Testa detecção de budget crítico (<20%)."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    await monitor.initialize()

    budget_data = {
        'error_budget_remaining': 0.15,
        'status': 'CRITICAL'
    }

    with patch.object(monitor, 'get_service_budget', return_value=budget_data):
        is_critical, data = await monitor.check_budget_threshold('orchestrator-dynamic', 0.2)

    assert is_critical is True
    assert data == budget_data

    await monitor.close()


@pytest.mark.asyncio
async def test_check_budget_threshold_healthy(mock_config, mock_redis, mock_metrics):
    """Testa budget saudável (>20%)."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    await monitor.initialize()

    budget_data = {
        'error_budget_remaining': 0.75,
        'status': 'HEALTHY'
    }

    with patch.object(monitor, 'get_service_budget', return_value=budget_data):
        is_critical, data = await monitor.check_budget_threshold('orchestrator-dynamic', 0.2)

    assert is_critical is False
    assert data == budget_data

    await monitor.close()


@pytest.mark.asyncio
async def test_check_budget_threshold_no_data(mock_config, mock_redis, mock_metrics):
    """Testa comportamento quando não há dados de budget."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)
    await monitor.initialize()

    with patch.object(monitor, 'get_service_budget', return_value=None):
        is_critical, data = await monitor.check_budget_threshold('orchestrator-dynamic', 0.2)

    assert is_critical is False  # Fail-open
    assert data is None

    await monitor.close()


@pytest.mark.asyncio
async def test_initialize_and_close(mock_config, mock_redis, mock_metrics):
    """Testa lifecycle de inicialização e cleanup."""
    monitor = SLAMonitor(mock_config, mock_redis, mock_metrics)

    assert monitor.http_client is None

    await monitor.initialize()
    assert monitor.http_client is not None

    await monitor.close()
    # Verificar que close foi chamado (http_client foi fechado)
