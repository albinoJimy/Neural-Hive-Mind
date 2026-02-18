from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime


class TaskType(str, Enum):
    BUILD = 'BUILD'
    DEPLOY = 'DEPLOY'
    TEST = 'TEST'
    VALIDATE = 'VALIDATE'
    EXECUTE = 'EXECUTE'
    COMPENSATE = 'COMPENSATE'
    QUERY = 'QUERY'


class TicketStatus(str, Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    COMPENSATING = 'COMPENSATING'
    COMPENSATED = 'COMPENSATED'


class Priority(str, Enum):
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'


class RiskBand(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class SecurityLevel(str, Enum):
    PUBLIC = 'PUBLIC'
    INTERNAL = 'INTERNAL'
    CONFIDENTIAL = 'CONFIDENTIAL'
    RESTRICTED = 'RESTRICTED'


class SLA(BaseModel):
    '''Service Level Agreement'''
    deadline: int  # Unix timestamp
    timeout_ms: int
    max_retries: int

    @validator('timeout_ms')
    def validate_timeout(cls, v):
        if v <= 0:
            raise ValueError('timeout_ms must be greater than 0')
        return v

    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0:
            raise ValueError('max_retries must be >= 0')
        return v


class QoS(BaseModel):
    '''Quality of Service'''
    delivery_mode: str  # 'at-least-once', 'exactly-once', 'at-most-once'
    consistency: str  # 'eventual', 'strong'
    durability: str  # 'persistent', 'ephemeral'


class ExecutionTicket(BaseModel):
    '''Modelo Pydantic para ExecutionTicket seguindo schema Avro'''

    # Identificação
    ticket_id: str
    plan_id: str
    intent_id: str
    decision_id: str
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    # Tarefa
    task_id: str
    task_type: TaskType
    description: str
    dependencies: List[str] = Field(default_factory=list)
    status: TicketStatus = TicketStatus.PENDING
    priority: Priority = Priority.NORMAL
    risk_band: RiskBand = RiskBand.MEDIUM

    # SLA & QoS
    sla: SLA
    qos: QoS

    # Execução
    parameters: Dict[str, str] = Field(default_factory=dict)
    required_capabilities: List[str] = Field(default_factory=list)
    security_level: SecurityLevel = SecurityLevel.INTERNAL

    # Timestamps
    created_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    estimated_duration_ms: Optional[int] = None
    actual_duration_ms: Optional[int] = None

    # Retry & Error
    retry_count: int = 0
    error_message: Optional[str] = None
    compensation_ticket_id: Optional[str] = None

    # Metadata
    metadata: Dict[str, str] = Field(default_factory=dict)
    schema_version: int = 1

    @validator('ticket_id', 'plan_id', 'intent_id', 'decision_id', 'task_id')
    def validate_uuid_format(cls, v):
        '''Validar formato UUID básico'''
        if not v or len(v) < 8:
            raise ValueError(f'Invalid ID format: {v}')
        return v

    def to_dict(self) -> Dict[str, Any]:
        '''Serializar para dict'''
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionTicket':
        '''Deserializar de dict'''
        return cls(**data)
