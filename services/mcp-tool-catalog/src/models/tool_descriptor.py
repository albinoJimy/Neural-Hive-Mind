"""Pydantic models for Tool Descriptor mirroring Avro schema."""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class ToolCategory(str, Enum):
    """Tool category enumeration."""

    ANALYSIS = "ANALYSIS"
    GENERATION = "GENERATION"
    TRANSFORMATION = "TRANSFORMATION"
    VALIDATION = "VALIDATION"
    AUTOMATION = "AUTOMATION"
    INTEGRATION = "INTEGRATION"


class IntegrationType(str, Enum):
    """Integration type enumeration."""

    CLI = "CLI"
    REST_API = "REST_API"
    GRPC = "GRPC"
    LIBRARY = "LIBRARY"
    CONTAINER = "CONTAINER"


class AuthenticationMethod(str, Enum):
    """Authentication method enumeration."""

    NONE = "NONE"
    API_KEY = "API_KEY"
    OAUTH2 = "OAUTH2"
    MTLS = "MTLS"
    SPIFFE = "SPIFFE"


class ToolDescriptor(BaseModel):
    """Tool descriptor mirroring Avro schema."""

    tool_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    category: ToolCategory
    capabilities: List[str]
    version: str
    reputation_score: float = Field(ge=0.0, le=1.0)
    average_execution_time_ms: int = Field(ge=0)
    cost_score: float = Field(ge=0.0, le=1.0)
    required_parameters: Dict[str, str] = Field(default_factory=dict)
    output_format: str
    integration_type: IntegrationType
    endpoint_url: Optional[str] = None
    authentication_method: AuthenticationMethod
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    schema_version: int = 1

    @field_validator("reputation_score")
    @classmethod
    def validate_reputation_score(cls, v: float) -> float:
        """Validate reputation score is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("reputation_score must be between 0.0 and 1.0")
        return v

    @field_validator("cost_score")
    @classmethod
    def validate_cost_score(cls, v: float) -> float:
        """Validate cost score is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("cost_score must be between 0.0 and 1.0")
        return v

    def calculate_fitness(
        self, weight_reputation: float = 0.4, weight_cost: float = 0.3, weight_time: float = 0.1
    ) -> float:
        """Calculate fitness score for genetic algorithm."""
        normalized_time = min(self.average_execution_time_ms / 300000.0, 1.0)
        fitness = (
            self.reputation_score * weight_reputation
            + (1.0 - self.cost_score) * weight_cost
            + (1.0 - normalized_time) * weight_time
        )
        return max(0.0, min(fitness, 1.0))

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        data["created_at"] = int(self.created_at.timestamp() * 1000)
        data["updated_at"] = int(self.updated_at.timestamp() * 1000)
        data["category"] = self.category.value
        data["integration_type"] = self.integration_type.value
        data["authentication_method"] = self.authentication_method.value
        return data

    @classmethod
    def from_avro(cls, avro_data: Dict) -> "ToolDescriptor":
        """Create from Avro deserialized data."""
        avro_data["created_at"] = datetime.fromtimestamp(avro_data["created_at"] / 1000.0)
        avro_data["updated_at"] = datetime.fromtimestamp(avro_data["updated_at"] / 1000.0)
        return cls(**avro_data)

    class Config:
        """Pydantic configuration."""

        use_enum_values = False
        json_encoders = {datetime: lambda v: int(v.timestamp() * 1000)}
