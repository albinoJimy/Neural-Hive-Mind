"""Common rules that gate approvals regardless of thresholds or ML.

Estas regras são imutáveis no sentido em que não são parametrizadas por
risk score nem por ML — refletem políticas operacionais (ex: operações
destrutivas exigem revisão humana).
"""

from dataclasses import dataclass
from typing import Literal, Optional

from ..models import UnifiedApprovalRequest
from .thresholds import ApprovalThresholds


@dataclass
class RuleResult:
    """Resultado da avaliação de regras comuns.

    Quando ``status == "pending"`` o engine deve interromper a avaliação
    e devolver pending sem tentar threshold/ML.
    """

    status: Optional[Literal["pending", "rejected"]]
    reason: Optional[str]


class CommonRules:
    """Regras transversais que se aplicam antes de threshold/ML."""

    def __init__(self, thresholds: Optional[ApprovalThresholds] = None) -> None:
        self.thresholds = thresholds or ApprovalThresholds()

    def evaluate(self, request: UnifiedApprovalRequest) -> RuleResult:
        """Aplica as regras na ordem em que devem bloquear o request."""
        if self.thresholds.require_manual_for_destructive and request.is_destructive:
            return RuleResult(
                status="pending",
                reason="Destructive operations require manual approval",
            )

        return RuleResult(status=None, reason=None)
