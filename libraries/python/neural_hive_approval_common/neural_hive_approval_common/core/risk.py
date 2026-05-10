"""Risk assessment for approval requests.

Avalia o risco bruto independente da banda — é responsável por
decisões de auto-rejeição quando o score é catastrófico.
"""

from dataclasses import dataclass
from typing import Literal, Optional

from ..models import RiskBand, UnifiedApprovalRequest


# Acima deste score, qualquer request é auto-rejeitado independentemente
# da banda. Mantido em sync com o limiar histórico do approval-service.
AUTO_REJECT_THRESHOLD: float = 0.9


@dataclass
class RiskAssessment:
    """Resultado do assessor de risco."""

    decision: Optional[Literal["rejected"]]
    reason: Optional[str]


class RiskAssessor:
    """Decide rejeições automáticas com base no risk score absoluto."""

    def __init__(self, auto_reject_threshold: float = AUTO_REJECT_THRESHOLD) -> None:
        self.auto_reject_threshold = auto_reject_threshold

    def assess(self, request: UnifiedApprovalRequest) -> RiskAssessment:
        """Devolve uma decisão de auto-reject ou um assessment vazio."""
        if request.risk_score >= self.auto_reject_threshold:
            return RiskAssessment(
                decision="rejected",
                reason=f"Risk score ({request.risk_score:.2f}) too high",
            )
        return RiskAssessment(decision=None, reason=None)

    @staticmethod
    def classify_band(risk_score: float) -> RiskBand:
        """Heurística de bandas — útil para callers que ainda não têm band."""
        if risk_score >= 0.75:
            return RiskBand.CRITICAL
        if risk_score >= 0.5:
            return RiskBand.HIGH
        if risk_score >= 0.25:
            return RiskBand.MEDIUM
        return RiskBand.LOW
