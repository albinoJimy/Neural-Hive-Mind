"""Modelos para delegação de tarefas a agentes especializados."""

from datetime import datetime, timezone

UTC = timezone.utc
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Tipos de agentes especializados."""

    REQUIREMENTS_ENGINEERING = "requirements-engineering"
    ARCHITECT_AGENT = "architect-agent"
    DOCUMENTATION_GENERATION = "documentation-generation"
    TEST_GENERATION = "test-generation"
    CODE_GENERATION = "code-generation"
    DEPLOYMENT_AGENT = "deployment-agent"
    OPTIMIZER_AGENTS = "optimizer-agents"
    ANALYST_AGENTS = "analyst-agents"
    SCOUT_AGENTS = "scout-agents"
    GUARD_AGENTS = "guard-agents"


class TaskStatus(str, Enum):
    """Estados de tarefas delegadas."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(str, Enum):
    """Prioridades de tarefas."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DelegatedTask(BaseModel):
    """Tarefa delegada a um agente especializado."""

    id: str = Field(..., description="ID único da tarefa")
    agent_type: AgentType = Field(..., description="Tipo de agente")
    task_type: str = Field(..., description="Tipo específico da tarefa")
    payload: dict[str, Any] = Field(default_factory=dict, description="Payload da tarefa")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Estado da tarefa")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Prioridade")

    cognitive_plan_id: str | None = Field(default=None, description="ID do plano cognitivo")
    workflow_id: str | None = Field(default=None, description="ID do workflow")
    correlation_id: str | None = Field(default=None, description="ID de correlação")

    assigned_at: datetime | None = Field(default=None, description="Data de atribuição")
    started_at: datetime | None = Field(default=None, description="Data de início")
    completed_at: datetime | None = Field(default=None, description="Data de conclusão")

    result: dict[str, Any] | None = Field(default=None, description="Resultado da tarefa")
    error: str | None = Field(default=None, description="Mensagem de erro")
    retry_count: int = Field(default=0, description="Número de tentativas")
    max_retries: int = Field(default=3, description="Máximo de tentativas")

    timeout_seconds: int = Field(default=300, description="Timeout em segundos")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Data de criação"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Data de atualização"
    )


class DelegationRequest(BaseModel):
    """Request para delegar tarefa."""

    agent_type: AgentType = Field(..., description="Tipo de agente")
    task_type: str = Field(..., description="Tipo específico da tarefa")
    payload: dict[str, Any] = Field(default_factory=dict, description="Payload da tarefa")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Prioridade")
    timeout_seconds: int = Field(default=300, description="Timeout em segundos")

    cognitive_plan_id: str | None = Field(default=None, description="ID do plano cognitivo")
    workflow_id: str | None = Field(default=None, description="ID do workflow")
    correlation_id: str | None = Field(default=None, description="ID de correlação")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class DelegationResponse(BaseModel):
    """Response de delegação."""

    task_id: str = Field(..., description="ID da tarefa criada")
    status: TaskStatus = Field(..., description="Estado da tarefa")
    agent_type: AgentType = Field(..., description="Tipo de agente")
    estimated_duration_seconds: int | None = Field(default=None, description="Duração estimada")


class AgentCapabilities(BaseModel):
    """Capacidades de um agente."""

    agent_type: AgentType = Field(..., description="Tipo de agente")
    endpoint: str = Field(..., description="Endpoint do agente")
    available_tasks: list[str] = Field(default_factory=list, description="Tarefas disponíveis")
    max_concurrent_tasks: int = Field(default=10, description="Máximo de tarefas concorrentes")
    avg_duration_seconds: int = Field(default=60, description="Duração média em segundos")
    is_healthy: bool = Field(default=True, description="Agente saudável")


class DelegationMetrics(BaseModel):
    """Métricas de delegação."""

    total_tasks: int = Field(default=0, description="Total de tarefas")
    pending_tasks: int = Field(default=0, description="Tarefas pendentes")
    in_progress_tasks: int = Field(default=0, description="Tarefas em progresso")
    completed_tasks: int = Field(default=0, description="Tarefas completadas")
    failed_tasks: int = Field(default=0, description="Tarefas falhadas")

    avg_duration_seconds: float = Field(default=0.0, description="Duração média em segundos")
    success_rate: float = Field(default=1.0, description="Taxa de sucesso (0-1)")

    by_agent_type: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="Métricas por tipo de agente"
    )
