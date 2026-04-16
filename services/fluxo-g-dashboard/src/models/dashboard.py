"""Modelos de domínio para Fluxo G Dashboard."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    """Status de workflow."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    CONTINUED_AS_NEW = "continued_as_new"
    TIMED_OUT = "timed_out"


class FluxoGStage(str, Enum):
    """Etapas do Fluxo G."""

    G1_REQUIREMENTS = "g1_requirements"
    G2_DOCUMENTATION = "g2_documentation"
    G3_KNOWLEDGE_GRAPH = "g3_knowledge_graph"
    G4_APPROVALS = "g4_approvals"
    G5_RAG_ENRICHMENT = "g5_rag_enrichment"


class StageStatus(str, Enum):
    """Status de etapa."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowSummary(BaseModel):
    """Resumo de workflow."""

    workflow_id: str
    workflow_type: str = Field(default="FluxoGWorkflow")
    plan_id: Optional[str] = None
    intent_id: Optional[str] = None
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class StageProgress(BaseModel):
    """Progresso de uma etapa."""

    stage: FluxoGStage
    status: StageStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FluxoGWorkflowDetail(BaseModel):
    """Detalhes de workflow Fluxo G."""

    workflow_id: str
    plan_id: str
    intent_id: Optional[str] = None
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None

    # Progresso por etapa
    stages: List[StageProgress] = Field(default_factory=list)

    # Resultados
    requirements_result: Optional[Dict[str, Any]] = None
    documentation_result: Optional[Dict[str, Any]] = None
    knowledge_graph_result: Optional[Dict[str, Any]] = None
    approvals_result: Optional[Dict[str, Any]] = None

    # Métricas
    total_duration_seconds: Optional[float] = None
    stages_completed: int = 0
    stages_failed: int = 0


class DashboardMetrics(BaseModel):
    """Métricas do dashboard."""

    # Workflows
    total_workflows: int = 0
    running_workflows: int = 0
    completed_workflows: int = 0
    failed_workflows: int = 0

    # Por tipo
    fluxo_g_workflows: int = 0
    orchestration_workflows: int = 0

    # Médias
    avg_duration_seconds: float = 0.0
    success_rate: float = 0.0

    # Services health
    services_health: Dict[str, bool] = Field(default_factory=dict)


class ApprovalItem(BaseModel):
    """Item de aprovação para exibição."""

    request_id: str
    type: str
    title: str
    status: str
    confidence_score: float
    requires_human_review: bool
    created_at: datetime
    plan_id: Optional[str] = None


class KnowledgeGraphNode(BaseModel):
    """Nó do grafo de conhecimento."""

    id: str
    node_type: str
    name: str
    description: Optional[str] = None
    created_at: datetime
