"""
Approval Decision Logic.

Centralized decision logic for approval requests with configurable thresholds
and ML predictor integration.

Fulfills:
- R-A2: Decision logic with configurable thresholds
- R-A4: ML predictor interface
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import structlog
from pydantic import BaseModel, Field, field_validator

from .models import (
    ApprovalStatus,
    RiskBand,
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)

logger = structlog.get_logger()


@dataclass
class ApprovalThresholds:
    """Configuracao de thresholds para decisao automatica.

    R-A2: Configurable thresholds for decision logic.
    """

    # Auto-approve thresholds by risk band
    auto_approve_max_risk_low: float = 0.3  # Auto-aprove if risk <= 0.3 for LOW band
    auto_approve_max_risk_medium: float = 0.2  # Auto-aprove if risk <= 0.2 for MEDIUM band
    auto_approve_max_risk_high: float = 0.1  # Auto-aprove if risk <= 0.1 for HIGH band
    # CRITICAL never auto-approves

    # ML confidence threshold for auto-approval
    ml_confidence_threshold: float = 0.8  # ML confidence >= 0.8 for auto-decision

    # Destructive operations always require manual approval
    require_manual_for_destructive: bool = True

    # Enable ML predictor integration
    enable_ml_auto_approval: bool = False


class DecisionConfig(BaseModel):
    """Configuration for approval decision logic."""

    thresholds: ApprovalThresholds = Field(default_factory=ApprovalThresholds)

    @field_validator("thresholds", mode="before")
    @classmethod
    def validate_thresholds(cls, v: Any) -> ApprovalThresholds:
        """Validate thresholds configuration."""
        if isinstance(v, dict):
            return ApprovalThresholds(**v)
        if isinstance(v, ApprovalThresholds):
            return v
        return ApprovalThresholds()


class ApprovalDecisionLogic:
    """
    Centralized approval decision logic.

    R-A2: Implements decision logic with configurable thresholds.
    R-A4: Integrates with ML predictor interface.
    INV-6: Respects approval request lifecycle (PENDING -> APPROVED/REJECTED only).
    """

    def __init__(self, config: Optional[DecisionConfig] = None):
        """
        Initialize decision logic.

        Args:
            config: Decision configuration. Uses defaults if not provided.
        """
        self.config = config or DecisionConfig()
        self.logger = logger.bind(component="approval_decision_logic")

    async def evaluate(
        self,
        request: UnifiedApprovalRequest,
        ml_predictor: Optional["MLPredictorInterface"] = None,
        user_id: Optional[str] = None,
    ) -> tuple[Literal["approved", "rejected"], Optional[str], bool]:
        """
        Evaluate an approval request and return decision.

        Args:
            request: Approval request to evaluate
            ml_predictor: Optional ML predictor for enhanced decisions
            user_id: User ID making the decision (for manual decisions)

        Returns:
            Tuple of (decision, reason, is_auto)

        Raises:
            ValueError: If request is invalid
        """
        if not request.plan_id:
            raise ValueError("plan_id is required")

        # INV-6: Check current status
        if request.status != ApprovalStatus.PENDING:
            self.logger.warning(
                "evaluation_non_pending",
                plan_id=request.plan_id,
                current_status=request.status,
            )
            return "rejected", f"Request already {request.status}", False

        # Rule 1: Destructive operations always require manual approval
        if (
            self.config.thresholds.require_manual_for_destructive
            and request.is_destructive
        ):
            self.logger.info(
                "destructive_requires_manual",
                plan_id=request.plan_id,
                destructive_tasks=request.destructive_tasks,
            )
            return "pending", "Destructive operations require manual approval", False

        # Rule 2: Check risk band thresholds
        decision_by_risk = self._evaluate_by_risk_threshold(request)
        if decision_by_risk is not None:
            decision, reason = decision_by_risk
            self.logger.info(
                "decision_by_risk_threshold",
                plan_id=request.plan_id,
                decision=decision,
                reason=reason,
                risk_band=request.risk_band,
                risk_score=request.risk_score,
            )
            return decision, reason, True

        # Rule 3: ML predictor integration (if enabled and available)
        # Skip for CRITICAL risk band
        if (
            self.config.thresholds.enable_ml_auto_approval
            and ml_predictor
            and ml_predictor.is_enabled()
            and request.risk_band != RiskBand.CRITICAL
        ):
            decision_by_ml = await self._evaluate_by_ml(request, ml_predictor)
            if decision_by_ml is not None:
                decision, reason, confidence = decision_by_ml
                self.logger.info(
                    "decision_by_ml",
                    plan_id=request.plan_id,
                    decision=decision,
                    reason=reason,
                    confidence=confidence,
                )
                return decision, reason, True

        # Default: Manual approval required
        return "pending", "Manual approval required", False

    def _evaluate_by_risk_threshold(
        self, request: UnifiedApprovalRequest
    ) -> Optional[tuple[Literal["approved", "rejected"], str]]:
        """
        Evaluate based on risk band thresholds.

        Returns:
            (decision, reason) or None if cannot decide automatically
        """
        thresholds = self.config.thresholds
        risk = request.risk_score
        band = request.risk_band

        # Auto-reject for very high risk (regardless of band)
        if risk >= 0.9:
            return "rejected", f"Risk score ({risk:.2f}) too high"

        # CRITICAL always requires manual approval (after risk check)
        if band == RiskBand.CRITICAL:
            return None

        # Auto-approve based on thresholds
        if band == RiskBand.LOW and risk <= thresholds.auto_approve_max_risk_low:
            return "approved", f"Low risk ({risk:.2f}) below threshold"

        if band == RiskBand.MEDIUM and risk <= thresholds.auto_approve_max_risk_medium:
            return "approved", f"Medium risk ({risk:.2f}) below threshold"

        if band == RiskBand.HIGH and risk <= thresholds.auto_approve_max_risk_high:
            return "approved", f"High risk ({risk:.2f}) below threshold"

        # Cannot decide automatically
        return None

    async def _evaluate_by_ml(
        self, request: UnifiedApprovalRequest, ml_predictor: "MLPredictorInterface"
    ) -> Optional[tuple[Literal["approved", "rejected"], str, float]]:
        """
        Evaluate using ML predictor.

        R-A4: ML predictor interface integration.

        Returns:
            (decision, reason, confidence) or None if ML cannot decide
        """
        try:
            # Get ML prediction
            prediction = await ml_predictor.predict_from_text(
                intent_text=request.original_intent_text or "",
                specialist_confidence=0.5,  # Could be fetched from ledger
            )

            if not prediction:
                return None

            decision = prediction.get("decision")
            confidence = prediction.get("confidence", 0.0)

            # Check confidence threshold
            if confidence < self.config.thresholds.ml_confidence_threshold:
                self.logger.debug(
                    "ml_confidence_below_threshold",
                    plan_id=request.plan_id,
                    confidence=confidence,
                    threshold=self.config.thresholds.ml_confidence_threshold,
                )
                return None

            if decision == "approve" and confidence >= 0.9:
                return "approved", f"ML prediction (confidence: {confidence:.2f})", confidence
            elif decision == "reject":
                return (
                    "rejected",
                    f"ML prediction (confidence: {confidence:.2f})",
                    confidence,
                )

        except Exception as e:
            self.logger.warning(
                "ml_evaluation_failed",
                plan_id=request.plan_id,
                error=str(e),
            )

        return None

    def create_decision(
        self,
        plan_id: str,
        decision: Literal["approved", "rejected"],
        approved_by: str,
        rejection_reason: Optional[str] = None,
        comments: Optional[str] = None,
        ml_confidence: Optional[float] = None,
        ml_model_version: Optional[str] = None,
        auto_approved: bool = False,
    ) -> UnifiedApprovalDecision:
        """
        Create an approval decision object.

        INV-3: Produces same ApprovalDecision format as existing approval-service.

        Args:
            plan_id: ID of the plan
            decision: Decision (approved/rejected)
            approved_by: User ID making the decision
            rejection_reason: Reason for rejection (if rejected)
            comments: Additional comments
            ml_confidence: ML model confidence (if applicable)
            ml_model_version: ML model version (if applicable)
            auto_approved: Whether this was an auto-approval

        Returns:
            UnifiedApprovalDecision object
        """
        return UnifiedApprovalDecision(
            plan_id=plan_id,
            decision=decision,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
            rejection_reason=rejection_reason,
            comments=comments,
            ml_confidence=ml_confidence,
            ml_model_version=ml_model_version,
            auto_approved=auto_approved,
        )
