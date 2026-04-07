import hashlib
import json
from enum import Enum
from typing import Any

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
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CausalAnalysis(BaseModel):
    """Causal analysis evidence."""

    method: str = Field(default="", description="Causal analysis method used")
    root_cause: str = Field(default="", description="Root cause identified")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Alias for confidence")
    confounders: list[str] = Field(default_factory=list, description="Identified confounders")
    contributing_factors: list[str] = Field(
        default_factory=list, description="Contributing factors"
    )
    effect_size: float = Field(default=0.0, description="Effect size of causal relationship")


class Adjustment(BaseModel):
    """Parameter adjustment."""

    parameter_name: str = Field(default="", description="Name of adjusted parameter")
    parameter: str = Field(default="", description="Alias for parameter_name")
    old_value: str = Field(default="", description="Previous value")
    previous_value: float = Field(default=0.0, description="Previous value as float")
    new_value: str = Field(default="", description="New value")
    justification: str = Field(default="", description="Justification for adjustment")


class RollbackPlan(BaseModel):
    """Rollback plan for optimization."""

    rollback_strategy: str = Field(..., description="Strategy for rollback")
    rollback_steps: list[str] = Field(default_factory=list, description="Steps to rollback")
    validation_criteria: list[str] = Field(
        default_factory=list, description="Criteria to validate rollback"
    )


class OptimizationEvent(BaseModel):
    """Optimization event model matching Avro schema."""

    optimization_id: str = Field(..., description="Unique identifier (UUID)")
    version: str = Field(default="1.0.0", description="Schema version")
    correlation_id: str = Field(default="", description="Correlation ID for tracing")
    trace_id: str = Field(default="", description="OpenTelemetry trace ID")
    span_id: str = Field(default="", description="OpenTelemetry span ID")
    optimization_type: OptimizationType = Field(..., description="Type of optimization")
    target_component: str = Field(default="", description="Target component")
    experiment_id: str | None = Field(None, description="Reference to experiment")
    hypothesis: str = Field(default="", description="Hypothesis that was tested")
    baseline_metrics: dict[str, float] = Field(
        default_factory=dict, description="Metrics before optimization"
    )
    optimized_metrics: dict[str, float] = Field(
        default_factory=dict, description="Metrics after optimization"
    )
    improvement_percentage: float = Field(default=0.0, description="Percentage improvement")
    causal_analysis: CausalAnalysis | None = Field(None, description="Causal analysis evidence")
    adjustments: list[Adjustment] = Field(
        default_factory=list, description="List of adjustments applied"
    )
    approval_status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING_REVIEW, description="Approval status"
    )
    approved_by: str | None = Field(None, description="Agent that approved")
    rollback_plan: str | RollbackPlan = Field(default="", description="Rollback plan")
    applied_at: int | None = Field(None, description="Timestamp (Unix millis)")
    valid_until: int | None = Field(None, description="Expiration timestamp")
    metadata: dict[str, str] = Field(default_factory=dict, description="Additional metadata")
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

    def to_avro_dict(self) -> dict[str, Any]:
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
    def from_avro_dict(cls, data: dict[str, Any]) -> "OptimizationEvent":
        """Create instance from Avro dictionary."""
        # Convert nested structures
        if "causal_analysis" in data:
            data["causal_analysis"] = CausalAnalysis(**data["causal_analysis"])
        if "adjustments" in data:
            data["adjustments"] = [Adjustment(**adj) for adj in data["adjustments"]]
        return cls(**data)
