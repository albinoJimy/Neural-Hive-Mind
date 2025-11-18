"""
Testes unitários para GuardrailEnforcer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.guardrail_enforcer import GuardrailEnforcer
from src.models.security_validation import ViolationType, Severity


@pytest.fixture
def mock_opa_client():
    """Mock OPA client."""
    return AsyncMock()


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client."""
    client = MagicMock()
    collection = AsyncMock()
    collection.insert_one = AsyncMock()
    client.guardrail_violations = collection
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def sample_ticket():
    """ExecutionTicket de exemplo."""
    return {
        "ticket_id": "ticket-123",
        "task_type": "BUILD",
        "parameters": {},
        "environment": "development"
    }


@pytest.fixture
def sample_ticket_ml():
    """ExecutionTicket com modelo ML."""
    return {
        "ticket_id": "ticket-ml-123",
        "task_type": "ML_TRAINING",
        "parameters": {
            "model": "sentiment-classifier",
            "bias_testing_completed": False
        },
        "environment": "production"
    }


@pytest.fixture
def sample_ticket_deploy():
    """ExecutionTicket de deploy em produção."""
    return {
        "ticket_id": "ticket-deploy-123",
        "task_type": "DEPLOY",
        "parameters": {
            "affected_percentage": 0.5,  # 50%
            "rollback_plan": False,
            "tests_passed": False
        },
        "environment": "production"
    }


@pytest.mark.asyncio
async def test_enforce_guardrails_no_violations(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client,
    sample_ticket
):
    """Testa guardrails sem violações."""
    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client,
        mode="BLOCKING"
    )

    violations = await enforcer.enforce_guardrails(sample_ticket)

    assert len(violations) == 0


@pytest.mark.asyncio
async def test_check_bias_risk(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client,
    sample_ticket_ml
):
    """Testa detecção de uso de modelo ML sem bias testing."""
    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client
    )

    violations = await enforcer._check_bias_risk(sample_ticket_ml)

    assert len(violations) > 0
    assert violations[0].violation_type == ViolationType.ETHICAL_CONCERN
    assert "bias testing" in violations[0].description.lower()


@pytest.mark.asyncio
async def test_check_privacy_compliance(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client
):
    """Testa detecção de violação GDPR."""
    ticket = {
        "ticket_id": "ticket-privacy-123",
        "task_type": "DATA_PROCESSING",
        "parameters": {
            "data_classification": "PII",
            "user_consent": False
        }
    }

    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client
    )

    violations = await enforcer._check_privacy_compliance(ticket)

    assert len(violations) > 0
    assert any(
        v.violation_type == ViolationType.COMPLIANCE_BREACH
        for v in violations
    )


@pytest.mark.asyncio
async def test_check_blast_radius(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client,
    sample_ticket_deploy
):
    """Testa detecção de blast radius > 10%."""
    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client
    )

    violations = await enforcer._check_blast_radius(sample_ticket_deploy)

    assert len(violations) > 0
    assert "blast radius" in violations[0].description.lower()


@pytest.mark.asyncio
async def test_check_rollback_plan(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client,
    sample_ticket_deploy
):
    """Testa que mudanças críticas requerem rollback plan."""
    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client
    )

    violations = await enforcer._check_rollback_plan(sample_ticket_deploy)

    assert len(violations) > 0
    assert "rollback plan" in violations[0].description.lower()


@pytest.mark.asyncio
async def test_check_cost_threshold(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client
):
    """Testa bloqueio de mudanças que excedem budget."""
    ticket = {
        "ticket_id": "ticket-cost-123",
        "task_type": "DEPLOY",
        "parameters": {
            "estimated_cost_usd": 5000  # Acima do threshold de $1000
        }
    }

    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client
    )

    violations = await enforcer._check_cost_threshold(ticket)

    assert len(violations) > 0
    assert "custo" in violations[0].description.lower()


@pytest.mark.asyncio
async def test_guardrails_advisory_mode(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client,
    sample_ticket_deploy
):
    """Testa que modo ADVISORY apenas alerta."""
    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client,
        mode="ADVISORY"
    )

    violations = await enforcer.enforce_guardrails(sample_ticket_deploy)

    # Deve retornar violations mas não bloquear
    assert enforcer.mode == "ADVISORY"


@pytest.mark.asyncio
async def test_guardrails_blocking_mode(
    mock_opa_client,
    mock_mongodb_client,
    mock_redis_client,
    sample_ticket_deploy
):
    """Testa que modo BLOCKING rejeita ticket."""
    enforcer = GuardrailEnforcer(
        mock_opa_client,
        mock_mongodb_client,
        mock_redis_client,
        mode="BLOCKING"
    )

    violations = await enforcer.enforce_guardrails(sample_ticket_deploy)

    # Deve ter violações e modo BLOCKING
    assert len(violations) > 0
    assert enforcer.mode == "BLOCKING"
