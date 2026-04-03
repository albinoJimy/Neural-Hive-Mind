from typing import Any

from pydantic import BaseModel, Field, field_validator

from compat import StrEnum


class TaskType(StrEnum):
    BUILD = "BUILD"
    DEPLOY = "DEPLOY"
    TEST = "TEST"
    VALIDATE = "VALIDATE"
    EXECUTE = "EXECUTE"
    COMPENSATE = "COMPENSATE"
    QUERY = "QUERY"


class TicketStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityLevel(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class SLA(BaseModel):
    """Service Level Agreement"""

    deadline: int  # Unix timestamp
    timeout_ms: int
    max_retries: int

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timeout_ms must be greater than 0")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries must be >= 0")
        return v


class QoS(BaseModel):
    """Quality of Service"""

    delivery_mode: str  # 'at-least-once', 'exactly-once', 'at-most-once'
    consistency: str  # 'eventual', 'strong'
    durability: str  # 'persistent', 'ephemeral'


class ExecutionTicket(BaseModel):
    """Modelo Pydantic para ExecutionTicket seguindo schema Avro"""

    # Identificação
    ticket_id: str
    plan_id: str
    intent_id: str
    decision_id: str
    correlation_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None

    # Tarefa
    task_id: str
    task_type: TaskType
    description: str
    dependencies: list[str] = Field(default_factory=list)
    status: TicketStatus = TicketStatus.PENDING
    priority: Priority = Priority.NORMAL
    risk_band: RiskBand = RiskBand.MEDIUM

    # SLA & QoS
    sla: SLA
    qos: QoS

    # Execução
    parameters: dict[str, str] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    security_level: SecurityLevel = SecurityLevel.INTERNAL

    # Timestamps
    created_at: int
    started_at: int | None = None
    completed_at: int | None = None
    estimated_duration_ms: int | None = None
    actual_duration_ms: int | None = None

    # Retry & Error
    retry_count: int = 0
    error_message: str | None = None
    compensation_ticket_id: str | None = None

    # Metadata
    metadata: dict[str, str] = Field(default_factory=dict)
    schema_version: int = 1

    @field_validator("ticket_id", "plan_id", "intent_id", "decision_id", "task_id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        """Validar formato UUID básico"""
        if not v or len(v) < 8:
            raise ValueError(f"Invalid ID format: {v}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Serializar para dict"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionTicket":
        """Deserializar de dict"""
        return cls(**data)
