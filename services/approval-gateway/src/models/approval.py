"""Modelos de domínio para Approval Gateway."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Status de uma aprovação."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalType(str, Enum):
    """Tipo de aprovação."""

    REQUIREMENT = "requirement"
    ARCHITECTURE = "architecture"
    CODE_GENERATION = "code_generation"
    DOCUMENTATION = "documentation"
    TEST_PLAN = "test_plan"


class ApprovalRequest(BaseModel):
    """Solicitação de aprovação."""

    id: str = Field(..., description="ID único da solicitação")
    type: ApprovalType = Field(..., description="Tipo de aprovação")
    title: str = Field(..., description="Título da solicitação")
    description: str = Field(..., description="Descrição detalhada")

    # Contexto da solicitação
    context: dict[str, Any] = Field(
        default_factory=dict, description="Contexto adicional (artifacts, metadados)"
    )

    # Metadados
    requested_by: str = Field(..., description="Quem solicitou")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class ApprovalDecision(BaseModel):
    """Decisão de aprovação."""

    id: str = Field(..., description="ID da decisão")
    request_id: str = Field(..., description="ID da solicitação")
    status: ApprovalStatus = Field(..., description="Decisão tomada")

    # Análise
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Grau de confiança na decisão")
    reasoning: str = Field(..., description="Raciocínio da decisão")

    # Detalhes
    approved_by: Optional[str] = Field(None, description="Quem aprovou (humano ou IA)")
    approved_at: datetime = Field(default_factory=datetime.utcnow)

    # Feedback para aprendizado
    feedback: Optional[str] = Field(None, description="Feedback adicional")
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")

    class Config:
        populate_by_name = True


class ApprovalMetrics(BaseModel):
    """Métricas de aprovações."""

    total_requests: int = 0
    pending_requests: int = 0
    approved_requests: int = 0
    rejected_requests: int = 0
    auto_approved: int = 0
    auto_rejected: int = 0
    human_approved: int = 0
    human_rejected: int = 0

    average_decision_time_seconds: float = 0.0
    average_confidence_score: float = 0.0


class ApprovalPolicy(BaseModel):
    """Política de aprovação automática."""

    id: str
    name: str
    description: str

    # Condições
    applies_to_types: list[ApprovalType] = Field(
        default_factory=list, description="Tipos de aprovação a que se aplica"
    )

    # Thresholds
    auto_approve_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confiança mínima para aprovação automática"
    )
    auto_reject_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Confiança máxima para rejeição automática"
    )
    require_human_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confiança que requer intervenção humana"
    )

    # Regras adicionais
    require_human_for_critical: bool = Field(
        default=True, description="Requer humano para itens críticos"
    )
    max_auto_approve_complexity: int = Field(
        default=5, description="Complexidade máxima para aprovação automática"
    )

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
