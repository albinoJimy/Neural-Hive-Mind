"""
Neural Hive Risk Scoring Library

Biblioteca reutilizável para avaliação de risco multi-domínio.
Suporta domínios: Business, Technical, Security, Operational, Compliance.
"""

from neural_hive_domain import UnifiedDomain

from .alerts import (
    AlertHandler,
    AlertRule,
    AlertSeverity,
    AlertType,
    CallbackAlertHandler,
    LoggingAlertHandler,
    RiskAlert,
    RiskAlertManager,
)
from .calculator import AggregationStrategy, RiskCalculator
from .config import RiskBand, RiskScoringConfig
from .engine import RiskScoringEngine, RiskScoringMetrics
from .ensemble import EnsembleMethod, EnsembleResult, RiskEnsemble, RiskModel
from .explainability import FactorContribution, RiskExplainability, RiskExplanation, WhatIfScenario
from .history import AnomalyDetection, RiskHistory, RiskSnapshot, TrendAnalysis, TrendDirection
from .models import RiskAssessment, RiskFactor, RiskMatrix
from .thresholds import (
    DynamicThresholds,
    ThresholdAdjustmentStrategy,
    ThresholdMonitor,
    ThresholdViolation,
)
from .utils import get_domain_enum, get_domain_value

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
