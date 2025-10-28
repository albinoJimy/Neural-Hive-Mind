import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class OptimizationType(str, Enum):
    """Types of optimization."""

    WEIGHT_RECALIBRATION = "WEIGHT_RECALIBRATION"
    SLO_ADJUSTMENT = "SLO_ADJUSTMENT"
    HEURISTIC_UPDATE = "HEURISTIC_UPDATE"
    POLICY_CHANGE = "POLICY_CHANGE"


class ApprovalStatus(str, Enum):
    """Approval status."""

    AUTO_APPROVED = "AUTO_APPROVED"
    QUEEN_APPROVED = "QUEEN_APPROVED"
    PENDING_REVIEW = "PENDING_REVIEW"


class CausalAnalysis(BaseModel):
    """Causal analysis evidence."""

    method: str = Field(..., description="Causal analysis method used")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    confounders: List[str] = Field(default_factory=list, description="Identified confounders")
    effect_size: float = Field(..., description="Effect size of causal relationship")


class Adjustment(BaseModel):
    """Parameter adjustment."""

    parameter_name: str = Field(..., description="Name of adjusted parameter")
    old_value: str = Field(..., description="Previous value")
    new_value: str = Field(..., description="New value")
    justification: str = Field(..., description="Justification for adjustment")


class OptimizationEvent(BaseModel):
    """Optimization event model matching Avro schema."""

    optimization_id: str = Field(..., description="Unique identifier (UUID)")
    version: str = Field(default="1.0.0", description="Schema version")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    trace_id: str = Field(..., description="OpenTelemetry trace ID")
    span_id: str = Field(..., description="OpenTelemetry span ID")
    optimization_type: OptimizationType = Field(..., description="Type of optimization")
    target_component: str = Field(..., description="Target component")
    experiment_id: Optional[str] = Field(None, description="Reference to experiment")
    hypothesis: str = Field(..., description="Hypothesis that was tested")
    baseline_metrics: Dict[str, float] = Field(..., description="Metrics before optimization")
    optimized_metrics: Dict[str, float] = Field(..., description="Metrics after optimization")
    improvement_percentage: float = Field(..., description="Percentage improvement")
    causal_analysis: CausalAnalysis = Field(..., description="Causal analysis evidence")
    adjustments: List[Adjustment] = Field(..., description="List of adjustments applied")
    approval_status: ApprovalStatus = Field(..., description="Approval status")
    approved_by: Optional[str] = Field(None, description="Agent that approved")
    rollback_plan: str = Field(..., description="Rollback plan")
    applied_at: int = Field(..., description="Timestamp (Unix millis)")
    valid_until: Optional[int] = Field(None, description="Expiration timestamp")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")
    hash: str = Field(default="", description="SHA-256 hash for integrity")
    schema_version: int = Field(default=1, description="Schema structure version")

    @field_validator("improvement_percentage")
    @classmethod
    def validate_improvement(cls, v: float) -> float:
        if v < -1.0:
            raise ValueError("Improvement percentage cannot be less than -100%")
        return v

    def calculate_hash(self) -> str:
        """Calculate SHA-256 hash of the event."""
        # Exclude hash field itself from calculation
        data = self.model_dump(exclude={"hash"})
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def to_avro_dict(self) -> Dict[str, Any]:
        """Convert to Avro-compatible dictionary."""
        data = self.model_dump()
        # Convert enums to strings
        data["optimization_type"] = self.optimization_type.value
        data["approval_status"] = self.approval_status.value
        # Convert nested models
        data["causal_analysis"] = self.causal_analysis.model_dump()
        data["adjustments"] = [adj.model_dump() for adj in self.adjustments]
        return data

    @classmethod
    def from_avro_dict(cls, data: Dict[str, Any]) -> "OptimizationEvent":
        """Create instance from Avro dictionary."""
        # Convert nested structures
        if "causal_analysis" in data:
            data["causal_analysis"] = CausalAnalysis(**data["causal_analysis"])
        if "adjustments" in data:
            data["adjustments"] = [Adjustment(**adj) for adj in data["adjustments"]]
        return cls(**data)
