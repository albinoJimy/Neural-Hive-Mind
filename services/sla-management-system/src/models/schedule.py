"""
Modelos de dados para Schedule de Workflows.

Define os modelos usados pelo scheduler de workflows do SLA Management System.
Suporta schedules baseados em cron, eventos e triggers manuais.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

# UTC timezone
UTC = timezone.utc


class ScheduleType(str, Enum):
    """Tipo de schedule."""

    CRON = "cron"
    EVENT = "event"
    RESOURCE = "resource"
    MANUAL = "manual"


class ScheduleStatus(str, Enum):
    """Status do schedule."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    COMPLETED = "completed"


class SchedulePriority(str, Enum):
    """Prioridade de schedules."""

    CRITICAL = "critical"  # SLO violations, freeze triggers
    HIGH = "high"  # Remediation, policy enforcement
    MEDIUM = "medium"  # Budget recalculation
    LOW = "low"  # Reports, maintenance


class ScheduleTrigger(BaseModel):
    """Configuração de trigger para schedule."""

    cron_expression: Optional[str] = Field(
        None, description="Expressão cron (ex: '0 * * * *' para hora em hora)"
    )
    event_type: Optional[str] = Field(
        None, description="Tipo de evento (ex: 'slo.violation', 'sla.budgets')"
    )
    event_filter: Optional[Dict[str, Any]] = Field(
        None, description="Filtro para evento (ex: {'slo_id': 'slo-123'})"
    )
    resource_threshold: Optional[Dict[str, float]] = Field(
        None, description="Threshold de recurso (ex: {'cpu_percent': 80.0})"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description="Parâmetros passados para o workflow"
    )


class Schedule(BaseModel):
    """Schedule de workflow."""

    schedule_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow: str = Field(..., description="Nome do workflow Temporal")
    schedule_type: ScheduleType = Field(..., description="Tipo de schedule")
    trigger: ScheduleTrigger = Field(..., description="Configuração do trigger")
    priority: SchedulePriority = Field(
        default=SchedulePriority.MEDIUM, description="Prioridade do schedule"
    )
    status: ScheduleStatus = Field(default=ScheduleStatus.ACTIVE, description="Status do schedule")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Data de criação")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Última atualização")
    last_run_at: Optional[datetime] = Field(None, description="Última execução")
    next_run_at: Optional[datetime] = Field(None, description="Próxima execução programada")
    total_runs: int = Field(default=0, description="Número total de execuções")
    failure_count: int = Field(default=0, description="Número de falhas consecutivas")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class ScheduleExecution(BaseModel):
    """Registro de execução de um schedule."""

    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    schedule_id: str = Field(..., description="ID do schedule")
    workflow_id: str = Field(..., description="ID do workflow executado")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = Field(None)
    status: str = Field(default="running")  # running, completed, failed
    error_message: Optional[str] = Field(None)
    output: Optional[Dict[str, Any]] = Field(None)


class ScheduleCreateRequest(BaseModel):
    """Request para criação de schedule."""

    workflow: str = Field(..., description="Nome do workflow Temporal")
    schedule_type: ScheduleType = Field(..., description="Tipo de schedule")
    trigger: ScheduleTrigger = Field(..., description="Configuração do trigger")
    priority: SchedulePriority = Field(
        default=SchedulePriority.MEDIUM, description="Prioridade do schedule"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class ScheduleUpdateRequest(BaseModel):
    """Request para atualização de schedule."""

    status: Optional[ScheduleStatus] = Field(None)
    priority: Optional[SchedulePriority] = Field(None)
    trigger: Optional[ScheduleTrigger] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(None)


class ScheduleListResponse(BaseModel):
    """Response para listagem de schedules."""

    schedules: list[Schedule] = Field(default_factory=list)
    total: int = Field(default=0)
    page: int = Field(default=1)
    page_size: int = Field(default=50)


class ScheduleTriggerResponse(BaseModel):
    """Response para trigger de schedule."""

    schedule_id: str
    workflow_id: str
    triggered_at: datetime
    manual: bool = False
