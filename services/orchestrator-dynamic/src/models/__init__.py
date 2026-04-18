"""Módulo de modelos de dados."""

from .agentic_delegation import (
    AgentCapabilities,
    AgentType,
    DelegatedTask,
    DelegationMetrics,
    DelegationRequest,
    DelegationResponse,
    TaskPriority,
    TaskStatus,
)
from .execution_ticket import (
    SLA,
    Consistency,
    DeliveryMode,
    Durability,
    ExecutionTicket,
    Priority,
    QoS,
    RiskBand,
    SecurityLevel,
    TaskType,
    TicketStatus,
)
from .workflow import (
    CutoverConfig,
    CutoverEvent,
    CutoverMetrics,
    CutoverPhase,
    CutoverStatus,
    RollbackReason,
)

__all__ = [
    "SLA",
    "Consistency",
    "DeliveryMode",
    "Durability",
    "ExecutionTicket",
    "Priority",
    "QoS",
    "RiskBand",
    "SecurityLevel",
    "TaskType",
    "TicketStatus",
    # Cutover models
    "CutoverConfig",
    "CutoverEvent",
    "CutoverMetrics",
    "CutoverPhase",
    "CutoverStatus",
    "RollbackReason",
    # Agentic delegation models
    "AgentCapabilities",
    "AgentType",
    "DelegatedTask",
    "DelegationMetrics",
    "DelegationRequest",
    "DelegationResponse",
    "TaskPriority",
    "TaskStatus",
]
