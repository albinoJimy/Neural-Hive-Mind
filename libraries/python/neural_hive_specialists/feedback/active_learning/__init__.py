"""
Active Learning module for feedback collection.

Este módulo fornece funcionalidades de Active Learning para coletar
feedbacks de forma estratégica, maximizando o valor informacional de
cada amostra coletada.
"""

from .balance_analyzer import BalanceMetrics, DatasetBalanceAnalyzer, PriorityRecommendation
from .feedback_queue import (
    DEFAULT_CLAIM_EXPIRY_HOURS,
    PriorityFeedbackQueue,
    QueuedCase,
    QueueStatus,
)
from .learning_strategy import (
    DEFAULT_CONFIDENCE_WEIGHT,
    DEFAULT_NOVELTY_WEIGHT,
    DEFAULT_REPRESENTATION_WEIGHT,
    DEFAULT_THRESHOLD,
    ActiveLearningStrategy,
    InformationValue,
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
