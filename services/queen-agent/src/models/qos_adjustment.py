from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class AdjustmentType(str, Enum):
    """Tipos de ajustes de QoS"""
    INCREASE_PRIORITY = "INCREASE_PRIORITY"
    DECREASE_PRIORITY = "DECREASE_PRIORITY"
    EXTEND_DEADLINE = "EXTEND_DEADLINE"
    ALLOCATE_MORE_RESOURCES = "ALLOCATE_MORE_RESOURCES"
    PAUSE_EXECUTION = "PAUSE_EXECUTION"
    RESUME_EXECUTION = "RESUME_EXECUTION"
    CANCEL_WORKFLOW = "CANCEL_WORKFLOW"


class QoSAdjustment(BaseModel):
    """Ajuste de QoS no Orchestrator"""

    adjustment_id: str = Field(default_factory=lambda: str(uuid4()), description="ID único do ajuste")
    adjustment_type: AdjustmentType = Field(..., description="Tipo de ajuste")

    target_workflow_id: str = Field(..., description="Workflow Temporal a ajustar")
    target_plan_id: str = Field(..., description="Plano cognitivo relacionado")

    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros do ajuste")
    reason: str = Field(..., description="Motivo do ajuste")

    requested_by: str = Field(default='queen-agent', description="Quem solicitou")

    applied_at: Optional[datetime] = Field(None, description="Quando foi aplicado")
    status: str = Field(default='PENDING', description="Status da aplicação")
    error_message: Optional[str] = Field(None, description="Mensagem de erro se falhou")

    def to_grpc_request(self) -> Dict[str, Any]:
        """Converter para mensagem gRPC para Orchestrator"""
        return {
            'adjustment_id': self.adjustment_id,
            'adjustment_type': self.adjustment_type.value,
            'workflow_id': self.target_workflow_id,
            'plan_id': self.target_plan_id,
            'parameters': self.parameters,
            'reason': self.reason
        }

    def mark_applied(self) -> None:
        """Marcar como aplicado"""
        self.status = 'APPLIED'
        self.applied_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """Marcar como falho"""
        self.status = 'FAILED'
        self.error_message = error
