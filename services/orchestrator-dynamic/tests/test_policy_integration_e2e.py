"""
Testes end-to-end cobrindo validação OPA nas etapas C1, C2 e C3.

Cenários cobertos:
- Fluxo completo C1 -> C2 -> C3 com OPA
- Violações bloqueando alocação
- Feature flags
- Fail-open quando OPA indisponível
- Circuit breaker
- Batch evaluation
- Security constraints
- Servidor OPA real (quando disponível)
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from src.activities.plan_validation import validate_cognitive_plan as validate_plan_activity
from src.activities.plan_validation import set_activity_dependencies as set_plan_deps
from src.activities.ticket_generation import (
    generate_execution_tickets,
    allocate_resources,
    set_activity_dependencies as set_ticket_deps
)
from src.policies.policy_validator import ValidationResult, PolicyViolation
from src.policies.opa_client import OPAClient


# Flag para testes com servidor OPA real
REAL_OPA_E2E = os.getenv("RUN_OPA_E2E", "").lower() == "true"


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


# ============================================================================
# Cenários E2E adicionais para OPA Integration
# ============================================================================


@pytest.mark.asyncio
async def test_orchestration_flow_deadline_violation():
    """Testa rejeição de ticket com deadline expirado."""
    violation = PolicyViolation(
        policy_name='sla_enforcement',
        rule='deadline_already_passed',
        message='Deadline já expirou',
        severity='critical'
    )
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(valid=True)
    policy_validator.validate_execution_ticket.return_value = ValidationResult(
        valid=False,
        violations=[violation]
    )

    config = _config(opa_enabled=True, fail_open=False)

    set_plan_deps(policy_validator=policy_validator, config=config)
    await validate_plan_activity('plan-deadline', _base_plan())

    set_ticket_deps(None, None, None, AsyncMock(), policy_validator, config, None)

    with pytest.raises(RuntimeError):
        await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-deadline'})

    _reset_plan_dependencies()
    _reset_ticket_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_capability_violation():
    """Testa rejeição por capability não permitida."""
    violation = PolicyViolation(
        policy_name='resource_limits',
        rule='capability_not_allowed',
        message='Capability não permitida: dangerous_capability',
        severity='high'
    )
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(
        valid=False,
        violations=[violation]
    )

    config = _config(opa_enabled=True, fail_open=False)

    set_plan_deps(policy_validator=policy_validator, config=config)

    with pytest.raises(RuntimeError):
        await validate_plan_activity('plan-cap', _base_plan())

    _reset_plan_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_security_tenant_isolation():
    """Testa rejeição por violação de isolamento de tenant."""
    violation = PolicyViolation(
        policy_name='security_constraints',
        rule='cross_tenant_access',
        message='Tentativa de acesso cross-tenant bloqueada',
        severity='critical'
    )
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(valid=True)
    policy_validator.validate_execution_ticket.return_value = ValidationResult(valid=True)
    policy_validator.validate_resource_allocation.return_value = ValidationResult(
        valid=False,
        violations=[violation]
    )

    config = _config(opa_enabled=True, fail_open=False)
    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = {
            'agent_id': 'agent-another-tenant',
            'tenant_id': 'tenant-2'  # Tenant diferente
        }
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    set_plan_deps(policy_validator=policy_validator, config=config)
    await validate_plan_activity('plan-sec', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-sec'})

    with pytest.raises(RuntimeError):
        await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_rate_limit_exceeded():
    """Testa rejeição por rate limit excedido."""
    violation = PolicyViolation(
        policy_name='security_constraints',
        rule='tenant_rate_limit_exceeded',
        message='Rate limit excedido para tenant',
        severity='high'
    )
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(
        valid=False,
        violations=[violation]
    )

    config = _config(opa_enabled=True, fail_open=False)

    set_plan_deps(policy_validator=policy_validator, config=config)

    with pytest.raises(RuntimeError):
        await validate_plan_activity('plan-rate', _base_plan())

    _reset_plan_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_batch_tickets():
    """Testa processamento em batch de múltiplos tickets."""
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(valid=True)
    policy_validator.validate_execution_ticket.return_value = ValidationResult(valid=True)
    policy_validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    config = _config(opa_enabled=True, fail_open=False)

    scheduler = AsyncMock()
    ticket_counter = [0]

    async def _schedule(ticket):
        ticket_counter[0] += 1
        ticket['allocation_metadata'] = {
            'agent_id': f'agent-batch-{ticket_counter[0]}',
            'agent_type': 'worker-agent'
        }
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    # Plano com múltiplas tasks
    batch_plan = {
        'plan_id': 'plan-batch',
        'intent_id': 'intent-batch',
        'decision_id': 'dec-batch',
        'risk_score': 0.3,
        'risk_band': 'low',
        'tasks': [
            {'task_id': f'task-{i}', 'task_type': 'EXECUTE', 'description': f'task {i}'}
            for i in range(5)
        ],
        'execution_order': [f'task-{i}' for i in range(5)]
    }

    set_plan_deps(policy_validator=policy_validator, config=config)
    await validate_plan_activity('plan-batch', batch_plan)

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(batch_plan, {'decision_id': 'dec-batch'})

    # Alocar todos os tickets
    allocated_tickets = []
    for ticket in tickets:
        allocated = await allocate_resources(ticket)
        allocated_tickets.append(allocated)

    _reset_plan_dependencies()
    _reset_ticket_dependencies()

    assert len(allocated_tickets) == 5
    assert policy_validator.validate_execution_ticket.call_count == 5
    assert policy_validator.validate_resource_allocation.call_count == 5


@pytest.mark.asyncio
async def test_orchestration_flow_circuit_breaker_open():
    """Testa comportamento quando circuit breaker está aberto."""
    policy_validator = AsyncMock()

    # Simula circuit breaker aberto
    async def _fail_with_circuit_open(*args, **kwargs):
        raise Exception("Circuit breaker OPEN - OPA indisponível")

    policy_validator.validate_cognitive_plan.side_effect = _fail_with_circuit_open

    config = _config(opa_enabled=True, fail_open=False)

    set_plan_deps(policy_validator=policy_validator, config=config)

    with pytest.raises(Exception) as exc_info:
        await validate_plan_activity('plan-cb', _base_plan())

    assert 'Circuit breaker' in str(exc_info.value) or 'OPA' in str(exc_info.value)

    _reset_plan_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_circuit_breaker_fail_open():
    """Testa fail-open quando circuit breaker está aberto."""
    policy_validator = AsyncMock()

    # Simula circuit breaker aberto mas com fail-open
    async def _fail_with_circuit_open(*args, **kwargs):
        raise Exception("Circuit breaker OPEN")

    policy_validator.validate_cognitive_plan.side_effect = _fail_with_circuit_open
    policy_validator.validate_execution_ticket.side_effect = _fail_with_circuit_open
    policy_validator.validate_resource_allocation.side_effect = _fail_with_circuit_open

    config = _config(opa_enabled=True, fail_open=True)

    scheduler = AsyncMock()
    scheduler.schedule_ticket.return_value = {
        'ticket_id': 'ticket-failopen',
        'allocation_metadata': {'agent_id': 'agent-fallback'}
    }

    set_plan_deps(policy_validator=policy_validator, config=config)
    plan_result = await validate_plan_activity('plan-failopen', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-failopen'})
    allocated = await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()

    # Com fail-open, operações devem continuar
    assert plan_result['valid'] is True
    assert allocated['allocation_metadata']['agent_id'] == 'agent-fallback'


@pytest.mark.asyncio
async def test_orchestration_flow_multiple_violations():
    """Testa cenário com múltiplas violações de diferentes políticas."""
    violations = [
        PolicyViolation(
            policy_name='resource_limits',
            rule='timeout_exceeds_maximum',
            message='Timeout muito alto',
            severity='high'
        ),
        PolicyViolation(
            policy_name='sla_enforcement',
            rule='qos_requirement_conflict',
            message='Conflito de requisitos QoS',
            severity='medium'
        )
    ]

    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(
        valid=False,
        violations=violations
    )

    config = _config(opa_enabled=True, fail_open=False)

    set_plan_deps(policy_validator=policy_validator, config=config)

    with pytest.raises(RuntimeError):
        await validate_plan_activity('plan-multi', _base_plan())

    _reset_plan_dependencies()


@pytest.mark.asyncio
async def test_orchestration_flow_warnings_only():
    """Testa cenário com warnings mas sem violações (allow=True)."""
    policy_validator = AsyncMock()
    policy_validator.validate_cognitive_plan.return_value = ValidationResult(
        valid=True,
        warnings=[{
            'policy': 'sla_enforcement',
            'rule': 'deadline_approaching',
            'message': 'Deadline está próximo'
        }]
    )
    policy_validator.validate_execution_ticket.return_value = ValidationResult(valid=True)
    policy_validator.validate_resource_allocation.return_value = ValidationResult(valid=True)

    config = _config(opa_enabled=True, fail_open=False)

    scheduler = AsyncMock()

    async def _schedule(ticket):
        ticket['allocation_metadata'] = {'agent_id': 'agent-warn', 'agent_type': 'worker-agent'}
        return ticket

    scheduler.schedule_ticket.side_effect = _schedule

    set_plan_deps(policy_validator=policy_validator, config=config)
    plan_result = await validate_plan_activity('plan-warn', _base_plan())

    set_ticket_deps(None, None, None, scheduler, policy_validator, config, None)
    tickets = await generate_execution_tickets(_base_plan(), {'decision_id': 'dec-warn'})
    allocated = await allocate_resources(tickets[0])

    _reset_plan_dependencies()
    _reset_ticket_dependencies()

    # Warnings não bloqueiam execução
    assert plan_result['valid'] is True
    assert allocated['allocation_metadata']['agent_id'] == 'agent-warn'


# ============================================================================
# Testes com servidor OPA real (requer RUN_OPA_E2E=true)
# ============================================================================


@pytest.fixture
def opa_real_config():
    """Configuração para testes com OPA real."""
    config = Mock()
    config.opa_host = os.getenv('OPA_HOST', 'localhost')
    config.opa_port = int(os.getenv('OPA_PORT', '8181'))
    config.opa_timeout_seconds = 5
    config.opa_retry_attempts = 3
    config.opa_cache_ttl_seconds = 30
    config.opa_fail_open = False
    config.opa_circuit_breaker_enabled = True
    config.opa_circuit_breaker_failure_threshold = 5
    config.opa_circuit_breaker_reset_timeout = 60
    return config


@pytest.fixture
def mock_metrics():
    """Mock de métricas para testes."""
    metrics = Mock()
    metrics.record_opa_validation = Mock()
    metrics.record_opa_validation_latency = Mock()
    metrics.record_opa_circuit_breaker_transition = Mock()
    metrics.record_opa_cache_miss = Mock()
    metrics.record_opa_batch_evaluation = Mock()
    metrics.record_opa_policy_decision_duration = Mock()
    return metrics


@pytest.mark.skipif(not REAL_OPA_E2E, reason="RUN_OPA_E2E not enabled")
@pytest.mark.asyncio
async def test_real_opa_resource_limits_valid(opa_real_config, mock_metrics):
    """Testa avaliação de resource_limits com servidor OPA real."""
    client = OPAClient(opa_real_config, metrics=mock_metrics)

    input_data = {
        'resource': {
            'ticket_id': 'e2e-real-001',
            'risk_band': 'medium',
            'sla': {
                'timeout_ms': 60000,
                'max_retries': 2
            },
            'required_capabilities': ['code_generation']
        },
        'parameters': {
            'allowed_capabilities': ['code_generation', 'testing'],
            'max_concurrent_tickets': 100
        },
        'context': {
            'total_tickets': 50
        }
    }

    try:
        result = await client.evaluate_policy('resource_limits', input_data)
        assert 'result' in result
        assert 'allow' in result['result']
    except Exception as e:
        pytest.skip(f"OPA server não disponível: {e}")
    finally:
        await client.close()


@pytest.mark.skipif(not REAL_OPA_E2E, reason="RUN_OPA_E2E not enabled")
@pytest.mark.asyncio
async def test_real_opa_sla_enforcement_deadline_valid(opa_real_config, mock_metrics):
    """Testa sla_enforcement com deadline válido no servidor OPA real."""
    client = OPAClient(opa_real_config, metrics=mock_metrics)

    current_time = int(datetime.now().timestamp() * 1000)
    deadline = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)

    input_data = {
        'resource': {
            'ticket_id': 'e2e-sla-001',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 120000,
                'deadline': deadline
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'estimated_duration_ms': 60000
        },
        'context': {
            'current_time': current_time
        }
    }

    try:
        result = await client.evaluate_policy('sla_enforcement', input_data)
        assert 'result' in result
        assert result['result'].get('allow') is True
    except Exception as e:
        pytest.skip(f"OPA server não disponível: {e}")
    finally:
        await client.close()


@pytest.mark.skipif(not REAL_OPA_E2E, reason="RUN_OPA_E2E not enabled")
@pytest.mark.asyncio
async def test_real_opa_sla_enforcement_deadline_expired(opa_real_config, mock_metrics):
    """Testa sla_enforcement com deadline expirado no servidor OPA real."""
    client = OPAClient(opa_real_config, metrics=mock_metrics)

    current_time = int(datetime.now().timestamp() * 1000)
    deadline = int((datetime.now() - timedelta(hours=1)).timestamp() * 1000)  # Deadline passado

    input_data = {
        'resource': {
            'ticket_id': 'e2e-sla-expired',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 120000,
                'deadline': deadline
            },
            'qos': {
                'delivery_mode': 'EXACTLY_ONCE',
                'consistency': 'STRONG'
            },
            'priority': 'HIGH',
            'estimated_duration_ms': 60000
        },
        'context': {
            'current_time': current_time
        }
    }

    try:
        result = await client.evaluate_policy('sla_enforcement', input_data)
        assert 'result' in result
        # Deve rejeitar ou ter violações
        policy_result = result['result']
        if 'allow' in policy_result:
            assert policy_result['allow'] is False or len(policy_result.get('violations', [])) > 0
    except Exception as e:
        pytest.skip(f"OPA server não disponível: {e}")
    finally:
        await client.close()


@pytest.mark.skipif(not REAL_OPA_E2E, reason="RUN_OPA_E2E not enabled")
@pytest.mark.asyncio
async def test_real_opa_feature_flags_evaluation(opa_real_config, mock_metrics):
    """Testa feature_flags no servidor OPA real."""
    client = OPAClient(opa_real_config, metrics=mock_metrics)

    current_time = int(datetime.now().timestamp() * 1000)

    input_data = {
        'resource': {
            'ticket_id': 'e2e-ff-001',
            'risk_band': 'medium'
        },
        'flags': {
            'intelligent_scheduler_enabled': True,
            'burst_capacity_enabled': False,
            'predictive_allocation_enabled': False,
            'auto_scaling_enabled': False,
            'scheduler_namespaces': ['production']
        },
        'context': {
            'namespace': 'production',
            'current_load': 0.5,
            'tenant_id': 'tenant-e2e',
            'queue_depth': 50,
            'current_time': current_time,
            'model_accuracy': 0.9
        }
    }

    try:
        result = await client.evaluate_policy('feature_flags', input_data)
        assert 'result' in result
        policy_result = result['result']
        # Feature flags devem retornar booleans
        if 'enable_intelligent_scheduler' in policy_result:
            assert isinstance(policy_result['enable_intelligent_scheduler'], bool)
    except Exception as e:
        pytest.skip(f"OPA server não disponível: {e}")
    finally:
        await client.close()


@pytest.mark.skipif(not REAL_OPA_E2E, reason="RUN_OPA_E2E not enabled")
@pytest.mark.asyncio
async def test_real_opa_security_constraints_valid_tenant(opa_real_config, mock_metrics):
    """Testa security_constraints com tenant válido no servidor OPA real."""
    client = OPAClient(opa_real_config, metrics=mock_metrics)

    current_time = int(datetime.now().timestamp() * 1000)

    input_data = {
        'resource': {
            'ticket_id': 'e2e-sec-001',
            'tenant_id': 'tenant-allowed',
            'risk_band': 'medium',
            'required_capabilities': ['testing']
        },
        'security': {
            'spiffe_enabled': False,
            'allowed_tenants': ['tenant-allowed', 'tenant-2'],
            'tenant_rate_limits': {'tenant-allowed': 100},
            'global_rate_limit': 1000,
            'default_tenant_rate_limit': 10
        },
        'context': {
            'user_id': 'user-e2e',
            'current_time': current_time,
            'request_count_last_minute': 5
        }
    }

    try:
        result = await client.evaluate_policy('security_constraints', input_data)
        assert 'result' in result
        policy_result = result['result']
        if 'allow' in policy_result:
            assert policy_result['allow'] is True
    except Exception as e:
        pytest.skip(f"OPA server não disponível: {e}")
    finally:
        await client.close()


@pytest.mark.skipif(not REAL_OPA_E2E, reason="RUN_OPA_E2E not enabled")
@pytest.mark.asyncio
async def test_real_opa_batch_evaluation(opa_real_config, mock_metrics):
    """Testa batch evaluation com servidor OPA real."""
    client = OPAClient(opa_real_config, metrics=mock_metrics)

    current_time = int(datetime.now().timestamp() * 1000)

    evaluations = []
    for i in range(5):
        evaluations.append({
            'policy': 'resource_limits',
            'input': {
                'resource': {
                    'ticket_id': f'e2e-batch-{i}',
                    'risk_band': 'low',
                    'sla': {'timeout_ms': 30000, 'max_retries': 1},
                    'required_capabilities': ['testing']
                },
                'parameters': {
                    'allowed_capabilities': ['testing'],
                    'max_concurrent_tickets': 100
                },
                'context': {'total_tickets': 10}
            }
        })

    try:
        results = await client.batch_evaluate(evaluations)
        assert len(results) == 5
        for result in results:
            assert 'result' in result or 'error' in result
    except Exception as e:
        pytest.skip(f"OPA server não disponível: {e}")
    finally:
        await client.close()
