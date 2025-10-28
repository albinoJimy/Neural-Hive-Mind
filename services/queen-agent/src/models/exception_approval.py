from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from uuid import uuid4

from .strategic_decision import RiskAssessment


class ExceptionType(str, Enum):
    """Tipos de exceções a guardrails"""
    SECURITY_OVERRIDE = "SECURITY_OVERRIDE"
    COMPLIANCE_WAIVER = "COMPLIANCE_WAIVER"
    SLA_EXTENSION = "SLA_EXTENSION"
    RESOURCE_LIMIT_BYPASS = "RESOURCE_LIMIT_BYPASS"


class ApprovalStatus(str, Enum):
    """Status de aprovação de exceção"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExceptionApproval(BaseModel):
    """Aprovação de exceção a guardrails éticos"""

    exception_id: str = Field(default_factory=lambda: str(uuid4()), description="ID único da exceção")
    exception_type: ExceptionType = Field(..., description="Tipo de exceção")

    requested_by: str = Field(..., description="Serviço/agente solicitante")
    plan_id: str = Field(..., description="ID do plano cognitivo")
    intent_id: str = Field(default="", description="ID da intenção")

    justification: str = Field(..., description="Justificativa detalhada")
    risk_assessment: RiskAssessment = Field(..., description="Avaliação de risco")
    guardrails_affected: List[str] = Field(default_factory=list, description="Guardrails que serão violados")

    approval_status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Status de aprovação")
    approved_by: Optional[str] = Field(None, description="Decision ID do Queen Agent que aprovou")
    approved_at: Optional[datetime] = Field(None, description="Timestamp de aprovação")

    expires_at: datetime = Field(..., description="Validade da aprovação")
    conditions: List[str] = Field(default_factory=list, description="Condições para aprovação")

    audit_trail: List[Dict[str, Any]] = Field(default_factory=list, description="Histórico de mudanças")

    created_at: datetime = Field(default_factory=datetime.now, description="Data de criação")
    updated_at: datetime = Field(default_factory=datetime.now, description="Data de atualização")

    def approve(self, decision_id: str, conditions: List[str]) -> None:
        """Aprovar exceção"""
        self.approval_status = ApprovalStatus.APPROVED
        self.approved_by = decision_id
        self.approved_at = datetime.now()
        self.conditions = conditions
        self.updated_at = datetime.now()

        self.audit_trail.append({
            'action': 'approved',
            'decision_id': decision_id,
            'conditions': conditions,
            'timestamp': self.approved_at.isoformat()
        })

    def reject(self, reason: str) -> None:
        """Rejeitar exceção"""
        self.approval_status = ApprovalStatus.REJECTED
        self.updated_at = datetime.now()

        self.audit_trail.append({
            'action': 'rejected',
            'reason': reason,
            'timestamp': self.updated_at.isoformat()
        })

    def is_expired(self) -> bool:
        """Verificar se exceção expirou"""
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serializar para MongoDB"""
        data = self.model_dump()

        # Converter enums para strings
        data['exception_type'] = self.exception_type.value
        data['approval_status'] = self.approval_status.value

        # Converter datetimes para ISO strings
        data['expires_at'] = self.expires_at.isoformat()
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()

        if self.approved_at:
            data['approved_at'] = self.approved_at.isoformat()

        return data
