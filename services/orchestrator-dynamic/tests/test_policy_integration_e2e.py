"""
Testes end-to-end cobrindo validação OPA nas etapas C1, C2 e C3.
"""
import pytest
from unittest.mock import AsyncMock, Mock

from src.activities.plan_validation import validate_cognitive_plan as validate_plan_activity
from src.activities.plan_validation import set_activity_dependencies as set_plan_deps
from src.activities.ticket_generation import (
    generate_execution_tickets,
    allocate_resources,
    set_activity_dependencies as set_ticket_deps
)
from src.policies.policy_validator import ValidationResult, PolicyViolation


def _reset_plan_dependencies():
    set_plan_deps(None, None)


def _reset_ticket_dependencies():
    set_ticket_deps(None, None, None, None, None, None, None)


def _base_plan():
    return {
        'plan_id': 'plan-1',
        'intent_id': 'intent-9',
        'decision_id': 'dec-7',
        'risk_score': 0.4,
        'risk_band': 'medium',
        'tasks': [
            {'task_id': 'task-1', 'task_type': 'EXECUTE', 'description': 'do something'},
            {'task_id': 'task-2', 'task_type': 'EXECUTE', 'description': 'do next', 'dependencies': ['task-1']}
        ],
        'execution_order': ['task-1', 'task-2']
    }


def _config(opa_enabled=True, fail_open=False):
    cfg = Mock()
    cfg.opa_enabled = opa_enabled
    cfg.opa_fail_open = fail_open
    return cfg


@pytest.mark.asyncio
async def test_orchestration_flow_c1_c2_c3_with_opa():
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(valid=True)
    policy_validator.validate_execution_ticket.return_value = ValidationResult(
        valid=True,
        policy_decisions={'feature_flags': {'enable_intelligent_scheduler': True}}
    )
    policy_validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    config = _config(opa_enabled=True, fail_open=False)

    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = {
            'agent_id': 'agent-e2e',
            'agent_type': 'worker-agent',
            'capacity': {'cpu': '1000m'},
            'allocation_method': 'intelligent_scheduler'
        }
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    set_plan_deps(policy_validator=policy_validator, config=config)
    plan_validation_result = await validate_plan_activity('plan-1', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-7'})
    allocated = await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()

    assert plan_validation_result['valid'] is True
    assert policy_validator.validate_cognitive_plan.called
    assert policy_validator.validate_execution_ticket.called
    assert policy_validator.validate_resource_allocation.called
    assert allocated['allocation_metadata']['agent_id'] == 'agent-e2e'


@pytest.mark.asyncio
async def test_orchestration_flow_c3_violation_blocks_allocation():
    violation = PolicyViolation(
        policy_name='resource_limits',
        rule='timeout_exceeds_maximum',
        message='timeout alto',
        severity='high'
    )
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(valid=True)
    policy_validator.validate_execution_ticket.return_value = ValidationResult(valid=True)
    policy_validator.validate_resource_allocation.return_value = ValidationResult(valid=False, violations=[violation])

    config = _config(opa_enabled=True, fail_open=False)
    scheduler = AsyncMock()
    scheduler.schedule_ticket.return_value = {'ticket_id': 'ticket-1', 'allocation_metadata': {'agent_id': 'agent-x'}}

    set_plan_deps(policy_validator=policy_validator, config=config)
    await validate_plan_activity('plan-1', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-7'})

    with pytest.raises(RuntimeError):
        await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_with_feature_flags():
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(valid=True)
    policy_validator.validate_execution_ticket.return_value = ValidationResult(
        valid=True,
        policy_decisions={'feature_flags': {'enable_intelligent_scheduler': True}}
    )
    policy_validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    config = _config(opa_enabled=True, fail_open=False)

    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = {'agent_id': 'agent-ff', 'agent_type': 'worker-agent'}
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    set_plan_deps(policy_validator=policy_validator, config=config)
    await validate_plan_activity('plan-ff', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-ff'})
    allocated = await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()

    assert allocated['allocation_metadata']['agent_id'] == 'agent-ff'
    policy_validator.validate_execution_ticket.assert_called()
    policy_validator.validate_resource_allocation.assert_called_once()


@pytest.mark.asyncio
async def test_orchestration_flow_opa_unavailable_fail_open():
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.side_effect = Exception('OPA down')
    policy_validator.validate_execution_ticket.side_effect = Exception('OPA down')
    policy_validator.validate_resource_allocation.side_effect = Exception('OPA down')

    config = _config(opa_enabled=True, fail_open=True)
    scheduler = AsyncMock()
    scheduler.schedule_ticket.return_value = {'ticket_id': 'ticket-1', 'allocation_metadata': {'agent_id': 'agent-y'}}

    set_plan_deps(policy_validator=policy_validator, config=config)
    plan_result = await validate_plan_activity('plan-1', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-7'})
    allocated = await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()

    assert plan_result['valid'] is True
    assert allocated['allocation_metadata']['agent_id'] == 'agent-y'
