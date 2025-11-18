"""
Testes unitários para AlertManager.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
import uuid

from src.sla.alert_manager import AlertManager
from src.config.settings import OrchestratorSettings


@pytest.fixture
def mock_config():
    """Fixture com configurações mock."""
    config = MagicMock(spec=OrchestratorSettings)
    config.sla_violations_topic = 'sla.violations'
    config.sla_alerts_topic = 'sla.alerts'
    config.sla_alert_deduplication_ttl_seconds = 300
    return config


@pytest.fixture
def mock_kafka_producer():
    """Fixture com Kafka producer mock."""
    producer = AsyncMock()
    producer.publish_ticket = AsyncMock(return_value={'published': True})
    return producer


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
    metrics.record_sla_alert_sent = MagicMock()
    metrics.record_sla_violation_published = MagicMock()
    metrics.record_sla_monitor_error = MagicMock()
    metrics.record_sla_alert_deduplicated = MagicMock()
    return metrics


@pytest.fixture
def budget_critical_context():
    """Contexto para alerta de budget crítico."""
    return {
        'workflow_id': 'orch-123',
        'service_name': 'orchestrator-dynamic',
        'budget_remaining': 0.15,
        'status': 'CRITICAL',
        'burn_rates': [{'window_hours': 1, 'rate': 8.5}]
    }


@pytest.fixture
def deadline_approaching_context():
    """Contexto para alerta de deadline próximo."""
    return {
        'workflow_id': 'orch-456',
        'ticket_id': 'ticket-789',
        'remaining_seconds': 30,
        'percent_consumed': 0.85,
        'sla_deadline': int(datetime.now().timestamp() * 1000)
    }


@pytest.mark.asyncio
async def test_send_proactive_alert_budget_critical(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics, budget_critical_context
):
    """Testa envio de alerta de budget crítico."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    result = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)

    assert result is True
    mock_kafka_producer.publish_ticket.assert_called_once()

    # Verificar payload do alerta
    call_args = mock_kafka_producer.publish_ticket.call_args
    assert call_args[1]['topic'] == 'sla.alerts'
    alert_payload = call_args[1]['ticket']
    assert alert_payload['event_type'] == 'ALERT'
    assert alert_payload['alert_type'] == 'BUDGET_CRITICAL'
    assert alert_payload['severity'] == 'CRITICAL'
    assert alert_payload['workflow_id'] == 'orch-123'

    # Verificar cache de deduplicação
    mock_redis.setex.assert_called_once()

    # Verificar métrica
    mock_metrics.record_sla_alert_sent.assert_called_once_with('BUDGET_CRITICAL', 'CRITICAL')


@pytest.mark.asyncio
async def test_send_proactive_alert_deadline_approaching(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics, deadline_approaching_context
):
    """Testa envio de alerta de deadline próximo."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    result = await manager.send_proactive_alert('DEADLINE_APPROACHING', deadline_approaching_context)

    assert result is True
    mock_kafka_producer.publish_ticket.assert_called_once()

    # Verificar payload
    call_args = mock_kafka_producer.publish_ticket.call_args
    assert call_args[1]['topic'] == 'sla.alerts'
    alert_payload = call_args[1]['ticket']
    assert alert_payload['event_type'] == 'ALERT'
    assert alert_payload['alert_type'] == 'DEADLINE_APPROACHING'
    assert alert_payload['severity'] == 'CRITICAL'
    assert 'ticket_id' in alert_payload['context']


@pytest.mark.asyncio
async def test_send_proactive_alert_deduplicated(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics, budget_critical_context
):
    """Testa deduplicação de alertas."""
    # Simular alerta já enviado (cache hit)
    mock_redis.get = AsyncMock(return_value="1")

    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    result = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)

    assert result is False  # Alerta não enviado (deduplicated)
    mock_kafka_producer.publish_ticket.assert_not_called()
    mock_metrics.record_sla_alert_deduplicated.assert_called_once()


@pytest.mark.asyncio
async def test_send_proactive_alert_no_redis(
    mock_config, mock_kafka_producer, mock_metrics, budget_critical_context
):
    """Testa envio de alerta sem Redis (fail-open)."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    # Não injetar Redis

    result = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)

    assert result is True  # Deve enviar mesmo sem Redis
    mock_kafka_producer.publish_ticket.assert_called_once()


@pytest.mark.asyncio
async def test_send_proactive_alert_kafka_failure(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics, budget_critical_context
):
    """Testa falha na publicação Kafka."""
    mock_kafka_producer.publish_ticket = AsyncMock(side_effect=Exception("Kafka error"))

    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    result = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)

    assert result is False
    mock_metrics.record_sla_monitor_error.assert_called_once_with('alert_publish')


