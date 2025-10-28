from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import json
from pydantic import BaseModel, Field, ConfigDict


class IncidentType(str, Enum):
    THREAT_DETECTED = "THREAT_DETECTED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    SLA_BREACH = "SLA_BREACH"
    MTLS_FAILURE = "MTLS_FAILURE"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    CLASSIFIED = "CLASSIFIED"
    REMEDIATING = "REMEDIATING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class SourceType(str, Enum):
    PROMETHEUS = "PROMETHEUS"
    ALERTMANAGER = "ALERTMANAGER"
    KAFKA = "KAFKA"
    ISTIO = "ISTIO"
    OPA = "OPA"


class EntityType(str, Enum):
    POD = "POD"
    SERVICE = "SERVICE"
    NAMESPACE = "NAMESPACE"
    NODE = "NODE"


class DetectionSource(BaseModel):
    source_type: SourceType
    source_id: str
    alert_name: Optional[str] = None


class AffectedEntity(BaseModel):
    entity_type: EntityType
    entity_id: str
    entity_name: str


class Classification(BaseModel):
    confidence_score: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    impact_assessment: str
    recommended_playbook: Optional[str] = None


class SecurityIncident(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_id": "550e8400-e29b-41d4-a716-446655440000",
                "incident_type": "ANOMALY_DETECTED",
                "severity": "HIGH",
                "status": "DETECTED",
                "description": "High error rate detected in worker-agents service"
            }
        }
    )

    # Identificação
    incident_id: str
    incident_type: IncidentType
    severity: Severity
    status: IncidentStatus

    # Rastreabilidade
    correlation_id: str
    trace_id: str
    span_id: str
    plan_id: Optional[str] = None
    intent_id: Optional[str] = None
    ticket_id: Optional[str] = None

    # Detecção
    detected_at: datetime
    detection_source: DetectionSource
    affected_entities: list[AffectedEntity]

    # Análise
    description: str
    metrics_snapshot: dict[str, float] = Field(default_factory=dict)
    logs_sample: list[str] = Field(default_factory=list)
    threat_indicators: list[str] = Field(default_factory=list)

    # Classificação
    classification: Classification

    # Remediação
    remediation_action_id: Optional[str] = None
    playbook_executed: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_summary: Optional[str] = None

    # Auditoria
    escalated_to_human: bool = False
    escalation_reason: Optional[str] = None
    hash: str = ""
    schema_version: int = 1

    def calculate_hash(self) -> str:
        """Gera SHA-256 de campos críticos"""
        hash_data = {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type.value,
            "detected_at": self.detected_at.isoformat(),
            "affected_entities": [
                {
                    "entity_type": e.entity_type.value,
                    "entity_id": e.entity_id,
                    "entity_name": e.entity_name
                }
                for e in self.affected_entities
            ]
        }
        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def to_avro_dict(self) -> dict:
        """Converte para formato Avro-compatível"""
        data = self.model_dump(mode='json')
        # Converte enums para strings
        data['incident_type'] = self.incident_type.value
        data['severity'] = self.severity.value
        data['status'] = self.status.value
        data['detection_source']['source_type'] = self.detection_source.source_type.value
        for entity in data['affected_entities']:
            entity['entity_type'] = entity['entity_type']
        # Converte timestamps
        data['detected_at'] = int(self.detected_at.timestamp() * 1000)
        if self.resolved_at:
            data['resolved_at'] = int(self.resolved_at.timestamp() * 1000)
        return data

    @classmethod
    def from_avro_dict(cls, data: dict) -> "SecurityIncident":
        """Cria instância a partir de dict Avro"""
        # Converte timestamps
        data['detected_at'] = datetime.fromtimestamp(data['detected_at'] / 1000)
        if data.get('resolved_at'):
            data['resolved_at'] = datetime.fromtimestamp(data['resolved_at'] / 1000)
        return cls(**data)
