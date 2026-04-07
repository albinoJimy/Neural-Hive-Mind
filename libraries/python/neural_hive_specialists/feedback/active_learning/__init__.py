"""
Active Learning module for feedback collection.

Este módulo fornece funcionalidades de Active Learning para coletar
feedbacks de forma estratégica, maximizando o valor informacional de
cada amostra coletada.
"""

from .balance_analyzer import DatasetBalanceAnalyzer, BalanceMetrics, PriorityRecommendation
from .learning_strategy import (
    ActiveLearningStrategy,
    InformationValue,
    DEFAULT_CONFIDENCE_WEIGHT,
    DEFAULT_REPRESENTATION_WEIGHT,
    DEFAULT_NOVELTY_WEIGHT,
    DEFAULT_THRESHOLD,
)
from .feedback_queue import (
    PriorityFeedbackQueue,
    QueuedCase,
    QueueStatus,
    DEFAULT_CLAIM_EXPIRY_HOURS,
)

__all__ = [
    "DatasetBalanceAnalyzer",
    "BalanceMetrics",
    "PriorityRecommendation",
    "ActiveLearningStrategy",
    "InformationValue",
    "DEFAULT_CONFIDENCE_WEIGHT",
    "DEFAULT_REPRESENTATION_WEIGHT",
    "DEFAULT_NOVELTY_WEIGHT",
    "DEFAULT_THRESHOLD",
    "PriorityFeedbackQueue",
    "QueuedCase",
    "QueueStatus",
    "DEFAULT_CLAIM_EXPIRY_HOURS",
]
