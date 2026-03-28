"""
Neural Hive Risk Scoring Library

Biblioteca reutilizável para avaliação de risco multi-domínio.
Suporta domínios: Business, Technical, Security, Operational, Compliance.
"""

from .utils import get_domain_value, get_domain_enum
from .config import RiskBand, RiskScoringConfig
from .models import RiskFactor, RiskAssessment, RiskMatrix
from .engine import RiskScoringEngine, RiskScoringMetrics
from .calculator import RiskCalculator, AggregationStrategy
from .thresholds import (
    DynamicThresholds,
    ThresholdAdjustmentStrategy,
    ThresholdMonitor,
    ThresholdViolation
)
from .history import (
    RiskHistory,
    RiskSnapshot,
    TrendAnalysis,
    TrendDirection,
    AnomalyDetection
)
from .explainability import (
    RiskExplainability,
    RiskExplanation,
    FactorContribution,
    WhatIfScenario
)
from .ensemble import (
    RiskEnsemble,
    RiskModel,
    EnsembleMethod,
    EnsembleResult
)
from .alerts import (
    RiskAlertManager,
    RiskAlert,
    AlertRule,
    AlertType,
    AlertSeverity,
    AlertHandler,
    LoggingAlertHandler,
    CallbackAlertHandler
)

from neural_hive_domain import UnifiedDomain

__version__ = "2.0.0"

__all__ = [
    # Core
    "RiskScoringEngine",
    "RiskScoringMetrics",
    "RiskCalculator",
    "RiskBand",
    "RiskFactor",
    "RiskAssessment",
    "RiskMatrix",
    "RiskScoringConfig",
    "UnifiedDomain",

    # Calculator
    "AggregationStrategy",

    # Thresholds
    "DynamicThresholds",
    "ThresholdAdjustmentStrategy",
    "ThresholdMonitor",
    "ThresholdViolation",

    # History
    "RiskHistory",
    "RiskSnapshot",
    "TrendAnalysis",
    "TrendDirection",
    "AnomalyDetection",

    # Explainability
    "RiskExplainability",
    "RiskExplanation",
    "FactorContribution",
    "WhatIfScenario",

    # Ensemble
    "RiskEnsemble",
    "RiskModel",
    "EnsembleMethod",
    "EnsembleResult",

    # Alerts
    "RiskAlertManager",
    "RiskAlert",
    "AlertRule",
    "AlertType",
    "AlertSeverity",
    "AlertHandler",
    "LoggingAlertHandler",
    "CallbackAlertHandler",
]
