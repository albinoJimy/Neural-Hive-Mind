"""
Módulo de feedback e continuous learning para especialistas Neural Hive.

Este módulo implementa coleta de feedback humano, trigger de re-treinamento
e integração com pipeline MLflow para continuous learning.
"""

from .feedback_collector import FeedbackCollector, FeedbackDocument
from .retraining_trigger import RetrainingTrigger
from .feedback_api import create_feedback_router

__all__ = [
    'FeedbackCollector',
    'FeedbackDocument',
    'RetrainingTrigger',
    'create_feedback_router'
]
