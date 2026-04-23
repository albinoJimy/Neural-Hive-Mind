"""
Neural Hive Context Library

Biblioteca compartilhada para Context Layer do Neural Hive Mind.

Components:
- RichContext: Modelo de contexto agregado
- WorkflowClassifier: Classificação de workflow (Orchestration vs Generation)
- PIIDetector: Detecção de informações pessoais sensíveis
"""

__version__ = "0.1.0"

# Models
from neural_hive_context.models.rich_context import (
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
)

from neural_hive_context.models.workflow import (
    WorkflowType,
    WorkflowClassification,
    WorkflowSignal,
)

from neural_hive_context.models.pii import (
    PIIType,
    PIIEntity,
    PIIResult,
    PIIDetectionConfig,
    PIIRiskLevel,
)

# Interfaces
from neural_hive_context.interfaces.workflow_classifier import IWorkflowClassifier
from neural_hive_context.interfaces.pii_detector import IPIIDetector
from neural_hive_context.interfaces.context_builder import IContextBuilder

__all__ = [
    # RichContext models
    "RichContext",
    "IntentContext",
    "SystemContext",
    "TemporalContext",
    "SecurityContext",
    "ConversationContext",
    # Workflow models
    "WorkflowType",
    "WorkflowClassification",
    "WorkflowSignal",
    # PII models
    "PIIType",
    "PIIEntity",
    "PIIResult",
    "PIIDetectionConfig",
    "PIIRiskLevel",
    # Interfaces
    "IWorkflowClassifier",
    "IPIIDetector",
    "IContextBuilder",
]
