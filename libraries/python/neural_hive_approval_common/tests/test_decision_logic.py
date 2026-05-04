"""
Tests for Approval Decision Logic.

R-A2: Decision logic with configurable thresholds
R-A4: ML predictor interface
INV-6: Approval Request Lifecycle (PENDING -> APPROVED/REJECTED only)
"""


import pytest

from neural_hive_approval_common.decision_logic import (
    ApprovalDecisionLogic,
    ApprovalThresholds,
    DecisionConfig,
)
from neural_hive_approval_common.models import (
    ApprovalStatus,
    RiskBand,
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)
from neural_hive_approval_common.predictor import MLPredictor, MLPredictorInterface


class MockMLPredictor(MLPredictorInterface):
    """Mock ML predictor for testing."""

    def __init__(self, enabled=True, decision="approve", confidence=0.9):
        self.enabled = enabled
        self.decision = decision
        self.confidence = confidence

    def is_enabled(self) -> bool:
        return self.enabled

    async def predict_from_text(self, intent_text, specialist_confidence=0.5):
        if not self.enabled:
            return None
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "model_version": "test-v1",
        }

    async def get_auto_decision(self, intent_text, risk_band, specialist_confidence=0.5):
        if not self.enabled:
            return None
        return {
            "auto_decision": self.decision,
            "confidence": self.confidence,
            "reason": "Mock ML decision",
        }


class TestApprovalThresholds:
    """Tests for ApprovalThresholds configuration."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = ApprovalThresholds()

        assert thresholds.auto_approve_max_risk_low == 0.3
        assert thresholds.auto_approve_max_risk_medium == 0.2
        assert thresholds.auto_approve_max_risk_high == 0.1
        assert thresholds.ml_confidence_threshold == 0.8
        assert thresholds.require_manual_for_destructive is True
        assert thresholds.enable_ml_auto_approval is False

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = ApprovalThresholds(
            auto_approve_max_risk_low=0.5,
            ml_confidence_threshold=0.9,
            enable_ml_auto_approval=True,
        )

        assert thresholds.auto_approve_max_risk_low == 0.5
        assert thresholds.ml_confidence_threshold == 0.9
        assert thresholds.enable_ml_auto_approval is True


class TestDecisionConfig:
    """Tests for DecisionConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = DecisionConfig()

        assert isinstance(config.thresholds, ApprovalThresholds)

    def test_config_from_dict(self):
        """Test configuration from dictionary."""
        config = DecisionConfig(
            thresholds={
                "auto_approve_max_risk_low": 0.5,
                "ml_confidence_threshold": 0.9,
            }
        )

        assert config.thresholds.auto_approve_max_risk_low == 0.5
        assert config.thresholds.ml_confidence_threshold == 0.9


