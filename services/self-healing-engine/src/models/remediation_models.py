from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_APPROVAL = "MANUAL_APPROVAL"


class RemediationRequest(BaseModel):
    remediation_id: Optional[str] = Field(default=None, description="Optional remediation ID (UUID). If not provided, it will be generated.")
    incident_id: str = Field(..., description="ID do incidente que originou a remediação")
    playbook_name: str = Field(..., description="Nome do playbook a executar")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros dinâmicos para execução")
    execution_mode: ExecutionMode = Field(default=ExecutionMode.AUTOMATIC, description="Modo de execução (automático ou aguardando aprovação)")


class RemediationResponse(BaseModel):
    remediation_id: str
    status: str
    started_at: Optional[str] = None
    message: Optional[str] = None


class RemediationStatusResponse(BaseModel):
    remediation_id: str
    status: str
    progress: float = 0.0
    actions_completed: int = 0
    total_actions: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
