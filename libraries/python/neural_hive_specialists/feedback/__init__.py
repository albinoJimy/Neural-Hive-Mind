"""
Módulo de feedback e continuous learning para especialistas Neural Hive.

Este módulo implementa coleta de feedback humano, trigger de re-treinamento
e integração com pipeline MLflow para continuous learning.
"""

from .feedback_api import create_feedback_router
from .feedback_collector import FeedbackCollector, FeedbackDocument
from .retraining_trigger import RetrainingTrigger

__all__ = [
    "FeedbackCollector",
    "FeedbackDocument",
    "RetrainingTrigger",
    "create_feedback_router",
]
