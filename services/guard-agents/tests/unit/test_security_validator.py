"""
Testes unitários para SecurityValidator.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.security_validator import SecurityValidator
from src.models.security_validation import (
    SecurityValidation,
    GuardrailViolation,
    ValidationStatus,
    ValidatorType,
    ViolationType,
    Severity
)


@pytest.fixture
def mock_opa_client():
    """Mock OPA client."""
    client = AsyncMock()
    client.evaluate_policy = AsyncMock(return_value={"allowed": True})
    return client


@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client."""
    return AsyncMock()


@pytest.fixture
def mock_vault_client():
    """Mock Vault client."""
    return AsyncMock()


@pytest.fixture
def mock_trivy_client():
    """Mock Trivy client."""
    client = AsyncMock()
    client.scan_parameters = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock()
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client."""
    client = MagicMock()
    collection = AsyncMock()
    collection.insert_one = AsyncMock()
    client.security_validations = collection
    return client


@pytest.fixture
def mock_clients(
    mock_opa_client,
    mock_k8s_client,
    mock_vault_client,
    mock_trivy_client,
    mock_redis_client,
    mock_mongodb_client
):
    """Fixture com todos os clients mockados."""
    return {
        "opa_client": mock_opa_client,
        "k8s_client": mock_k8s_client,
        "vault_client": mock_vault_client,
        "trivy_client": mock_trivy_client,
        "redis_client": mock_redis_client,
        "mongodb_client": mock_mongodb_client
    }


@pytest.fixture
def sample_ticket():
    """ExecutionTicket de exemplo."""
    return {
        "ticket_id": "ticket-123",
        "plan_id": "plan-456",
        "intent_id": "intent-789",
        "correlation_id": "corr-abc",
        "task_type": "BUILD",
        "security_level": "INTERNAL",
        "service_account": "default",
        "namespace": "default",
        "parameters": {
            "repo": "test-repo",
            "branch": "main"
        },
        "required_capabilities": []
    }


@pytest.mark.asyncio
async def test_validate_ticket_approved(mock_clients, sample_ticket):
    """Testa validação de ticket sem violações -> APPROVED."""
    validator = SecurityValidator(**mock_clients)

    validation = await validator.validate_ticket(sample_ticket)

    assert validation.validation_status == ValidationStatus.APPROVED
    assert len(validation.violations) == 0
    assert validation.risk_assessment.risk_score < 0.3
    assert validation.ticket_id == sample_ticket["ticket_id"]


@pytest.mark.asyncio
async def test_validate_ticket_rejected_secrets(mock_clients, sample_ticket):
    """Testa validação de ticket com secrets expostos -> REJECTED."""
    # Configurar Trivy para detectar secrets
    mock_clients["trivy_client"].scan_parameters = AsyncMock(return_value=[
        {
            "type": "aws-access-key",
            "match": "AKIA...",
            "line": 1
        }
    ])

    validator = SecurityValidator(**mock_clients)
    validation = await validator.validate_ticket(sample_ticket)

    assert validation.validation_status == ValidationStatus.REJECTED
    assert len(validation.violations) > 0
    assert validation.violations[0].violation_type == ViolationType.SECRET_EXPOSED
    assert validation.violations[0].severity == Severity.CRITICAL


@pytest.mark.asyncio
async def test_validate_ticket_rejected_rbac(mock_clients, sample_ticket):
    """Testa validação de ticket sem permissões RBAC -> REJECTED."""
    # Configurar ticket com required_capabilities
    sample_ticket["required_capabilities"] = ["SYS_ADMIN"]

    validator = SecurityValidator(**mock_clients)
    validation = await validator.validate_ticket(sample_ticket)

    # Deve detectar privilege escalation
    assert any(
        v.violation_type == ViolationType.RBAC_VIOLATION
        for v in validation.violations
    )


@pytest.mark.asyncio
async def test_validate_ticket_requires_approval(mock_clients, sample_ticket):
    """Testa validação de ticket com risk_score > 0.8 -> REQUIRES_APPROVAL."""
    # Configurar OPA para negar
    mock_clients["opa_client"].evaluate_policy = AsyncMock(return_value={
        "allowed": False,
        "reason": "Deploy em produção requer aprovação"
    })

    validator = SecurityValidator(**mock_clients)
    validation = await validator.validate_ticket(sample_ticket)

    # Deve ter violação de policy
    assert any(
        v.violation_type == ViolationType.POLICY_VIOLATION
        for v in validation.violations
    )


@pytest.mark.asyncio
async def test_validate_opa_policies(mock_clients, sample_ticket):
    """Testa validação OPA com policy negada."""
    mock_clients["opa_client"].evaluate_policy = AsyncMock(return_value={
        "allowed": False,
        "reason": "Política violada",
        "remediation": "Ajustar configuração"
    })

    validator = SecurityValidator(**mock_clients)
    violations = await validator._validate_opa_policies(sample_ticket)

    assert len(violations) == 1
    assert violations[0].violation_type == ViolationType.POLICY_VIOLATION
    assert "Política violada" in violations[0].description


@pytest.mark.asyncio
async def test_scan_secrets_detected(mock_clients, sample_ticket):
    """Testa detecção de AWS credentials pelo Trivy."""
    mock_clients["trivy_client"].scan_parameters = AsyncMock(return_value=[
        {
            "type": "aws-access-key",
            "match": "AKIAIOSFODNN7EXAMPLE",
            "line": 10
        },
        {
            "type": "aws-secret-key",
            "match": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "line": 11
        }
    ])

    validator = SecurityValidator(**mock_clients)
    violations = await validator._scan_secrets(sample_ticket)

    assert len(violations) == 2
    assert all(v.violation_type == ViolationType.SECRET_EXPOSED for v in violations)
    assert all(v.severity == Severity.CRITICAL for v in violations)


@pytest.mark.asyncio
async def test_validate_rbac_privilege_escalation(mock_clients, sample_ticket):
    """Testa detecção de tentativa de privilege escalation."""
    sample_ticket["required_capabilities"] = ["SYS_ADMIN", "NET_ADMIN"]

    validator = SecurityValidator(**mock_clients)
    violations = await validator._validate_rbac(sample_ticket)

    # Deve detectar privilege escalation
    assert any(
        "escalação de privilégios" in v.description.lower()
        for v in violations
    )


@pytest.mark.asyncio
async def test_calculate_risk_assessment(mock_clients):
    """Testa cálculo correto de risk_score."""
    validator = SecurityValidator(**mock_clients)

    # Sem violações
    violations = []
    risk = await validator._calculate_risk_assessment(violations, {})
    assert risk.risk_score == 0.0
    assert risk.severity == Severity.LOW

    # Com violações CRITICAL
    violations = [
        GuardrailViolation(
            violation_type=ViolationType.SECRET_EXPOSED,
            severity=Severity.CRITICAL,
            description="Test",
            remediation_suggestion="Test",
            detected_by="Test"
        )
    ]
    risk = await validator._calculate_risk_assessment(violations, {})
    assert risk.risk_score == 1.0
    assert risk.severity == Severity.CRITICAL


@pytest.mark.asyncio
async def test_cache_validation(mock_clients, sample_ticket):
    """Testa que validação é cacheada no Redis."""
    validator = SecurityValidator(**mock_clients)

    validation = await validator.validate_ticket(sample_ticket)

    # Verificar que setex foi chamado
    mock_clients["redis_client"].setex.assert_called_once()


@pytest.mark.asyncio
async def test_graceful_degradation_trivy_down(mock_clients, sample_ticket):
    """Testa que continua se Trivy falhar."""
    # Trivy indisponível
    mock_clients["trivy_client"] = None

    validator = SecurityValidator(**mock_clients)
    validation = await validator.validate_ticket(sample_ticket)

    # Deve completar sem erro
    assert validation is not None
    assert validation.validation_status in [ValidationStatus.APPROVED, ValidationStatus.REQUIRES_APPROVAL]
