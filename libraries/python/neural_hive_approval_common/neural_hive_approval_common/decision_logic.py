"""Backward-compatible wrapper around ``core.ApprovalDecisionEngine``.

A spec 2026-05-01-unified-gateway-architecture (TICKET-019) decompôs a
lógica de decisão em ``core/`` (engine, thresholds, rules, risk). Este
módulo é mantido para preservar a API pública usada por
``approval-service`` e pelos testes existentes (``ApprovalDecisionLogic``,
``ApprovalThresholds``, ``DecisionConfig``).

Internamente delega tudo ao novo ``ApprovalDecisionEngine``.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

import structlog

from .core.engine import ApprovalDecisionEngine, DecisionStrategy
from .core.thresholds import ApprovalThresholds, DecisionConfig, ThresholdEvaluator
from .models import (
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)
from .predictor import MLPredictorInterface

logger = structlog.get_logger()


# Tipagem agora reflete a realidade: a engine pode devolver "pending"
# quando uma regra (ex: destrutivo) bloqueia decisão automática.
LogicDecision = Literal["approved", "rejected", "pending"]


__all__ = [
    "ApprovalDecisionLogic",
    "ApprovalThresholds",
    "DecisionConfig",
]


class ApprovalDecisionLogic:
    """Wrapper que delega para ``ApprovalDecisionEngine``.

    Mantém a interface histórica:
    - ``evaluate(request, ml_predictor=None, user_id=None)``
    - ``create_decision(...)``

    Novo código deve usar ``ApprovalDecisionEngine`` diretamente.
    """

    def __init__(self, config: Optional[DecisionConfig] = None) -> None:
        self.config = config or DecisionConfig()
        self.logger = logger.bind(component="approval_decision_logic")
        self._engine = ApprovalDecisionEngine(config=self.config)

    async def evaluate(
        self,
        request: UnifiedApprovalRequest,
        ml_predictor: Optional[MLPredictorInterface] = None,
        user_id: Optional[str] = None,
    ) -> tuple[LogicDecision, Optional[str], bool]:
        """Delegates to the engine using ML strategy when a predictor is provided."""
        strategy = (
            DecisionStrategy.ML_BASED if ml_predictor is not None else DecisionStrategy.RULE_BASED
        )
        return await self._engine.decide(
            request=request,
            ml_predictor=ml_predictor,
            strategy=strategy,
            user_id=user_id,
        )

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
        """Constrói uma ``UnifiedApprovalDecision`` (mantém compat. INV-3)."""
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

    # Evaluator interno exposto para testes que dependiam do método privado
    # ``_evaluate_by_risk_threshold``. Deprecated em favor do ``ThresholdEvaluator``.
    def _evaluate_by_risk_threshold(
        self, request: UnifiedApprovalRequest
    ) -> Optional[tuple[Literal["approved", "rejected"], str]]:
        return ThresholdEvaluator(thresholds=self.config.thresholds).evaluate(request)
