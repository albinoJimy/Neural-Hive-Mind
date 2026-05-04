"""
Tests for Unified Approval Models.

R-A1: UnifiedApprovalRequest, UnifiedApprovalDecision models
INV-3: Approval Decision Format compatibility
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from neural_hive_approval_common.models import (
    ApprovalStatus,
    ApproveRequestBody,
    PendingApprovalsQuery,
    RejectRequestBody,
    RevertRequestBody,
    RiskBand,
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)


class TestUnifiedApprovalRequest:
    """Tests for UnifiedApprovalRequest model.

    R-A1: UnifiedApprovalRequest with required fields.
    INV-3: Approval Decision Format compatibility.
    INV-9: Original intent text preservation.
    """

    def test_create_minimal_request(self):
        """Test creating minimal approval request."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.3,
            risk_band=RiskBand.LOW,
            cognitive_plan={"tasks": []},
        )

        assert request.plan_id == "plan-123"
        assert request.intent_id == "intent-456"
        assert request.risk_score == 0.3
        assert request.risk_band == RiskBand.LOW
        assert request.status == ApprovalStatus.PENDING
        assert request.approval_id is not None

    def test_create_with_original_intent_text(self):
        """Test creating request with original intent text (INV-9)."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            original_intent_text="Create a new user account",
            risk_score=0.3,
            risk_band=RiskBand.LOW,
            cognitive_plan={"tasks": []},
        )

        assert request.original_intent_text == "Create a new user account"

    def test_create_with_destructive_tasks(self):
        """Test creating request with destructive tasks."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.7,
            risk_band=RiskBand.HIGH,
            is_destructive=True,
            destructive_tasks=["task-1", "task-2"],
            cognitive_plan={"tasks": []},
        )

        assert request.is_destructive is True
        assert request.destructive_tasks == ["task-1", "task-2"]

    def test_risk_score_validation(self):
        """Test risk score validation (0-1)."""
        with pytest.raises(ValidationError):
            UnifiedApprovalRequest(
                plan_id="plan-123",
                intent_id="intent-456",
                risk_score=1.5,  # Invalid
                risk_band=RiskBand.LOW,
                cognitive_plan={"tasks": []},
            )

        with pytest.raises(ValidationError):
            UnifiedApprovalRequest(
                plan_id="plan-123",
                intent_id="intent-456",
                risk_score=-0.1,  # Invalid
                risk_band=RiskBand.LOW,
                cognitive_plan={"tasks": []},
            )

    def test_to_kafka_dict_compatibility(self):
        """Test that model is compatible with existing Kafka format (INV-3, INV-4)."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.3,
            risk_band=RiskBand.LOW,
            cognitive_plan={"tasks": []},
        )

        # Verify fields match existing contract
        assert hasattr(request, "plan_id")
        assert hasattr(request, "intent_id")
        assert hasattr(request, "risk_score")
        assert hasattr(request, "risk_band")
        assert hasattr(request, "status")


class TestUnifiedApprovalDecision:
    """Tests for UnifiedApprovalDecision model.

    R-A1: UnifiedApprovalDecision with required fields.
    INV-3: Approval Decision Format compatibility.
    """

    def test_create_approval_decision(self):
        """Test creating approval decision."""
        decision = UnifiedApprovalDecision(
            plan_id="plan-123",
            decision="approved",
            approved_by="user-456",
        )

        assert decision.plan_id == "plan-123"
        assert decision.decision == "approved"
        assert decision.approved_by == "user-456"
        assert decision.approved_at is not None
        assert decision.auto_approved is False

    def test_create_rejection_decision(self):
        """Test creating rejection decision."""
        decision = UnifiedApprovalDecision(
            plan_id="plan-123",
            decision="rejected",
            approved_by="user-456",
            rejection_reason="Security concern",
        )

        assert decision.decision == "rejected"
        assert decision.rejection_reason == "Security concern"

    def test_create_auto_approved_decision(self):
        """Test creating auto-approved decision."""
        decision = UnifiedApprovalDecision(
            plan_id="plan-123",
            decision="approved",
            approved_by="system",
            auto_approved=True,
            ml_confidence=0.95,
            ml_model_version="v1.0.0",
        )

        assert decision.auto_approved is True
        assert decision.ml_confidence == 0.95
        assert decision.ml_model_version == "v1.0.0"

    def test_decision_literal_validation(self):
        """Test that decision must be 'approved' or 'rejected'."""
        with pytest.raises(ValidationError):
            UnifiedApprovalDecision(
                plan_id="plan-123",
                decision="pending",  # Invalid
                approved_by="user-456",
            )

    def test_inv3_compatibility(self):
        """Test INV-3: Approval Decision Format compatibility."""
        decision = UnifiedApprovalDecision(
            plan_id="plan-123",
            decision="approved",
            approved_by="user-456",
            approved_at=datetime.now(timezone.utc),
            rejection_reason=None,
        )

        # Verify required INV-3 fields
        assert hasattr(decision, "decision")
        assert decision.decision in ["approved", "rejected"]
        assert hasattr(decision, "approved_by")
        assert isinstance(decision.approved_by, str)
        assert hasattr(decision, "approved_at")
        assert isinstance(decision.approved_at, datetime)
        assert hasattr(decision, "rejection_reason")
        # rejection_reason can be None


class TestRequestBodyModels:
    """Tests for request body models."""

    def test_approve_request_body(self):
        """Test approve request body."""
        body = ApproveRequestBody(comments="Looks good")
        assert body.comments == "Looks good"

        body_no_comments = ApproveRequestBody()
        assert body_no_comments.comments is None

    def test_reject_request_body(self):
        """Test reject request body."""
        body = RejectRequestBody(reason="Security risk")
        assert body.reason == "Security risk"

        # Reason is required
        with pytest.raises(ValidationError):
            RejectRequestBody(reason="")

    def test_revert_request_body(self):
        """Test revert request body (INV-6: Saga compensation)."""
        body = RevertRequestBody(
            reason="Execution failed",
            ticket_id="saga-123",
        )
        assert body.reason == "Execution failed"
        assert body.ticket_id == "saga-123"


class TestQueryModels:
    """Tests for query models."""

    def test_pending_approvals_query_defaults(self):
        """Test pending approvals query with defaults."""
        query = PendingApprovalsQuery()
        assert query.limit == 50
        assert query.offset == 0
        assert query.risk_band is None
        assert query.is_destructive is None

    def test_pending_approvals_query_with_filters(self):
        """Test pending approvals query with filters."""
        query = PendingApprovalsQuery(
            limit=10,
            offset=20,
            risk_band=RiskBand.HIGH,
            is_destructive=True,
        )
        assert query.limit == 10
        assert query.offset == 20
        assert query.risk_band == RiskBand.HIGH
        assert query.is_destructive is True

    def test_limit_validation(self):
        """Test limit validation (1-100)."""
        with pytest.raises(ValidationError):
            PendingApprovalsQuery(limit=0)

        with pytest.raises(ValidationError):
            PendingApprovalsQuery(limit=101)
