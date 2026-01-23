"""
Testes de integração das activities com MongoDB (mockado).
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pymongo.errors import PyMongoError

from neural_hive_resilience.circuit_breaker import CircuitBreakerError
from src.activities import plan_validation, result_consolidation, ticket_generation


@pytest.fixture
def minimal_config():
    """Config mínima para desabilitar caminhos pesados."""
    config = Mock()
    config.ml_allocation_outcomes_enabled = False
    config.sla_management_enabled = False
    return config


@pytest.mark.asyncio
async def test_audit_validation_calls_mongodb(monkeypatch):
    """audit_validation deve chamar save_validation_audit com workflow_id."""
    mock_client = AsyncMock()
    plan_validation.set_activity_dependencies(policy_validator=None, config=None, mongodb_client=mock_client)

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-100'

    with patch('temporalio.activity.info', return_value=workflow_info):
        await plan_validation.audit_validation('plan-100', {'valid': True})

    mock_client.save_validation_audit.assert_awaited_once_with('plan-100', {'valid': True}, 'wf-100')


@pytest.mark.asyncio
async def test_audit_validation_without_mongodb_client(monkeypatch):
    """Sem MongoDB client a activity deve completar sem erro."""
    plan_validation.set_activity_dependencies(policy_validator=None, config=None, mongodb_client=None)

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-200'

    with patch('temporalio.activity.info', return_value=workflow_info):
        await plan_validation.audit_validation('plan-200', {'valid': False})


@pytest.mark.asyncio
async def test_audit_validation_mongodb_failure(monkeypatch):
    """Erros na persistência devem ser fail-open."""
    mock_client = AsyncMock()
    mock_client.save_validation_audit.side_effect = Exception('mongo unavailable')
    plan_validation.set_activity_dependencies(policy_validator=None, config=None, mongodb_client=mock_client)

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-210'

    with patch('temporalio.activity.info', return_value=workflow_info):
        await plan_validation.audit_validation('plan-210', {'valid': True})


@pytest.mark.asyncio
async def test_consolidate_results_saves_workflow_result(minimal_config):
    """consolidate_results deve persistir resultado consolidado."""
    mock_client = AsyncMock()
    result_consolidation.set_activity_dependencies(
        scheduling_optimizer=None,
        config=minimal_config,
        mongodb_client=mock_client
    )

    tickets = [{'ticket': {'status': 'COMPLETED', 'plan_id': 'p1', 'intent_id': 'i1', 'estimated_duration_ms': 10}}]
    await result_consolidation.consolidate_results(tickets, 'wf-300')

    mock_client.save_workflow_result.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_self_healing_saves_incident(minimal_config):
    """trigger_self_healing deve persistir incidente via MongoDB."""
    mock_client = AsyncMock()
    result_consolidation.set_activity_dependencies(
        scheduling_optimizer=None,
        config=minimal_config,
        mongodb_client=mock_client
    )

    await result_consolidation.trigger_self_healing('wf-400', ['err'])

    mock_client.save_incident.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_self_healing_fail_open(minimal_config):
    """Persistência com erro não deve lançar exceção."""
    mock_client = AsyncMock()
    mock_client.save_incident.side_effect = Exception('mongo down')
    result_consolidation.set_activity_dependencies(
        scheduling_optimizer=None,
        config=minimal_config,
        mongodb_client=mock_client
    )

    await result_consolidation.trigger_self_healing('wf-410', ['err'])


@pytest.mark.asyncio
async def test_buffer_telemetry_saves_to_mongodb(minimal_config):
    """buffer_telemetry deve salvar frame no buffer MongoDB."""
    mock_client = AsyncMock()
    result_consolidation.set_activity_dependencies(
        scheduling_optimizer=None,
        config=minimal_config,
        mongodb_client=mock_client
    )

    await result_consolidation.buffer_telemetry({'correlation': {'workflow_id': 'wf-500'}})

    mock_client.save_telemetry_buffer.assert_awaited_once()


@pytest.mark.asyncio
async def test_buffer_telemetry_fail_open(minimal_config):
    """Erros na persistência do buffer não devem quebrar a activity."""
    mock_client = AsyncMock()
    mock_client.save_telemetry_buffer.side_effect = Exception('mongo down')
    result_consolidation.set_activity_dependencies(
        scheduling_optimizer=None,
        config=minimal_config,
        mongodb_client=mock_client
    )

    await result_consolidation.buffer_telemetry({'correlation': {'workflow_id': 'wf-510'}})


@pytest.mark.asyncio
async def test_consolidate_results_fail_open_on_mongodb_error(minimal_config):
    """Falha na persistência não deve quebrar consolidate_results."""
    mock_client = AsyncMock()
    mock_client.save_workflow_result.side_effect = Exception('mongo down')

    result_consolidation.set_activity_dependencies(
        scheduling_optimizer=None,
        config=minimal_config,
        mongodb_client=mock_client
    )

    tickets = [{'ticket': {'status': 'FAILED', 'plan_id': 'p2', 'intent_id': 'i2', 'estimated_duration_ms': 5}}]
    result = await result_consolidation.consolidate_results(tickets, 'wf-600')

    assert result['workflow_id'] == 'wf-600'


# ======================================================
# Testes de integração para publish_ticket_to_kafka com falhas MongoDB
# ======================================================

@pytest.fixture
def mock_kafka_producer():
    """Kafka producer mockado com sucesso."""
    producer = AsyncMock()
    producer.publish_ticket = AsyncMock(return_value={
        'topic': 'execution.tickets',
        'partition': 0,
        'offset': 123,
        'timestamp': 1700000000
    })
    return producer


@pytest.fixture
def config_fail_open_disabled():
    """Config com MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False."""
    config = Mock()
    config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = False
    return config


@pytest.fixture
def config_fail_open_enabled():
    """Config com MONGODB_FAIL_OPEN_EXECUTION_TICKETS=True."""
    config = Mock()
    config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = True
    return config


@pytest.fixture
def valid_ticket():
    """Ticket válido para testes."""
    return {
        'ticket_id': 'ticket-mongo-test-1',
        'plan_id': 'plan-1',
        'intent_id': 'intent-1',
        'status': 'PENDING',
        'allocation_metadata': {
            'agent_id': 'worker-1',
            'allocated_at': 1700000000
        },
        'metadata': {}
    }


@pytest.mark.asyncio
async def test_publish_ticket_mongodb_failure_propagates_when_fail_open_disabled(
    mock_kafka_producer, config_fail_open_disabled, valid_ticket
):
    """publish_ticket_to_kafka deve propagar erro quando MONGODB_FAIL_OPEN_EXECUTION_TICKETS=False."""
    mock_mongodb = AsyncMock()
    mock_mongodb.save_execution_ticket.side_effect = PyMongoError('Connection refused')

    ticket_generation.set_activity_dependencies(
        kafka_producer=mock_kafka_producer,
        mongodb_client=mock_mongodb,
        config=config_fail_open_disabled
    )

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-mongo-fail-1'

    with patch('temporalio.activity.info', return_value=workflow_info):
        with patch('temporalio.activity.logger', Mock()):
            with pytest.raises(RuntimeError, match='Falha crítica na persistência'):
                await ticket_generation.publish_ticket_to_kafka(valid_ticket)

    # Kafka publish deve ter sido chamado antes do erro de persistência
    mock_kafka_producer.publish_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_ticket_mongodb_failure_degrades_when_fail_open_enabled(
    mock_kafka_producer, config_fail_open_enabled, valid_ticket
):
    """publish_ticket_to_kafka deve degradar (continuar) quando MONGODB_FAIL_OPEN_EXECUTION_TICKETS=True."""
    mock_mongodb = AsyncMock()
    mock_mongodb.save_execution_ticket.side_effect = PyMongoError('Connection refused')

    ticket_generation.set_activity_dependencies(
        kafka_producer=mock_kafka_producer,
        mongodb_client=mock_mongodb,
        config=config_fail_open_enabled
    )

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-mongo-fail-2'

    with patch('temporalio.activity.info', return_value=workflow_info):
        with patch('temporalio.activity.logger', Mock()):
            result = await ticket_generation.publish_ticket_to_kafka(valid_ticket)

    # Deve retornar sucesso (publicado no Kafka) apesar do erro MongoDB
    assert result['published'] is True
    assert result['ticket_id'] == valid_ticket['ticket_id']
    mock_kafka_producer.publish_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_ticket_circuit_breaker_open_degrades_gracefully(
    mock_kafka_producer, config_fail_open_disabled, valid_ticket
):
    """publish_ticket_to_kafka deve degradar quando circuit breaker está aberto."""
    mock_mongodb = AsyncMock()
    mock_mongodb.save_execution_ticket.side_effect = CircuitBreakerError('Circuit open')

    ticket_generation.set_activity_dependencies(
        kafka_producer=mock_kafka_producer,
        mongodb_client=mock_mongodb,
        config=config_fail_open_disabled
    )

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-circuit-open-1'

    with patch('temporalio.activity.info', return_value=workflow_info):
        with patch('temporalio.activity.logger', Mock()):
            # CircuitBreakerError não deve propagar, apenas logar warning
            result = await ticket_generation.publish_ticket_to_kafka(valid_ticket)

    # Deve retornar sucesso (publicado no Kafka) apesar do circuit breaker
    assert result['published'] is True
    assert result['ticket_id'] == valid_ticket['ticket_id']
    mock_kafka_producer.publish_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_ticket_mongodb_success_path(
    mock_kafka_producer, config_fail_open_disabled, valid_ticket
):
    """publish_ticket_to_kafka deve completar com sucesso quando MongoDB está ok."""
    mock_mongodb = AsyncMock()
    mock_mongodb.save_execution_ticket = AsyncMock(return_value=None)

    ticket_generation.set_activity_dependencies(
        kafka_producer=mock_kafka_producer,
        mongodb_client=mock_mongodb,
        config=config_fail_open_disabled
    )

    workflow_info = Mock()
    workflow_info.workflow_id = 'wf-success-1'

    with patch('temporalio.activity.info', return_value=workflow_info):
        with patch('temporalio.activity.logger', Mock()):
            result = await ticket_generation.publish_ticket_to_kafka(valid_ticket)

    assert result['published'] is True
    assert result['ticket_id'] == valid_ticket['ticket_id']
    mock_kafka_producer.publish_ticket.assert_awaited_once()
    mock_mongodb.save_execution_ticket.assert_awaited_once()
