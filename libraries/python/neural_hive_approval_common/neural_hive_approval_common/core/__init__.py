"""Core decomposition of approval decision logic.

Spec: 2026-05-01-unified-gateway-architecture, TICKET-019.

Decompõe a `ApprovalDecisionLogic` monolítica em quatro responsabilidades
separadas para permitir composição e testes isolados:

- ``ThresholdEvaluator`` (`thresholds`): aplica thresholds por risk band.
- ``RiskAssessor`` (`risk`): avalia o risco bruto (auto-reject de alta gravidade).
- ``CommonRules`` (`rules`): regras imutáveis (destrutivos exigem manual).
- ``ApprovalDecisionEngine`` (`engine`): orquestra os três acima e o
  predictor ML, expondo estratégias `rule_based`, `ml_based` (e
  `llm_based` reservada para futuro).
"""

from .engine import ApprovalDecisionEngine, DecisionStrategy
from .risk import RiskAssessment, RiskAssessor
from .rules import CommonRules, RuleResult
from .thresholds import ApprovalThresholds, DecisionConfig, ThresholdEvaluator

__all__ = [
    "ApprovalDecisionEngine",
    "ApprovalThresholds",
    "CommonRules",
    "DecisionConfig",
    "DecisionStrategy",
    "RiskAssessment",
    "RiskAssessor",
    "RuleResult",
    "ThresholdEvaluator",
]
