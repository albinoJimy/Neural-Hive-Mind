from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class ExperimentType(str, Enum):
    """Types of experiment."""

    A_B_TEST = "A_B_TEST"
    CANARY = "CANARY"
    SHADOW = "SHADOW"
    MULTI_ARMED_BANDIT = "MULTI_ARMED_BANDIT"


class RandomizationStrategy(str, Enum):
    """Randomization strategies."""

    RANDOM = "RANDOM"
    STRATIFIED = "STRATIFIED"
    BLOCKED = "BLOCKED"


class ComparisonOperator(str, Enum):
    """Comparison operators."""

    GT = "GT"
    LT = "LT"
    EQ = "EQ"
    GTE = "GTE"
    LTE = "LTE"


class SuccessCriterion(BaseModel):
    """Success criterion for experiment."""

    metric_name: str = Field(..., description="Name of the metric")
    operator: ComparisonOperator = Field(..., description="Comparison operator")
    threshold: float = Field(..., description="Threshold value")
    confidence_level: float = Field(..., ge=0.0, le=1.0, description="Required confidence level")


class Guardrail(BaseModel):
    """Safety guardrail for experiment."""

    metric_name: str = Field(..., description="Name of metric to monitor")
    max_degradation_percentage: float = Field(..., description="Max allowed degradation percentage")
    abort_threshold: float = Field(..., description="Threshold to abort experiment")


class ExperimentRequest(BaseModel):
    """Experiment request model matching Avro schema."""

    experiment_id: str = Field(..., description="Unique identifier (UUID)")
    version: str = Field(default="1.0.0", description="Schema version")
    correlation_id: str = Field(..., description="Correlation ID")
    trace_id: str = Field(..., description="OpenTelemetry trace ID")
    span_id: str = Field(..., description="OpenTelemetry span ID")
    hypothesis: str = Field(..., description="Hypothesis to test")
    objective: str = Field(..., description="Objective of experiment")
    experiment_type: ExperimentType = Field(..., description="Type of experiment")
    target_component: str = Field(..., description="Target component")
    baseline_configuration: Dict[str, str] = Field(..., description="Current configuration")
    experimental_configuration: Dict[str, str] = Field(..., description="Proposed configuration")
    success_criteria: List[SuccessCriterion] = Field(..., description="Success criteria")
    guardrails: List[Guardrail] = Field(..., description="Safety guardrails")
    traffic_percentage: float = Field(..., ge=0.0, le=1.0, description="Traffic percentage")
    duration_seconds: int = Field(..., gt=0, description="Max duration in seconds")
    sample_size: int = Field(..., gt=0, description="Required sample size")
    randomization_strategy: RandomizationStrategy = Field(..., description="Randomization strategy")
    ethical_approval_required: bool = Field(default=False, description="Ethical approval required")
    approved_by_compliance: bool = Field(default=False, description="Approved by compliance")
    rollback_on_failure: bool = Field(default=True, description="Rollback on failure")
    created_at: int = Field(..., description="Creation timestamp (Unix millis)")
    created_by: str = Field(..., description="Agent that created the experiment")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("traffic_percentage")
    @classmethod
    def validate_traffic(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Traffic percentage must be between 0.0 and 1.0")
        return v

    def to_avro_dict(self) -> Dict[str, Any]:
        """Convert to Avro-compatible dictionary."""
        data = self.model_dump()
        # Convert enums to strings
        data["experiment_type"] = self.experiment_type.value
        data["randomization_strategy"] = self.randomization_strategy.value
        # Convert nested models
        data["success_criteria"] = [sc.model_dump() for sc in self.success_criteria]
        data["guardrails"] = [g.model_dump() for g in self.guardrails]
        # Convert operator enums in success criteria
        for sc in data["success_criteria"]:
            sc["operator"] = sc["operator"] if isinstance(sc["operator"], str) else sc["operator"].value
        return data

    @classmethod
    def from_avro_dict(cls, data: Dict[str, Any]) -> "ExperimentRequest":
        """Create instance from Avro dictionary."""
        # Convert nested structures
        if "success_criteria" in data:
            data["success_criteria"] = [SuccessCriterion(**sc) for sc in data["success_criteria"]]
        if "guardrails" in data:
            data["guardrails"] = [Guardrail(**g) for g in data["guardrails"]]
        return cls(**data)

    def validate_guardrails(self) -> bool:
        """Validate guardrails consistency."""
        for guardrail in self.guardrails:
            if guardrail.max_degradation_percentage <= 0:
                return False
            if guardrail.abort_threshold <= 0:
                return False
        return True
