"""
Testes de integração da validação OPA (C3) na alocação de recursos.
"""
import pytest
from unittest.mock import AsyncMock, Mock

from src.activities.ticket_generation import allocate_resources, set_activity_dependencies
from src.policies.policy_validator import ValidationResult, PolicyViolation, PolicyWarning


@pytest.fixture
def sample_ticket():
    return {
        'ticket_id': 'ticket-123',
        'plan_id': 'plan-1',
        'sla': {'timeout_ms': 60000},
        'required_capabilities': ['code_generation'],
        'metadata': {}
    }


@pytest.fixture
def sample_allocation_metadata():
    return {
        'agent_id': 'agent-42',
        'agent_type': 'worker-agent',
        'capacity': {'cpu': '500m', 'memory': '512Mi'},
        'allocation_method': 'intelligent_scheduler'
    }


@pytest.fixture
def mock_config():
    cfg = Mock()
    cfg.opa_enabled = True
    cfg.opa_fail_open = False
    return cfg


@pytest.fixture
def mock_config_fail_open(mock_config):
    cfg = Mock()
    cfg.opa_enabled = True
    cfg.opa_fail_open = True
    return cfg


@pytest.fixture
def mock_scheduler(sample_allocation_metadata):
    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = dict(sample_allocation_metadata)
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule
    return scheduler


@pytest.fixture
def policy_result_ok():
    return ValidationResult(valid=True, policy_decisions={'resource_limits': {'allow': True}})


@pytest.fixture
def policy_result_warning():
    return ValidationResult(
        valid=True,
        warnings=[PolicyWarning(policy_name='resource_limits', rule='soft_limit', message='near limit')],
        policy_decisions={'resource_limits': {'allow': True, 'warnings': ['soft_limit']}}
    )


def _reset_dependencies():
    set_activity_dependencies(None, None, None, None, None, None, None)


@pytest.mark.asyncio
async def test_c3_validation_success(sample_ticket, mock_scheduler, policy_result_ok, mock_config):
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = policy_result_ok

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    ticket = await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    assert ticket['allocation_metadata']['agent_id'] == 'agent-42'
    validator.validate_resource_allocation.assert_called_once()
    assert 'policy_validated_at' in ticket['metadata']


@pytest.mark.asyncio
async def test_c3_validation_with_warnings(sample_ticket, mock_scheduler, policy_result_warning, mock_config):
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = policy_result_warning

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    ticket = await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    # Formato simplificado nos mocks (policy_path real pode ser usado em produção)
    assert ticket['metadata']['policy_decisions']['resource_limits']['allow'] is True
    assert 'policy_validated_at' in ticket['metadata']


@pytest.mark.asyncio
async def test_c3_validation_disabled(sample_ticket, mock_scheduler, policy_result_ok):
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = policy_result_ok
    config = Mock()
    config.opa_enabled = False
    config.opa_fail_open = False

    set_activity_dependencies(None, None, None, mock_scheduler, validator, config, None)
    ticket = await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    validator.validate_resource_allocation.assert_not_called()
    assert ticket['allocation_metadata']['agent_id'] == 'agent-42'


@pytest.mark.asyncio
async def test_c3_validation_violation_blocks_allocation(sample_ticket, mock_scheduler, mock_config):
    violation = PolicyViolation(
        policy_name='resource_limits',
        rule='timeout_exceeds_maximum',
        message='timeout too high',
        severity='high'
    )
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=False, violations=[violation])

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()


@pytest.mark.asyncio
async def test_c3_validation_timeout_exceeds_maximum(sample_ticket, mock_scheduler, mock_config):
    violation = PolicyViolation(
        policy_name='resource_limits',
        rule='timeout_exceeds_maximum',
        message='timeout excede limite',
        severity='high'
    )
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=False, violations=[violation])

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()


@pytest.mark.asyncio
async def test_c3_validation_capabilities_not_allowed(sample_ticket, mock_scheduler, mock_config):
    violation = PolicyViolation(
        policy_name='resource_limits',
        rule='capabilities_not_allowed',
        message='capability não permitida',
        severity='critical'
    )
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=False, violations=[violation])

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()


@pytest.mark.asyncio
async def test_c3_validation_concurrent_tickets_limit(sample_ticket, mock_scheduler, mock_config):
    violation = PolicyViolation(
        policy_name='resource_limits',
        rule='concurrent_tickets_limit',
        message='limite excedido',
        severity='high'
    )
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=False, violations=[violation])

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()


@pytest.mark.asyncio
async def test_c3_validation_fail_open_on_opa_error(sample_ticket, mock_scheduler, mock_config_fail_open):
    validator = AsyncMock()
    validator.validate_resource_allocation.side_effect = Exception('OPA unavailable')

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config_fail_open, None)
    ticket = await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    assert ticket['allocation_metadata']['agent_id'] == 'agent-42'


@pytest.mark.asyncio
async def test_c3_validation_fail_closed_on_opa_error(sample_ticket, mock_scheduler, mock_config):
    validator = AsyncMock()
    validator.validate_resource_allocation.side_effect = Exception('OPA down')

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()


@pytest.mark.asyncio
async def test_c3_validation_metadata_added_to_ticket(sample_ticket, mock_scheduler, policy_result_ok, mock_config):
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = policy_result_ok

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    ticket = await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    assert 'policy_decisions' in ticket['metadata']
    assert ticket['metadata']['policy_decisions']['resource_limits']['allow'] is True


@pytest.mark.asyncio
async def test_c3_validation_metrics_recorded(sample_ticket, mock_scheduler, mock_config):
    decisions = {'resource_limits': {'allow': True, 'evaluated': True}}
    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=True, policy_decisions=decisions)

    set_activity_dependencies(None, None, None, mock_scheduler, validator, mock_config, None)
    ticket = await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    assert ticket['metadata']['policy_decisions']['resource_limits']['evaluated'] is True


@pytest.mark.asyncio
async def test_c3_validation_agent_info_extraction(sample_ticket, sample_allocation_metadata, mock_config):
    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = dict(sample_allocation_metadata)
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    set_activity_dependencies(None, None, None, scheduler, validator, mock_config, None)
    await allocate_resources(dict(sample_ticket))
    _reset_dependencies()

    called_args = validator.validate_resource_allocation.call_args[0][1]
    assert called_args['agent_id'] == 'agent-42'
    assert called_args['capacity']['cpu'] == '500m'


@pytest.mark.asyncio
async def test_c3_validation_missing_allocation_metadata(sample_ticket, mock_config):
    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket.pop('allocation_metadata', None)
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    set_activity_dependencies(None, None, None, scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()


@pytest.mark.asyncio
async def test_c3_validation_invalid_agent_info(sample_ticket, mock_config):
    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = {'agent_type': 'worker-agent'}
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    validator = AsyncMock()
    validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    set_activity_dependencies(None, None, None, scheduler, validator, mock_config, None)
    with pytest.raises(RuntimeError):
        await allocate_resources(dict(sample_ticket))
    _reset_dependencies()
