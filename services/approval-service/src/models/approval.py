"""
Modelos de Dados Específicos do Approval Service API.

Este módulo contém apenas modelos específicos da API do approval-service
que não fazem parte do Approval Core Package (neural_hive_approval_common).

Os modelos compartilhados (ApprovalRequest, ApprovalDecision, RiskBand, etc.)
foram movidos para neural_hive_approval_common e são importados via __init__.py.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApprovalResponse(BaseModel):
    """Response de aprovacao para Kafka"""

    plan_id: str = Field(..., description="ID do plano")
    intent_id: str = Field(..., description="ID da intent")
    decision: str = Field(..., description="Decisao (approved/rejected)")
    approved_by: str = Field(..., description="ID do usuario que decidiu")
    approved_at: datetime = Field(..., description="Timestamp da decisao")
    rejection_reason: Optional[str] = Field(None, description="Motivo da rejeicao")
    cognitive_plan: Optional[dict[str, Any]] = Field(
        None, description="Plano completo (se aprovado)"
    )

    def to_kafka_dict(self) -> dict[str, Any]:
        """Converte para dicionario compativel com Kafka/Avro"""
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


class ApprovalDecisionResponse(BaseModel):
    """Response HTTP da decisao de aprovacao/rejeicao (exclusivo do approval-service).

    Espelha os campos de UnifiedApprovalDecision (neural_hive_approval_common)
    e adiciona um campo 'status' top-level coerente com 'decision'
    ('approved'/'rejected'). Resolve clientes que esperam '.status' na resposta
    de POST /api/v1/approvals/{plan_id}/approve sem alterar o modelo partilhado
    nem o contrato Kafka (INV-3/INV-4 preservados).
    """

    plan_id: str = Field(..., description="ID do plano")
    decision: str = Field(..., description="Decisao (approved/rejected)")
    status: str = Field(..., description="Status coerente com a decisao (approved/rejected)")
    approved_by: str = Field(..., description="ID do usuario que decidiu")
    approved_at: datetime = Field(..., description="Timestamp da decisao")
    rejection_reason: Optional[str] = Field(None, description="Motivo da rejeicao")
    comments: Optional[str] = Field(None, description="Comentarios adicionais")
    ml_confidence: Optional[float] = Field(None, description="Confianca do modelo ML na decisao")
    ml_model_version: Optional[str] = Field(
        None, description="Versao do modelo ML usado (se aplicavel)"
    )
    auto_approved: bool = Field(default=False, description="Se foi aprovacao automatica via ML")

    @classmethod
    def from_decision(cls, decision: Any) -> "ApprovalDecisionResponse":
        """Constroi a resposta a partir de um UnifiedApprovalDecision.

        Define 'status' a partir de 'decision', preservando os restantes campos.
        """
        return cls(
            plan_id=decision.plan_id,
            decision=decision.decision,
            status=decision.decision,
            approved_by=decision.approved_by,
            approved_at=decision.approved_at,
            rejection_reason=decision.rejection_reason,
            comments=decision.comments,
            ml_confidence=decision.ml_confidence,
            ml_model_version=decision.ml_model_version,
            auto_approved=decision.auto_approved,
        )


# NOTE: Os seguintes modelos são importados de neural_hive_approval_common:
# - ApprovalRequest (UnifiedApprovalRequest)
# - ApprovalDecision (UnifiedApprovalDecision)
# - ApprovalStatus
# - RiskBand
# - ApproveRequestBody
# - RejectRequestBody
# - RevertRequestBody
# - RevertResponse
# - ApprovalStats
# - PendingApprovalsQuery

# Apenas modelos exclusivos do approval-service permanecem neste arquivo:


class RepublishRequestBody(BaseModel):
    """Body do request de republicacao - exclusivo do approval-service"""

    force: bool = Field(
        default=False, description="Forcar republicacao mesmo se houver inconsistencias"
    )
    comments: Optional[str] = Field(None, description="Comentarios sobre a republicacao")
