"""Tests para modelos de aprovação."""

from datetime import datetime, timezone, timedelta

from src.models.approval import (
    ApprovalDecision,
    ApprovalMetrics,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
)


class TestApprovalStatus:
    """Testes para enum ApprovalStatus."""

    def test_status_values(self):
        """Verifica valores do enum."""
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.APPROVED == "approved"
        assert ApprovalStatus.REJECTED == "rejected"
        assert ApprovalStatus.CANCELLED == "cancelled"


class TestApprovalType:
    """Testes para enum ApprovalType."""

    def test_type_values(self):
        """Verifica valores do enum."""
        assert ApprovalType.REQUIREMENT == "requirement"
        assert ApprovalType.ARCHITECTURE == "architecture"
        assert ApprovalType.CODE_GENERATION == "code_generation"
        assert ApprovalType.DOCUMENTATION == "documentation"
        assert ApprovalType.TEST_PLAN == "test_plan"


class TestApprovalRequest:
    """Testes para ApprovalRequest."""

    def test_create_minimal_request(self):
        """Cria solicitação mínima."""
        request = ApprovalRequest(
            id="REQ-001",
            type=ApprovalType.REQUIREMENT,
            title="Login Feature",
            description="Implementação de login",
            requested_by="user@example.com",
        )

        assert request.id == "REQ-001"
        assert request.type == ApprovalType.REQUIREMENT
        assert request.title == "Login Feature"
        assert request.context == {}
        assert isinstance(request.created_at, datetime)

    def test_create_full_request(self):
        """Cria solicitação completa."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        context = {"complexity": 3, "priority": "high", "is_critical": False}

        request = ApprovalRequest(
            id="REQ-002",
            type=ApprovalType.ARCHITECTURE,
            title="Microservices Architecture",
            description="Arquitetura de microsserviços",
            requested_by="architect@example.com",
            context=context,
            expires_at=expires_at,
        )

        assert request.context["complexity"] == 3
        assert request.context["priority"] == "high"
        assert request.expires_at is not None


class TestApprovalDecision:
    """Testes para ApprovalDecision."""

    def test_create_decision(self):
        """Cria decisão de aprovação."""
        decision = ApprovalDecision(
            id="DEC-001",
            request_id="REQ-001",
            status=ApprovalStatus.APPROVED,
            confidence_score=0.9,
            reasoning="Solicitação bem estruturada",
            approved_by="ai-gpt-4",
        )

        assert decision.id == "DEC-001"
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.confidence_score == 0.9
        assert decision.approved_by == "ai-gpt-4"


class TestApprovalMetrics:
    """Testes para ApprovalMetrics."""

    def test_default_metrics(self):
        """Cria métricas com valores padrão."""
        metrics = ApprovalMetrics()

        assert metrics.total_requests == 0
        assert metrics.pending_requests == 0
        assert metrics.approved_requests == 0
        assert metrics.rejected_requests == 0

    def test_calculate_approval_rate(self):
        """Calcula taxa de aprovação."""
        metrics = ApprovalMetrics(total_requests=100, approved_requests=80, rejected_requests=20)

        approval_rate = metrics.approved_requests / metrics.total_requests
        assert approval_rate == 0.8


class TestApprovalPolicy:
    """Testes para ApprovalPolicy."""

    def test_default_policy(self):
        """Cria política padrão."""
        policy = ApprovalPolicy(
            id="default", name="Política Padrão", description="Política padrão do sistema"
        )

        assert policy.auto_approve_threshold == 0.8
        assert policy.auto_reject_threshold == 0.3
        assert policy.require_human_threshold == 0.5
        assert policy.require_human_for_critical is True

    def test_custom_policy(self):
        """Cria política customizada."""
        policy = ApprovalPolicy(
            id="strict",
            name="Política Rigorosa",
            description="Requer aprovação manual para tudo",
            applies_to_types=[ApprovalType.ARCHITECTURE],
            auto_approve_threshold=0.95,
            auto_reject_threshold=0.1,
            require_human_for_critical=True,
            max_auto_approve_complexity=2,
        )

        assert policy.auto_approve_threshold == 0.95
        assert len(policy.applies_to_types) == 1
        assert policy.max_auto_approve_complexity == 2
