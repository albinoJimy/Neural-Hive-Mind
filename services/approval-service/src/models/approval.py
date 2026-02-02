"""
Modelos de Dados para Aprovacao de Planos Cognitivos

Define os modelos Pydantic para o fluxo de aprovacao de planos.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field


class RiskBand(str, Enum):
    """Bandas de classificacao de risco"""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class ApprovalStatus(str, Enum):
    """Status de aprovacao"""
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class ApprovalRequest(BaseModel):
    """Request de aprovacao recebido do Kafka"""

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = Field(..., description='ID do plano cognitivo')
    intent_id: str = Field(..., description='ID da intent original')
    risk_score: float = Field(..., ge=0.0, le=1.0, description='Score de risco (0-1)')
    risk_band: RiskBand = Field(..., description='Banda de risco')
    is_destructive: bool = Field(default=False, description='Se contem operacoes destrutivas')
    destructive_tasks: List[str] = Field(
        default_factory=list,
        description='IDs das tasks destrutivas'
    )
    risk_matrix: Optional[Dict[str, float]] = Field(
        None,
        description='Matriz de risco multi-dominio'
    )
    status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING,
        description='Status atual da aprovacao'
    )
    requested_at: datetime = Field(
        default_factory=datetime.utcnow,
        description='Timestamp do request'
    )
    approved_by: Optional[str] = Field(None, description='ID do usuario que aprovou')
    approved_at: Optional[datetime] = Field(None, description='Timestamp da aprovacao')
    rejection_reason: Optional[str] = Field(None, description='Motivo da rejeicao')
    comments: Optional[str] = Field(None, description='Comentarios adicionais')
    cognitive_plan: Dict[str, Any] = Field(
        ...,
        description='Dados completos do plano cognitivo'
    )

    class Config:
        use_enum_values = True


class ApprovalDecision(BaseModel):
    """Decisao de aprovacao/rejeicao"""

    plan_id: str = Field(..., description='ID do plano')
    decision: Literal['approved', 'rejected'] = Field(..., description='Decisao')
    approved_by: str = Field(..., description='ID do usuario que decidiu')
    approved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description='Timestamp da decisao'
    )
    rejection_reason: Optional[str] = Field(None, description='Motivo da rejeicao')
    comments: Optional[str] = Field(None, description='Comentarios adicionais')


class ApprovalResponse(BaseModel):
    """Response de aprovacao para Kafka"""

    plan_id: str = Field(..., description='ID do plano')
    intent_id: str = Field(..., description='ID da intent')
    decision: Literal['approved', 'rejected'] = Field(..., description='Decisao')
    approved_by: str = Field(..., description='ID do usuario que decidiu')
    approved_at: datetime = Field(..., description='Timestamp da decisao')
    rejection_reason: Optional[str] = Field(None, description='Motivo da rejeicao')
    cognitive_plan: Optional[Dict[str, Any]] = Field(
        None,
        description='Plano completo (se aprovado)'
    )

    def to_kafka_dict(self) -> Dict[str, Any]:
        """Converte para dicionario compativel com Kafka/Avro"""
        import json
        return {
            'plan_id': self.plan_id,
            'intent_id': self.intent_id,
            'decision': self.decision,
            'approved_by': self.approved_by,
            'approved_at': int(self.approved_at.timestamp() * 1000),
            'rejection_reason': self.rejection_reason,
            'cognitive_plan_json': json.dumps(self.cognitive_plan, default=str) if self.cognitive_plan else None
        }


class ApprovalStats(BaseModel):
    """Estatisticas de aprovacao"""

    pending_count: int = Field(..., description='Quantidade pendente')
    approved_count: int = Field(..., description='Quantidade aprovada')
    rejected_count: int = Field(..., description='Quantidade rejeitada')
    avg_approval_time_seconds: Optional[float] = Field(
        None,
        description='Tempo medio de aprovacao em segundos'
    )
    by_risk_band: Dict[str, int] = Field(
        default_factory=dict,
        description='Contagem por banda de risco'
    )


class ApproveRequestBody(BaseModel):
    """Body do request de aprovacao"""
    comments: Optional[str] = Field(None, description='Comentarios opcionais')


class RejectRequestBody(BaseModel):
    """Body do request de rejeicao"""
    reason: str = Field(..., min_length=1, description='Motivo da rejeicao (obrigatorio)')
    comments: Optional[str] = Field(None, description='Comentarios opcionais')


class RepublishRequestBody(BaseModel):
    """Body do request de republicacao"""
    force: bool = Field(
        default=False,
        description='Forcar republicacao mesmo se houver inconsistencias'
    )
    comments: Optional[str] = Field(
        None,
        description='Comentarios sobre a republicacao'
    )


class PendingApprovalsQuery(BaseModel):
    """Query params para listar aprovacoes pendentes"""
    limit: int = Field(default=50, ge=1, le=100, description='Limite de resultados')
    offset: int = Field(default=0, ge=0, description='Offset para paginacao')
    risk_band: Optional[RiskBand] = Field(None, description='Filtro por banda de risco')
    is_destructive: Optional[bool] = Field(None, description='Filtro por destrutivo')
