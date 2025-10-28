"""Pydantic models for Tool Selection Request and Response."""
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from src.models.tool_descriptor import ToolCategory as ToolCategoryEnum


class ArtifactType(str, Enum):
    """Artifact type enumeration."""

    CODE = "CODE"
    IAC = "IAC"
    TEST = "TEST"
    POLICY = "POLICY"
    DOCUMENTATION = "DOCUMENTATION"


class SelectionConstraints(BaseModel):
    """Constraints for tool selection."""

    max_execution_time_ms: Optional[int] = None
    max_cost_score: Optional[float] = None
    min_reputation_score: Optional[float] = None


class ToolSelectionRequest(BaseModel):
    """Tool selection request mirroring Avro schema."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    ticket_id: str
    plan_id: Optional[str] = None
    intent_id: Optional[str] = None
    decision_id: Optional[str] = None
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    artifact_type: ArtifactType
    language: str
    complexity_score: float = Field(ge=0.0, le=1.0)
    required_categories: List[str]
    constraints: SelectionConstraints = Field(default_factory=SelectionConstraints)
    context: Dict[str, str] = Field(default_factory=dict)
    preferred_tools: List[str] = Field(default_factory=list)
    excluded_tools: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    schema_version: int = 1

    @field_validator("complexity_score")
    @classmethod
    def validate_complexity_score(cls, v: float) -> float:
        """Validate complexity score is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("complexity_score must be between 0.0 and 1.0")
        return v

    @field_validator("required_categories")
    @classmethod
    def validate_categories(cls, v: List[str]) -> List[str]:
        """Validate required_categories against ToolCategory enum."""
        valid_categories = {cat.value for cat in ToolCategoryEnum}
        for category in v:
            if category not in valid_categories:
                raise ValueError(f"Invalid category: {category}. Valid: {valid_categories}")
        return v

    def calculate_hash(self) -> str:
        """Calculate SHA-256 hash for caching."""
        key_data = {
            "artifact_type": self.artifact_type.value,
            "language": self.language,
            "complexity_score": round(self.complexity_score, 2),
            "required_categories": sorted(self.required_categories),
        }
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        data["created_at"] = int(self.created_at.timestamp() * 1000)
        data["artifact_type"] = self.artifact_type.value
        return data

    @classmethod
    def from_avro(cls, avro_data: Dict) -> "ToolSelectionRequest":
        """Create from Avro deserialized data."""
        avro_data["created_at"] = datetime.fromtimestamp(avro_data["created_at"] / 1000.0)
        return cls(**avro_data)


class SelectionMethod(str, Enum):
    """Selection method enumeration."""

    GENETIC_ALGORITHM = "GENETIC_ALGORITHM"
    HEURISTIC = "HEURISTIC"
    CACHED = "CACHED"
    FALLBACK = "FALLBACK"


class SelectedTool(BaseModel):
    """Selected tool with fitness and reasoning."""

    tool_id: str
    tool_name: str
    category: str
    execution_order: int = Field(ge=1)
    fitness_score: float = Field(ge=0.0, le=1.0)
    reasoning: str


class ToolSelectionResponse(BaseModel):
    """Tool selection response mirroring Avro schema."""

    response_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    selected_tools: List[SelectedTool]
    total_fitness_score: float = Field(ge=0.0, le=1.0)
    selection_method: SelectionMethod
    generations_evolved: int = Field(ge=0)
    population_size: int = Field(ge=0)
    convergence_time_ms: int = Field(ge=0)
    alternative_combinations: List[List[str]] = Field(default_factory=list)
    reasoning_summary: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    cached: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    schema_version: int = 1

    def to_avro(self) -> Dict:
        """Convert to Avro-compatible dictionary."""
        data = self.model_dump()
        data["created_at"] = int(self.created_at.timestamp() * 1000)
        data["selection_method"] = self.selection_method.value
        data["selected_tools"] = [
            {
                "tool_id": t.tool_id,
                "tool_name": t.tool_name,
                "category": t.category,
                "execution_order": t.execution_order,
                "fitness_score": t.fitness_score,
                "reasoning": t.reasoning,
            }
            for t in self.selected_tools
        ]
        return data

    def calculate_hash(self) -> str:
        """Calculate SHA-256 hash for integrity."""
        key_data = {
            "request_id": self.request_id,
            "selected_tools": [t.tool_id for t in self.selected_tools],
            "total_fitness_score": round(self.total_fitness_score, 4),
        }
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    class Config:
        """Pydantic configuration."""

        use_enum_values = False
