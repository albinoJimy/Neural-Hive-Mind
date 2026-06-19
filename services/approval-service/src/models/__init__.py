# models module
# Import from Approval Core Package (neural_hive_approval_common)
from neural_hive_approval_common import (
    ApprovalDecision,
    ApprovalRequest,
    ApproveRequestBody,
    ApprovalStats,
    ApprovalStatus,
    PendingApprovalsQuery,
    RejectRequestBody,
    RevertRequestBody,
    RevertResponse,
    RiskBand,
    UnifiedApprovalDecision,
    UnifiedApprovalRequest,
)

# Local imports for API-specific models unique to approval-service
from src.models.approval import (
    ApprovalDecisionResponse,
    ApprovalResponse,
    RepublishRequestBody,
)

# Type aliases for backward compatibility
ApprovalRequest = UnifiedApprovalRequest  # type: ignore
ApprovalDecision = UnifiedApprovalDecision  # type: ignore

__all__ = [
    # From Approval Core Package
    "ApprovalStatus",
    "RiskBand",
    "UnifiedApprovalDecision",
    "UnifiedApprovalRequest",
    # Backward compatibility aliases
    "ApprovalRequest",
    "ApprovalDecision",
    # Additional from Core Package
    "ApprovalStats",
    "PendingApprovalsQuery",
    "ApproveRequestBody",
    "RejectRequestBody",
    "RevertRequestBody",
    "RevertResponse",
    # Local API-specific models
    "ApprovalResponse",
    "ApprovalDecisionResponse",
    "RepublishRequestBody",
    # Continuous feedback models (EPIC 3.3)
    "ContinuousFeedbackRequest",
    "ContinuousFeedbackResponse",
    "ContinuousFeedbackStats",
    "FeedbackType",
    "TrainingDataKafkaMessage",
]

# Re-export continuous feedback models
from src.models.continuous_feedback import (
    ContinuousFeedbackRequest,
    ContinuousFeedbackResponse,
    ContinuousFeedbackStats,
    FeedbackType,
    TrainingDataKafkaMessage,
)
