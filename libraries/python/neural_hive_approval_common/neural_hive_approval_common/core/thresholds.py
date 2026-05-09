"""Threshold-based evaluation of approval requests.

Extraído de ``decision_logic.ApprovalDecisionLogic._evaluate_by_risk_threshold``
para satisfazer TICKET-019 (separação de responsabilidades).
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..models import RiskBand, UnifiedApprovalRequest


@dataclass
class ApprovalThresholds:
    """Configuração de thresholds para decisão automática (R-A2).

    Auto-approve thresholds são por risk band; CRITICAL nunca aprova
    automaticamente.
    """

    auto_approve_max_risk_low: float = 0.3
    auto_approve_max_risk_medium: float = 0.2
    auto_approve_max_risk_high: float = 0.1

    ml_confidence_threshold: float = 0.8
    require_manual_for_destructive: bool = True
    enable_ml_auto_approval: bool = False


class DecisionConfig(BaseModel):
    """Configuração agregada para a engine de decisão."""

    thresholds: ApprovalThresholds = Field(default_factory=ApprovalThresholds)

    @field_validator("thresholds", mode="before")
    @classmethod
    def validate_thresholds(cls, v: Any) -> ApprovalThresholds:
        if isinstance(v, dict):
            return ApprovalThresholds(**v)
        if isinstance(v, ApprovalThresholds):
            return v
        return ApprovalThresholds()


ThresholdDecision = tuple[Literal["approved", "rejected"], str]


class ThresholdEvaluator:
    """Avalia um request contra os thresholds por risk band.

    Não toma decisões de risco bruto (ver ``RiskAssessor``) nem aplica
    regras imutáveis (ver ``CommonRules``). Devolve ``None`` quando não
    consegue auto-decidir — o engine cai para o próximo handler.
    """

    def __init__(self, thresholds: Optional[ApprovalThresholds] = None) -> None:
        self.thresholds = thresholds or ApprovalThresholds()

    def evaluate(
        self, request: UnifiedApprovalRequest
    ) -> Optional[ThresholdDecision]:
        """Decide com base no par (risk_band, risk_score).

        Retorna ``None`` se a banda for CRITICAL ou se nenhum threshold
        for cumprido — nesses casos a decisão deve ser manual ou
        delegada a outro avaliador.
        """
        risk = request.risk_score
        band = request.risk_band

        if band == RiskBand.CRITICAL:
            return None

        if band == RiskBand.LOW and risk <= self.thresholds.auto_approve_max_risk_low:
            return "approved", f"Low risk ({risk:.2f}) below threshold"

        if (
            band == RiskBand.MEDIUM
            and risk <= self.thresholds.auto_approve_max_risk_medium
        ):
            return "approved", f"Medium risk ({risk:.2f}) below threshold"

        if band == RiskBand.HIGH and risk <= self.thresholds.auto_approve_max_risk_high:
            return "approved", f"High risk ({risk:.2f}) below threshold"

        return None
