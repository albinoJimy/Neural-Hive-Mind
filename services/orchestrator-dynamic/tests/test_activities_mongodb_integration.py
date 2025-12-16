"""
Testes de integração das activities com MongoDB (mockado).
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.activities import plan_validation, result_consolidation


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
