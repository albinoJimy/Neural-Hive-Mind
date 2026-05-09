"""
Unified Approval Models.

Define os modelos Pydantic para o fluxo de aprovacao de planos cognitivos.
Este modulo e compartilhado entre approval-service e qualquer outro serviço
que precise interagir com o sistema de aprovacao.

Mantem compatibilidade com INV-3: Approval Decision Format.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RiskBand(str, Enum):
    """Bandas de classificacao de risco."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, Enum):
    """Status de aprovacao.

    INV-6: Status transitions: PENDING -> APPROVED or PENDING -> REJECTED only.
    Once APPROVED or REJECTED, status cannot change (no reverting via normal flow).
    Revert is only allowed via Saga compensation (separate flow).

    CANCELLED e EXPIRED são estados terminais alternativos:
    - CANCELLED: requestor cancelou antes de decisão (ex: timeout do client).
    - EXPIRED: TTL excedido sem aprovação humana.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# Alias canónico exigido pela spec (TICKET-018: CommonStatus = ApprovalStatus)
CommonStatus = ApprovalStatus


class UnifiedApprovalRequest(BaseModel):
    """Request de aprovacao recebido do Kafka.

    INV-3: Compatible with existing ApprovalRequest format.
    INV-9: Preserves original_intent_text through entire pipeline for Active Learning.
    """

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = Field(..., description="ID do plano cognitivo")
    intent_id: str = Field(..., description="ID da intent original")
    original_intent_text: Optional[str] = Field(
        None, description="Texto original da intencao para análise ML"
    )
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Score de risco (0-1)")
    risk_band: RiskBand = Field(..., description="Banda de risco")
    is_destructive: bool = Field(default=False, description="Se contem operacoes destrutivas")
    destructive_tasks: list[str] = Field(
        default_factory=list, description="IDs das tasks destrutivas"
    )
    risk_matrix: Optional[dict[str, float]] = Field(
        None, description="Matriz de risco multi-dominio"
    )
    status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING, description="Status atual da aprovacao"
    )
    requested_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp do request"
    )
    approved_by: Optional[str] = Field(None, description="ID do usuario que aprovou")
    approved_at: Optional[datetime] = Field(None, description="Timestamp da aprovacao")
    rejection_reason: Optional[str] = Field(None, description="Motivo da rejeicao")
    comments: Optional[str] = Field(None, description="Comentarios adicionais")
    cognitive_plan: dict[str, Any] = Field(..., description="Dados completos do plano cognitivo")

    model_config = ConfigDict(use_enum_values=True)


class UnifiedApprovalDecision(BaseModel):
    """Decisao de aprovacao/rejeicao.

    INV-3: Must produce same ApprovalDecision format as existing approval-service.
    - decision: Literal["approved", "rejected"]
    - approved_by: str
    - approved_at: datetime
    - rejection_reason: str | None
    """

    plan_id: str = Field(..., description="ID do plano")
    decision: Literal["approved", "rejected"] = Field(..., description="Decisao")
    approved_by: str = Field(..., description="ID do usuario que decidiu")
    approved_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp da decisao"
    )
    rejection_reason: Optional[str] = Field(None, description="Motivo da rejeicao")
    comments: Optional[str] = Field(None, description="Comentarios adicionais")
    # Extended fields for ML-powered decisions
    ml_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confianca do modelo ML na decisao"
    )
    ml_model_version: Optional[str] = Field(
        None, description="Versao do modelo ML usado (se aplicavel)"
    )
    auto_approved: bool = Field(
        default=False, description="Se foi aprovacao automatica via ML"
    )


class ApprovalResponse(BaseModel):
    """Response de aprovacao para Kafka.

    INV-4: Kafka message format must remain compatible.
    Topic: plan_approvals_responses
    """

    plan_id: str = Field(..., description="ID do plano")
    intent_id: str = Field(..., description="ID da intent")
    decision: Literal["approved", "rejected"] = Field(..., description="Decisao")
    approved_by: str = Field(..., description="ID do usuario que decidiu")
    approved_at: datetime = Field(..., description="Timestamp da decisao")
    rejection_reason: Optional[str] = Field(None, description="Motivo da rejeicao")
    cognitive_plan: Optional[dict[str, Any]] = Field(
        None, description="Plano completo (se aprovado)"
    )

    def to_kafka_dict(self) -> dict[str, Any]:
        """Converte para dicionario compativel com Kafka/Avro.

        INV-4: Maintains Kafka topic contract.
        """
        import json

        return {
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "decision": self.decision,
            "approved_by": self.approved_by,
            "approved_at": int(self.approved_at.timestamp() * 1000),
            "rejection_reason": self.rejection_reason,
            "cognitive_plan_json": (
                json.dumps(self.cognitive_plan, default=str) if self.cognitive_plan else None
            ),
        }


class ApproveRequestBody(BaseModel):
    """Body do request de aprovacao."""

    comments: Optional[str] = Field(None, description="Comentarios opcionais")


class RejectRequestBody(BaseModel):
    """Body do request de rejeicao."""

    reason: str = Field(..., min_length=1, description="Motivo da rejeicao (obrigatorio)")
    comments: Optional[str] = Field(None, description="Comentarios opcionais")


class RevertRequestBody(BaseModel):
    """Body do request de reversao de aprovacao (Compensacao Saga).

    INV-6: Revert is only allowed via Saga compensation (separate flow).
    """

    reason: str = Field(..., min_length=1, description="Motivo da reversao (obrigatorio)")
    comments: Optional[str] = Field(None, description="Comentarios opcionais")
    ticket_id: Optional[str] = Field(
        None, description="ID do ticket de compensacao que originou a reversao"
    )


class RevertResponse(BaseModel):
    """Response da reversao de aprovacao."""

    approval_id: str = Field(..., description="ID da aprovacao revertida")
    plan_id: str = Field(..., description="ID do plano")
    previous_status: str = Field(..., description="Status antes da reversao")
    new_status: str = Field(..., description="Status apos a reversao")
    reverted_at: datetime = Field(default_factory=datetime.utcnow)
    reverted_by: str = Field(..., description="ID do usuario que fez a reversao")


class ApprovalStats(BaseModel):
    """Estatisticas de aprovacao."""

    pending_count: int = Field(..., description="Quantidade pendente")
    approved_count: int = Field(..., description="Quantidade aprovada")
    rejected_count: int = Field(..., description="Quantidade rejeitada")
    avg_approval_time_seconds: Optional[float] = Field(
        None, description="Tempo medio de aprovacao em segundos"
    )
    by_risk_band: dict[str, int] = Field(
        default_factory=dict, description="Contagem por banda de risco"
    )


class PendingApprovalsQuery(BaseModel):
    """Query params para listar aprovacoes pendentes."""

    limit: int = Field(default=50, ge=1, le=100, description="Limite de resultados")
    offset: int = Field(default=0, ge=0, description="Offset para paginacao")
    risk_band: Optional[RiskBand] = Field(None, description="Filtro por banda de risco")
    is_destructive: Optional[bool] = Field(None, description="Filtro por destrutivo")
