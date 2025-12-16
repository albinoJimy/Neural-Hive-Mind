"""
Testes de validação das métricas OPA em runtime.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from src.policies import OPAClient, PolicyValidator
from src.policies.opa_client import OPAConnectionError
from src.observability.metrics import get_metrics

from .test_opa_real_server import real_opa_config, real_opa_client


@pytest.mark.asyncio
async def test_records_opa_validation_metrics(real_opa_client, real_opa_config):
    """Testa registro de opa_validations_total e duração."""
    metrics = get_metrics()
    validator = PolicyValidator(real_opa_client, real_opa_config)
    deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

    ticket = {
        'ticket_id': 'metrics-001',
        'tenant_id': 'tenant-1',
        'namespace': 'production',
        'risk_band': 'high',
        'sla': {'timeout_ms': 120000, 'deadline': deadline, 'max_retries': 2},
        'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
        'priority': 'HIGH',
        'required_capabilities': ['code_generation'],
        'estimated_duration_ms': 60000,
        'jwt_token': 'header.payload.signature',
        'user_id': 'user-dev'
    }

    before = metrics.opa_validations_total.labels(
        policy_name='neuralhive/orchestrator/resource_limits',
        result='allowed'
    )._value.get()

    before_sum = metrics.opa_validation_duration_seconds.labels(
        policy_name='neuralhive/orchestrator/resource_limits'
    )._sum.get()

    await validator.validate_execution_ticket(ticket)

    after = metrics.opa_validations_total.labels(
        policy_name='neuralhive/orchestrator/resource_limits',
        result='allowed'
    )._value.get()

    after_sum = metrics.opa_validation_duration_seconds.labels(
        policy_name='neuralhive/orchestrator/resource_limits'
    )._sum.get()

    assert after == before + 1
    assert after_sum > before_sum


@pytest.mark.asyncio
async def test_records_policy_rejections(real_opa_client, real_opa_config):
    """Testa registro de opa_policy_rejections_total."""
    metrics = get_metrics()
    validator = PolicyValidator(real_opa_client, real_opa_config)
    deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

    ticket = {
        'ticket_id': 'metrics-002',
        'tenant_id': 'tenant-1',
        'namespace': 'production',
        'risk_band': 'high',
        'sla': {'timeout_ms': 7200000, 'deadline': deadline, 'max_retries': 6},
        'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
        'priority': 'HIGH',
        'required_capabilities': ['code_generation'],
        'estimated_duration_ms': 60000,
        'jwt_token': 'header.payload.signature',
        'user_id': 'user-dev'
    }

    before = metrics.opa_policy_rejections_total.labels(
        policy_name='resource_limits',
        rule='timeout_exceeds_maximum',
        severity='high'
    )._value.get()

    await validator.validate_execution_ticket(ticket)

    after = metrics.opa_policy_rejections_total.labels(
        policy_name='resource_limits',
        rule='timeout_exceeds_maximum',
        severity='high'
    )._value.get()

    assert after == before + 1


@pytest.mark.asyncio
async def test_records_policy_warnings(real_opa_client, real_opa_config):
    """Testa registro de opa_policy_warnings_total."""
    metrics = get_metrics()
    validator = PolicyValidator(real_opa_client, real_opa_config)
    current_time = int(datetime.now().timestamp() * 1000)
    deadline = current_time + 4000

    ticket = {
        'ticket_id': 'metrics-003',
        'tenant_id': 'tenant-1',
        'namespace': 'production',
        'risk_band': 'high',
        'sla': {'timeout_ms': 30000, 'deadline': deadline, 'max_retries': 1},
        'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
        'priority': 'HIGH',
        'required_capabilities': ['code_generation'],
        'estimated_duration_ms': 10000,
        'jwt_token': 'header.payload.signature',
        'user_id': 'user-dev'
    }

    before = metrics.opa_policy_warnings_total.labels(
        policy_name='sla_enforcement',
        rule='deadline_approaching_threshold'
    )._value.get()

    await validator.validate_execution_ticket(ticket)

    after = metrics.opa_policy_warnings_total.labels(
        policy_name='sla_enforcement',
        rule='deadline_approaching_threshold'
    )._value.get()

    assert after == before + 1


@pytest.mark.asyncio
async def test_records_evaluation_errors(real_opa_config, monkeypatch):
    """Testa registro de opa_evaluation_errors_total em erro de conexão."""
    metrics = get_metrics()
    real_opa_config.opa_fail_open = False
    client = OPAClient(real_opa_config)
    await client.initialize()
    validator = PolicyValidator(client, real_opa_config)

    monkeypatch.setattr(
        client,
        'batch_evaluate',
        AsyncMock(side_effect=OPAConnectionError("Connection refused"))
    )

    ticket = {
        'ticket_id': 'metrics-004',
        'tenant_id': 'tenant-1',
        'namespace': 'production',
        'risk_band': 'low',
        'sla': {'timeout_ms': 60000, 'deadline': int((datetime.now() + timedelta(hours=1)).timestamp() * 1000), 'max_retries': 1},
        'qos': {'delivery_mode': 'AT_LEAST_ONCE', 'consistency': 'EVENTUAL'},
        'priority': 'LOW',
        'required_capabilities': ['testing'],
        'estimated_duration_ms': 10000
    }

    before = metrics.opa_evaluation_errors_total.labels(error_type='connection')._value.get()

    await validator.validate_execution_ticket(ticket)

    after = metrics.opa_evaluation_errors_total.labels(error_type='connection')._value.get()

    assert after == before + 1
    await client.close()


@pytest.mark.asyncio
async def test_circuit_breaker_state_opens_after_failures(real_opa_config, monkeypatch):
    """Testa mudança de estado do circuit breaker após falhas."""
    metrics = get_metrics()
    real_opa_config.opa_circuit_breaker_failure_threshold = 2
    real_opa_config.opa_fail_open = True
    client = OPAClient(real_opa_config)
    await client.initialize()

    async def failing_internal(*_, **__):
        raise OPAConnectionError("forced failure")

    monkeypatch.setattr(client, '_evaluate_policy_internal', AsyncMock(side_effect=failing_internal))

    gauge = metrics.opa_circuit_breaker_state.labels(circuit_name='opa_client')
    before = gauge._value.get()

    for _ in range(3):
        with pytest.raises(OPAConnectionError):
            await client.evaluate_policy('neuralhive/orchestrator/resource_limits', {'input': {}})

    after = gauge._value.get()

    assert after == 2  # open state
    assert after != before
    await client.close()


@pytest.mark.asyncio
async def test_cache_hits_increment(real_opa_client):
    """Testa incremento de opa_cache_hits_total em cache hit."""
    metrics = get_metrics()
    input_data = {
        "resource": {
            "ticket_id": "metrics-005",
            "risk_band": "medium",
            "sla": {"timeout_ms": 60000, "max_retries": 1},
            "estimated_duration_ms": 30000,
            "required_capabilities": ["testing"]
        },
        "parameters": {
            "allowed_capabilities": ["testing"],
            "max_concurrent_tickets": 50
        },
        "context": {
            "total_tickets": 10
        }
    }

    before = metrics.opa_cache_hits_total._value.get()

    await real_opa_client.evaluate_policy(
        'neuralhive/orchestrator/resource_limits',
        {'input': input_data}
    )
    await real_opa_client.evaluate_policy(
        'neuralhive/orchestrator/resource_limits',
        {'input': input_data}
    )

    after = metrics.opa_cache_hits_total._value.get()

    assert after == before + 1


@pytest.mark.asyncio
async def test_security_metrics_increment_on_violation(real_opa_client, real_opa_config):
    """Testa incremento de métricas de segurança."""
    metrics = get_metrics()
    validator = PolicyValidator(real_opa_client, real_opa_config)
    future_deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

    # Violação de cross-tenant access
    violation_before = metrics.security_violations_total.labels(
        tenant_id='test-tenant',
        violation_type='cross_tenant_access',
        severity='critical'
    )._value.get()

    cross_tenant_ticket = {
        'ticket_id': 'metrics-006',
        'tenant_id': 'test-tenant',
        'namespace': 'production',
        'risk_band': 'high',
        'sla': {'timeout_ms': 120000, 'deadline': future_deadline, 'max_retries': 1},
        'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
        'priority': 'HIGH',
        'required_capabilities': ['code_generation'],
        'estimated_duration_ms': 60000,
        'jwt_token': 'header.payload.signature',
        'user_id': 'user-dev'
    }

    await validator.validate_execution_ticket(cross_tenant_ticket)

    violation_after = metrics.security_violations_total.labels(
        tenant_id='test-tenant',
        violation_type='cross_tenant_access',
        severity='critical'
    )._value.get()

    assert violation_after == violation_before + 1

    # Violação de missing_authentication
    real_opa_config.opa_allowed_tenants.append('test-tenant')
    auth_before = metrics.security_authentication_failures_total.labels(
        tenant_id='test-tenant',
        reason='missing_authentication'
    )._value.get()

    missing_auth_ticket = {
        'ticket_id': 'metrics-007',
        'tenant_id': 'test-tenant',
        'namespace': 'production',
        'risk_band': 'medium',
        'sla': {'timeout_ms': 60000, 'deadline': future_deadline, 'max_retries': 1},
        'qos': {'delivery_mode': 'AT_LEAST_ONCE', 'consistency': 'STRONG'},
        'priority': 'NORMAL',
        'required_capabilities': ['testing'],
        'estimated_duration_ms': 30000,
        'user_id': 'user-dev'
    }

    await validator.validate_execution_ticket(missing_auth_ticket)

    auth_after = metrics.security_authentication_failures_total.labels(
        tenant_id='test-tenant',
        reason='missing_authentication'
    )._value.get()

    assert auth_after == auth_before + 1


@pytest.mark.asyncio
async def test_tenant_rate_limit_violation_with_redis(real_opa_client, real_opa_config):
    """Garante que violation de rate limit usa contagem real do Redis."""

    class FakeRedis:
        def __init__(self, value):
            self.value = value

        async def get(self, key):
            return str(self.value)

    validator = PolicyValidator(real_opa_client, real_opa_config, redis_client=FakeRedis(50))
    future_deadline = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)

    ticket = {
        'ticket_id': 'metrics-008',
        'tenant_id': 'tenant-1',
        'namespace': 'production',
        'risk_band': 'medium',
        'sla': {'timeout_ms': 60000, 'deadline': future_deadline, 'max_retries': 1},
        'qos': {'delivery_mode': 'AT_LEAST_ONCE', 'consistency': 'STRONG'},
        'priority': 'NORMAL',
        'required_capabilities': ['testing'],
        'estimated_duration_ms': 30000,
        'jwt_token': 'header.payload.signature',
        'user_id': 'user-dev'
    }

    result = await validator.validate_execution_ticket(ticket)

    assert result.valid is False
    assert any(v.rule == 'tenant_rate_limit_exceeded' for v in result.violations)