@pytest.mark.asyncio
async def test_publish_sla_violation_success(
    mock_config, mock_kafka_producer, mock_metrics
):
    """Testa publicação bem-sucedida de violação SLA."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)

    violation = {
        'workflow_id': 'orch-999',
        'ticket_id': 'ticket-888',
        'violation_type': 'DEADLINE_EXCEEDED',
        'sla_deadline': int(datetime.now().timestamp() * 1000),
        'actual_completion': int(datetime.now().timestamp() * 1000) + 5000,
        'delay_ms': 5000,
        'budget_remaining': 0.1
    }

    await manager.publish_sla_violation(violation)

    mock_kafka_producer.publish_ticket.assert_called_once()

    # Verificar payload
    call_args = mock_kafka_producer.publish_ticket.call_args
    assert call_args[1]['topic'] == 'sla.violations'
    violation_event = call_args[1]['ticket']
    assert violation_event['event_type'] == 'VIOLATION'
    assert violation_event['violation_type'] == 'DEADLINE_EXCEEDED'
    assert violation_event['delay_ms'] == 5000
    assert 'violation_id' in violation_event
    assert 'timestamp' in violation_event

    # Verificar métrica
    mock_metrics.record_sla_violation_published.assert_called_once_with('DEADLINE_EXCEEDED')


@pytest.mark.asyncio
async def test_publish_sla_violation_with_defaults(
    mock_config, mock_kafka_producer, mock_metrics
):
    """Testa publicação de violação com campos mínimos (defaults aplicados)."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)

    violation = {
        'workflow_id': 'orch-111',
        'ticket_id': 'ticket-222',
        'violation_type': 'TIMEOUT'
    }

    await manager.publish_sla_violation(violation)

    call_args = mock_kafka_producer.publish_ticket.call_args
    violation_event = call_args[1]['ticket']

    # Verificar defaults
    assert violation_event['event_type'] == 'VIOLATION'
    assert violation_event['service_name'] == 'orchestrator-dynamic'
    assert violation_event['severity'] == 'WARNING'
    assert violation_event['metadata'] == {}
    assert 'timestamp' in violation_event


@pytest.mark.asyncio
async def test_publish_sla_violation_kafka_failure(
    mock_config, mock_kafka_producer, mock_metrics
):
    """Testa falha na publicação de violação."""
    mock_kafka_producer.publish_ticket = AsyncMock(side_effect=Exception("Kafka error"))

    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)

    violation = {
        'workflow_id': 'orch-333',
        'ticket_id': 'ticket-444',
        'violation_type': 'BUDGET_EXHAUSTED'
    }

    # Não deve lançar exceção (fail-open)
    await manager.publish_sla_violation(violation)

    mock_metrics.record_sla_monitor_error.assert_called_once_with('violation_publish')


@pytest.mark.asyncio
async def test_send_budget_alert(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics
):
    """Testa alerta específico de budget."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    budget_data = {
        'error_budget_remaining': 0.18,
        'status': 'CRITICAL',
        'burn_rates': [{'window_hours': 1, 'rate': 7.2}]
    }

    await manager.send_budget_alert('orch-555', 'orchestrator-dynamic', budget_data)

    mock_kafka_producer.publish_ticket.assert_called_once()

    call_args = mock_kafka_producer.publish_ticket.call_args
    alert_payload = call_args[1]['ticket']
    assert alert_payload['alert_type'] == 'BUDGET_CRITICAL'
    assert alert_payload['context']['service_name'] == 'orchestrator-dynamic'
    assert alert_payload['context']['budget_remaining'] == 0.18


@pytest.mark.asyncio
async def test_send_deadline_alert(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics
):
    """Testa alerta específico de deadline."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    deadline_data = {
        'remaining_seconds': 45,
        'percent_consumed': 0.82,
        'sla_deadline': int(datetime.now().timestamp() * 1000)
    }

    await manager.send_deadline_alert('orch-666', 'ticket-777', deadline_data)

    mock_kafka_producer.publish_ticket.assert_called_once()

    call_args = mock_kafka_producer.publish_ticket.call_args
    alert_payload = call_args[1]['ticket']
    assert alert_payload['alert_type'] == 'DEADLINE_APPROACHING'
    assert alert_payload['context']['ticket_id'] == 'ticket-777'
    assert alert_payload['context']['remaining_seconds'] == 45


@pytest.mark.asyncio
async def test_alert_deduplication_cache(
    mock_config, mock_kafka_producer, mock_redis, mock_metrics, budget_critical_context
):
    """Testa funcionamento do cache de deduplicação."""
    manager = AlertManager(mock_config, mock_kafka_producer, mock_metrics)
    manager.set_redis(mock_redis)

    # Primeiro envio - deve passar
    result1 = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)
    assert result1 is True

    # Simular cache hit
    mock_redis.get = AsyncMock(return_value="1")

    # Segundo envio - deve ser bloqueado
    result2 = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)
    assert result2 is False

    # Verificar que setex foi chamado apenas uma vez (no primeiro envio)
    assert mock_redis.setex.call_count == 1

    # Verificar que métrica de deduplicação foi registrada
    mock_metrics.record_sla_alert_deduplicated.assert_called_once()


@pytest.mark.asyncio
async def test_send_proactive_alert_producer_none(
    mock_config, mock_metrics, budget_critical_context
):
    """Testa comportamento quando producer é None."""
    manager = AlertManager(mock_config, None, mock_metrics)

    result = await manager.send_proactive_alert('BUDGET_CRITICAL', budget_critical_context)

    assert result is False
    mock_metrics.record_sla_monitor_error.assert_called_once_with('producer_not_initialized')


@pytest.mark.asyncio
async def test_publish_sla_violation_producer_none(
    mock_config, mock_metrics
):
    """Testa publicação de violação quando producer é None."""
    manager = AlertManager(mock_config, None, mock_metrics)

    violation = {
        'workflow_id': 'orch-999',
        'ticket_id': 'ticket-888',
        'violation_type': 'DEADLINE_EXCEEDED'
    }

    # Não deve lançar exceção
    await manager.publish_sla_violation(violation)

    mock_metrics.record_sla_monitor_error.assert_called_once_with('producer_not_initialized')
