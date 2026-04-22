"""Schemas de request/response para Approval Gateway."""

from typing import Any, Optional

from pydantic import BaseModel, Field
from src.models.approval import ApprovalStatus, ApprovalType


class CreateApprovalRequest(BaseModel):
    """Request para criar solicitação de aprovação."""

    type: ApprovalType = Field(..., description="Tipo de aprovação")
    title: str = Field(..., min_length=1, max_length=200, description="Título")
    description: str = Field(..., min_length=1, description="Descrição detalhada")
    requested_by: str = Field(..., description="Solicitante")
    context: Optional[dict[str, Any]] = Field(
        default_factory=dict, description="Contexto adicional"
    )
    expires_in_hours: Optional[int] = Field(
        default=24, ge=1, le=168, description="Horas até expirar"
    )


class UpdateApprovalRequest(BaseModel):
    """Request para atualizar solicitação."""

    status: ApprovalStatus = Field(..., description="Novo status")
    feedback: Optional[str] = Field(None, description="Feedback da decisão")
    reviewed_by: str = Field(..., description="Quem está revisando")


class ApprovalResponse(BaseModel):
    """Response de aprovação."""

    request_id: str
    status: ApprovalStatus
    confidence_score: float
    reasoning: str
    approved_by: Optional[str]
    requires_human_review: bool = Field(
        default=False, description="Se True, requer intervenção humana"
    )


class ApprovalListResponse(BaseModel):
    """Response de lista de aprovações."""

    total: int
    pending: int
    items: list[dict[str, Any]]
