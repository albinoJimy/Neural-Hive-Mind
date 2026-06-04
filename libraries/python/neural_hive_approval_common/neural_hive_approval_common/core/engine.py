"""Orchestrator for approval decision logic.

A ``ApprovalDecisionEngine`` compõe ``CommonRules``, ``RiskAssessor``,
``ThresholdEvaluator`` e (opcionalmente) ``MLPredictorInterface``,
expondo estratégias separadas para que o caller possa optar por
``rule_based`` puro ou ``ml_based`` (que sobrepõe ML aos rule-based).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

import structlog

from ..models import (
    ApprovalStatus,
    RiskBand,
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)
from ..predictor import MLPredictorInterface
from .risk import RiskAssessor
from .rules import CommonRules
from .thresholds import ApprovalThresholds, DecisionConfig, ThresholdEvaluator

logger = structlog.get_logger()

# A engine pode devolver "pending" quando nenhuma regra resolve o request.
EngineDecision = Literal["approved", "rejected", "pending"]


class DecisionStrategy(str, Enum):
    """Estratégias de avaliação suportadas."""

    RULE_BASED = "rule_based"
    ML_BASED = "ml_based"
    LLM_BASED = "llm_based"  # reservado para futuro


class ApprovalDecisionEngine:
    """Engine principal de decisão de aprovações.

    Mantém INV-6 (PENDING -> APPROVED/REJECTED) ao não decidir
    automaticamente em casos ambíguos — devolve "pending" para sinalizar
    que é necessária aprovação humana.
    """

    def __init__(
        self,
        config: Optional[DecisionConfig] = None,
        common_rules: Optional[CommonRules] = None,
        risk_assessor: Optional[RiskAssessor] = None,
        threshold_evaluator: Optional[ThresholdEvaluator] = None,
    ) -> None:
        self.config = config or DecisionConfig()
        thresholds: ApprovalThresholds = self.config.thresholds
        self.common_rules = common_rules or CommonRules(thresholds=thresholds)
        self.risk_assessor = risk_assessor or RiskAssessor()
        self.threshold_evaluator = threshold_evaluator or ThresholdEvaluator(thresholds=thresholds)
        self.logger = logger.bind(component="approval_decision_engine")

    async def decide(
        self,
        request: UnifiedApprovalRequest,
        ml_predictor: Optional[MLPredictorInterface] = None,
        strategy: DecisionStrategy = DecisionStrategy.RULE_BASED,
        user_id: Optional[str] = None,  # noqa: ARG002 — kept for API parity
    ) -> tuple[EngineDecision, Optional[str], bool]:
        """Avalia ``request`` e devolve ``(decision, reason, is_auto)``.

        ``is_auto`` é ``True`` quando a decisão veio de uma regra/ML/threshold
        e não exige acção humana posterior. Quando devolve "pending" o
        caller deve abrir o fluxo de revisão manual.
        """
        if not request.plan_id:
            raise ValueError("plan_id is required")

        if request.status != ApprovalStatus.PENDING:
            self.logger.warning(
                "evaluation_non_pending",
                plan_id=request.plan_id,
                current_status=request.status,
            )
            return "rejected", f"Request already {request.status}", False

        # 1. Common rules (ex: destructive → manual)
        rule_result = self.common_rules.evaluate(request)
        if rule_result.status is not None:
            self.logger.info(
                "decision_by_common_rules",
                plan_id=request.plan_id,
                status=rule_result.status,
                reason=rule_result.reason,
            )
            # Operações destrutivas devolvem pending (não auto).
            return rule_result.status, rule_result.reason, False

        # 2. Risk score absoluto — auto-reject de alta gravidade.
        risk_assessment = self.risk_assessor.assess(request)
        if risk_assessment.decision is not None:
            self.logger.info(
                "decision_by_risk_assessor",
                plan_id=request.plan_id,
                decision=risk_assessment.decision,
                reason=risk_assessment.reason,
                risk_score=request.risk_score,
            )
            return risk_assessment.decision, risk_assessment.reason, True

        # 3. Threshold por banda.
        threshold_decision = self.threshold_evaluator.evaluate(request)
        if threshold_decision is not None:
            decision, reason = threshold_decision
            self.logger.info(
                "decision_by_threshold",
                plan_id=request.plan_id,
                decision=decision,
                reason=reason,
                risk_band=request.risk_band,
                risk_score=request.risk_score,
            )
            return decision, reason, True

        # 4. ML predictor (se autorizado e a estratégia incluir ML).
        if (
            strategy in (DecisionStrategy.ML_BASED,)
            and self.config.thresholds.enable_ml_auto_approval
            and ml_predictor is not None
            and ml_predictor.is_enabled()
            and request.risk_band != RiskBand.CRITICAL
        ):
            ml_decision = await self._evaluate_by_ml(request, ml_predictor)
            if ml_decision is not None:
                decision, reason, confidence = ml_decision
                self.logger.info(
                    "decision_by_ml",
                    plan_id=request.plan_id,
                    decision=decision,
                    reason=reason,
                    confidence=confidence,
                )
                return decision, reason, True

        # 5. Default: pendente para revisão humana.
        return "pending", "Manual approval required", False

    async def _evaluate_by_ml(
        self,
        request: UnifiedApprovalRequest,
        ml_predictor: MLPredictorInterface,
    ) -> Optional[tuple[Literal["approved", "rejected"], str, float]]:
        """Aplica o ML predictor; devolve None quando não pode decidir."""
        try:
            prediction = await ml_predictor.predict_from_text(
                intent_text=request.original_intent_text or "",
                specialist_confidence=0.5,
            )
            if not prediction:
                return None

            decision = prediction.get("decision")
            confidence = float(prediction.get("confidence", 0.0))

            if confidence < self.config.thresholds.ml_confidence_threshold:
                self.logger.debug(
                    "ml_confidence_below_threshold",
                    plan_id=request.plan_id,
                    confidence=confidence,
                    threshold=self.config.thresholds.ml_confidence_threshold,
                )
                return None

            if decision == "approve" and confidence >= 0.9:
                return (
                    "approved",
                    f"ML prediction (confidence: {confidence:.2f})",
                    confidence,
                )
            if decision == "reject":
                return (
                    "rejected",
                    f"ML prediction (confidence: {confidence:.2f})",
                    confidence,
                )

        except Exception as exc:  # pragma: no cover — defensive
            self.logger.warning(
                "ml_evaluation_failed",
                plan_id=request.plan_id,
                error=str(exc),
            )
        return None

    @staticmethod
    def build_decision(
        plan_id: str,
        decision: Literal["approved", "rejected"],
        approved_by: str,
        rejection_reason: Optional[str] = None,
        comments: Optional[str] = None,
        ml_confidence: Optional[float] = None,
        ml_model_version: Optional[str] = None,
        auto_approved: bool = False,
    ) -> UnifiedApprovalDecision:
        """Constrói um ``UnifiedApprovalDecision`` mantendo INV-3."""
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
