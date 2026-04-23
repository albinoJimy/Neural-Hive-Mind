"""
Interfaces package for neural_hive_context.
"""

from neural_hive_context.interfaces.workflow_classifier import IWorkflowClassifier
from neural_hive_context.interfaces.pii_detector import IPIIDetector
from neural_hive_context.interfaces.context_builder import IContextBuilder
from neural_hive_context.interfaces.context_manager import IContextManager
from neural_hive_context.interfaces.active_learning import (
    IActiveLearningService,
    ActiveLearningSignal,
    ActiveLearningPriority,
)

__all__ = [
    "IWorkflowClassifier",
    "IPIIDetector",
    "IContextBuilder",
    "IContextManager",
    "IActiveLearningService",
    "ActiveLearningSignal",
    "ActiveLearningPriority",
]