class TestApprovalDecisionLogic:
    """Tests for ApprovalDecisionLogic.

    R-A2: Decision logic with configurable thresholds.
    R-A4: ML predictor interface integration.
    INV-6: Approval Request Lifecycle.
    """

    @pytest.fixture()
    def logic(self):
        """Fixture for decision logic with default config."""
        return ApprovalDecisionLogic()

    @pytest.fixture()
    def low_risk_request(self):
        """Fixture for low risk request."""
        return UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.2,
            risk_band=RiskBand.LOW,
            cognitive_plan={"tasks": []},
        )

    @pytest.fixture()
    def high_risk_request(self):
        """Fixture for high risk request."""
        return UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.7,
            risk_band=RiskBand.HIGH,
            cognitive_plan={"tasks": []},
        )

    @pytest.fixture()
    def destructive_request(self):
        """Fixture for destructive request."""
        return UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.1,
            risk_band=RiskBand.LOW,
            is_destructive=True,
            destructive_tasks=["task-1"],
            cognitive_plan={"tasks": []},
        )

    @pytest.mark.asyncio()
    async def test_low_risk_auto_approve(self, logic, low_risk_request):
        """Test auto-approval for low risk (R-A2)."""
        decision, reason, is_auto = await logic.evaluate(low_risk_request)

        assert decision == "approved"
        assert is_auto is True
        assert "below threshold" in reason.lower()

    @pytest.mark.asyncio()
    async def test_high_risk_manual_approval(self, logic, high_risk_request):
        """Test manual approval required for high risk."""
        decision, reason, is_auto = await logic.evaluate(high_risk_request)

        assert decision == "pending"
        assert is_auto is False
        assert "manual" in reason.lower()

    @pytest.mark.asyncio()
    async def test_destructive_requires_manual(self, logic, destructive_request):
        """Test destructive operations require manual approval."""
        decision, reason, is_auto = await logic.evaluate(destructive_request)

        assert decision == "pending"
        assert is_auto is False
        assert "destructive" in reason.lower()

    @pytest.mark.asyncio()
    async def test_very_high_risk_auto_reject(self, logic):
        """Test auto-reject for very high risk."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.95,
            risk_band=RiskBand.CRITICAL,
            cognitive_plan={"tasks": []},
        )

        decision, reason, is_auto = await logic.evaluate(request)

        assert decision == "rejected"
        assert is_auto is True
        assert "too high" in reason.lower()

    @pytest.mark.asyncio()
    async def test_inv6_non_pending_status(self, logic):
        """Test INV-6: Non-pending requests are rejected."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.1,
            risk_band=RiskBand.LOW,
            status=ApprovalStatus.APPROVED,  # Already approved
            cognitive_plan={"tasks": []},
        )

        decision, reason, is_auto = await logic.evaluate(request)

        assert decision == "rejected"
        assert "already" in reason.lower()

    @pytest.mark.asyncio()
    async def test_ml_predictor_integration(self, low_risk_request):
        """Test R-A4: ML predictor integration."""
        # Enable ML
        config = DecisionConfig(
            thresholds={
                "enable_ml_auto_approval": True,
                "ml_confidence_threshold": 0.8,
            }
        )
        logic = ApprovalDecisionLogic(config)

        # Mock ML predictor
        ml_predictor = MockMLPredictor(enabled=True, decision="approve", confidence=0.95)

        decision, reason, is_auto = await logic.evaluate(
            low_risk_request, ml_predictor=ml_predictor
        )

        # Should use ML decision
        assert decision == "approved"
        assert is_auto is True

    @pytest.mark.asyncio()
    async def test_ml_predictor_low_confidence(self, low_risk_request):
        """Test that low confidence ML predictions don't auto-approve."""
        config = DecisionConfig(
            thresholds={
                "enable_ml_auto_approval": True,
                "ml_confidence_threshold": 0.9,
            }
        )
        logic = ApprovalDecisionLogic(config)

        # Low confidence ML predictor
        ml_predictor = MockMLPredictor(enabled=True, decision="approve", confidence=0.7)

        decision, reason, is_auto = await logic.evaluate(
            low_risk_request, ml_predictor=ml_predictor
        )

        # Should fall back to risk-based decision
        assert decision == "approved"  # Still approved due to low risk
        assert "below threshold" in reason.lower()  # Risk-based reason

    @pytest.mark.asyncio()
    async def test_critical_risk_no_ml_auto(self):
        """Test CRITICAL risk never auto-approves even with ML."""
        request = UnifiedApprovalRequest(
            plan_id="plan-123",
            intent_id="intent-456",
            risk_score=0.5,
            risk_band=RiskBand.CRITICAL,
            cognitive_plan={"tasks": []},
        )

        config = DecisionConfig(
            thresholds={
                "enable_ml_auto_approval": True,
                "ml_confidence_threshold": 0.8,
            }
        )
        logic = ApprovalDecisionLogic(config)

        ml_predictor = MockMLPredictor(enabled=True, decision="approve", confidence=0.99)

        decision, reason, is_auto = await logic.evaluate(request, ml_predictor=ml_predictor)

        # CRITICAL always requires manual approval
        assert decision == "pending"
        assert is_auto is False

    def test_create_decision_inv3_compatibility(self, logic):
        """Test INV-3: Creates compatible ApprovalDecision format."""
        decision = logic.create_decision(
            plan_id="plan-123",
            decision="approved",
            approved_by="user-456",
        )

        assert isinstance(decision, UnifiedApprovalDecision)
        assert decision.plan_id == "plan-123"
        assert decision.decision == "approved"
        assert decision.approved_by == "user-456"
        assert decision.approved_at is not None

        # Verify INV-3 required fields
        assert hasattr(decision, "decision")
        assert hasattr(decision, "approved_by")
        assert hasattr(decision, "approved_at")
        assert hasattr(decision, "rejection_reason")

    def test_create_decision_with_ml_fields(self, logic):
        """Test creating decision with ML fields."""
        decision = logic.create_decision(
            plan_id="plan-123",
            decision="approved",
            approved_by="system",
            ml_confidence=0.95,
            ml_model_version="v1.0.0",
            auto_approved=True,
        )

        assert decision.ml_confidence == 0.95
        assert decision.ml_model_version == "v1.0.0"
        assert decision.auto_approved is True


class TestMLPredictorStub:
    """Tests for MLPredictor stub implementation.

    R-A4: ML predictor interface.
    """

    def test_stub_disabled(self):
        """Test stub predictor is disabled by default."""
        predictor = MLPredictor(enabled=False)

        assert predictor.is_enabled() is False

    @pytest.mark.asyncio()
    async def test_stub_predict_returns_none(self):
        """Test stub predictor returns None when enabled."""
        predictor = MLPredictor(enabled=True)

        result = await predictor.predict_from_text("test intent")

        assert result is None

    @pytest.mark.asyncio()
    async def test_stub_auto_decision_returns_none(self):
        """Test stub auto-decision returns None."""
        predictor = MLPredictor(enabled=True)

        result = await predictor.get_auto_decision("test intent", "low")

        assert result is None
