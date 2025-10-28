from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import json
from pydantic import BaseModel, Field, ConfigDict


class ActionType(str, Enum):
    RESTART_POD = "RESTART_POD"
    SCALE_UP = "SCALE_UP"
    SCALE_DOWN = "SCALE_DOWN"
    ROLLBACK_DEPLOYMENT = "ROLLBACK_DEPLOYMENT"
    ISOLATE_POD = "ISOLATE_POD"
    REVOKE_ACCESS = "REVOKE_ACCESS"
    APPLY_POLICY = "APPLY_POLICY"
    EXECUTE_PLAYBOOK = "EXECUTE_PLAYBOOK"


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class ExecutionMode(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL_APPROVAL_REQUIRED = "MANUAL_APPROVAL_REQUIRED"


class TargetEntity(BaseModel):
    entity_type: str
    entity_id: str
    entity_name: str


class ValidationCheck(BaseModel):
    check_name: str
    passed: bool
    details: Optional[str] = None


class RemediationAction(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action_id": "660e8400-e29b-41d4-a716-446655440000",
                "incident_id": "550e8400-e29b-41d4-a716-446655440000",
                "action_type": "RESTART_POD",
                "status": "PENDING",
                "playbook_name": "restart_pod"
            }
        }
    )

    # Identificação
    action_id: str
    incident_id: str
    action_type: ActionType
    status: ActionStatus

    # Rastreabilidade
    correlation_id: str
    trace_id: str
    span_id: str

    # Execução
    playbook_name: str
    playbook_version: str
    target_entities: list[TargetEntity]
    parameters: dict[str, str] = Field(default_factory=dict)
    execution_mode: ExecutionMode

    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout_ms: int = Field(gt=0)
    max_retries: int = Field(ge=0)
    retry_count: int = 0

    # Resultado
    success: Optional[bool] = None
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    metrics_before: dict[str, float] = Field(default_factory=dict)
    metrics_after: dict[str, float] = Field(default_factory=dict)

    # Validação
    validation_checks: list[ValidationCheck] = Field(default_factory=list)
    sla_restored: Optional[bool] = None
    mttd_seconds: Optional[float] = None
    mttr_seconds: Optional[float] = None

    # Auditoria
    approved_by: Optional[str] = None
    approval_timestamp: Optional[datetime] = None
    rollback_action_id: Optional[str] = None
    hash: str = ""
    schema_version: int = 1

    def calculate_hash(self) -> str:
        """Gera SHA-256 de campos críticos"""
        hash_data = {
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "action_type": self.action_type.value,
            "playbook_name": self.playbook_name,
            "created_at": self.created_at.isoformat()
        }
        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def calculate_mttd(self) -> Optional[float]:
        """Calcula MTTD se started_at disponível"""
        if self.started_at:
            return (self.started_at - self.created_at).total_seconds()
        return None

    def calculate_mttr(self) -> Optional[float]:
        """Calcula MTTR se completed_at disponível"""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_avro_dict(self) -> dict:
        """Converte para formato Avro-compatível"""
        data = self.model_dump(mode='json')
        data['action_type'] = self.action_type.value
        data['status'] = self.status.value
        data['execution_mode'] = self.execution_mode.value
        data['created_at'] = int(self.created_at.timestamp() * 1000)
        if self.started_at:
            data['started_at'] = int(self.started_at.timestamp() * 1000)
        if self.completed_at:
            data['completed_at'] = int(self.completed_at.timestamp() * 1000)
        if self.approval_timestamp:
            data['approval_timestamp'] = int(self.approval_timestamp.timestamp() * 1000)
        return data

    @classmethod
    def from_avro_dict(cls, data: dict) -> "RemediationAction":
        """Cria instância a partir de dict Avro"""
        data['created_at'] = datetime.fromtimestamp(data['created_at'] / 1000)
        if data.get('started_at'):
            data['started_at'] = datetime.fromtimestamp(data['started_at'] / 1000)
        if data.get('completed_at'):
            data['completed_at'] = datetime.fromtimestamp(data['completed_at'] / 1000)
        if data.get('approval_timestamp'):
            data['approval_timestamp'] = datetime.fromtimestamp(data['approval_timestamp'] / 1000)
        return cls(**data)
