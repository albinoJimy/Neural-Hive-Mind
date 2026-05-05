"""
Neural Hive Approval Common - Unified approval models and decision logic.

This library provides centralized approval models, decision logic, and Kafka
integration to ensure consistency across all components of the Neural Hive Mind
system that require approval workflows.

Example usage:
    from neural_hive_approval_common import (
        UnifiedApprovalRequest,
        UnifiedApprovalDecision,
        ApprovalDecisionLogic,
        ApprovalKafkaProducer,
    )

    # Create a request
    request = UnifiedApprovalRequest(
        plan_id="plan-123",
        intent_id="intent-456",
        risk_score=0.3,
        risk_band=RiskBand.LOW,
        cognitive_plan={...},
    )

    # Evaluate with decision logic
    logic = ApprovalDecisionLogic()
    decision = await logic.evaluate(request, ml_predictor=None)

    # Publish to Kafka
    producer = ApprovalKafkaProducer(settings)
    await producer.send_approval_response(decision)
"""

from .decision_logic import ApprovalDecisionLogic
from .kafka import ApprovalKafkaProducer
from .models import (
    ApprovalResponse,
    ApprovalStatus,
    ApprovalStats,
    ApproveRequestBody,
    PendingApprovalsQuery,
    RejectRequestBody,
    RevertRequestBody,
    RevertResponse,
    RiskBand,
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)
from .predictor import MLPredictor, MLPredictorInterface

__version__ = "1.0.0"

__all__ = [
    # Models
    "UnifiedApprovalRequest",
    "UnifiedApprovalDecision",
    "ApprovalRequest",  # Backward compatibility alias
    "ApprovalDecision",  # Backward compatibility alias
    "ApprovalResponse",
    "ApprovalStatus",
    "RiskBand",
    "ApproveRequestBody",
    "RejectRequestBody",
    "RevertRequestBody",
    "RevertResponse",
    "ApprovalStats",
    "PendingApprovalsQuery",
    # Decision Logic
    "ApprovalDecisionLogic",
    # Kafka Integration
    "ApprovalKafkaProducer",
    # ML Predictor Interface
    "MLPredictorInterface",
    "MLPredictor",
]

# Type aliases for backward compatibility
ApprovalRequest = UnifiedApprovalRequest
ApprovalDecision = UnifiedApprovalDecision
