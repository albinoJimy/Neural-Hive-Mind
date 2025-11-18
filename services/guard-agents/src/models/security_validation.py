"""
Modelos Pydantic para validação proativa de segurança de execution tickets.
"""

from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
import hashlib
import json
import uuid


class ViolationType(str, Enum):
    """Tipos de violações de segurança detectadas."""
    SECRET_EXPOSED = "SECRET_EXPOSED"
    RBAC_VIOLATION = "RBAC_VIOLATION"
    COMPLIANCE_BREACH = "COMPLIANCE_BREACH"
    ETHICAL_CONCERN = "ETHICAL_CONCERN"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class ValidationStatus(str, Enum):
    """Status da validação de segurança."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class ValidatorType(str, Enum):
    """Tipos de validadores de segurança."""
    OPA_POLICY = "OPA_POLICY"
    RBAC = "RBAC"
    SECRETS_SCAN = "SECRETS_SCAN"
    COMPLIANCE = "COMPLIANCE"
    GUARDRAIL = "GUARDRAIL"


class Severity(str, Enum):
    """Níveis de severidade."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GuardrailViolation(BaseModel):
    """Representa uma violação de guardrail de segurança."""

    violation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    violation_type: ViolationType
    severity: Severity
    description: str
    remediation_suggestion: str
    detected_by: str
    evidence: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "violation_id": "viol-123e4567-e89b-12d3-a456-426614174000",
                "violation_type": "SECRET_EXPOSED",
                "severity": "CRITICAL",
                "description": "AWS access key detectado nos parâmetros do ticket",
                "remediation_suggestion": "Remover credenciais hardcoded e usar Vault para secrets",
                "detected_by": "TrivyScanner",
                "evidence": {
                    "secret_type": "aws-access-key",
                    "location": "parameters.aws_credentials",
                    "pattern_matched": "AKIA[0-9A-Z]{16}"
                }
            }
        }
    )

    def to_dict(self) -> dict:
        """Converte a violação para dicionário."""
        return {
            "violation_id": self.violation_id,
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "remediation_suggestion": self.remediation_suggestion,
            "detected_by": self.detected_by,
            "evidence": self.evidence
        }


class RiskAssessment(BaseModel):
    """Avaliação de risco calculada para o ticket."""

    risk_score: float = Field(ge=0.0, le=1.0, description="Score de risco normalizado (0-1)")
    severity: Severity
    impact: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "risk_score": 0.85,
                "severity": "HIGH",
                "impact": "Exposição de credenciais pode comprometer infraestrutura AWS"
            }
        }
    )


class SecurityValidation(BaseModel):
    """Resultado da validação proativa de segurança de um ExecutionTicket."""

    validation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticket_id: str
    plan_id: str
    intent_id: str
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    validated_at: datetime = Field(default_factory=datetime.utcnow)
    validation_status: ValidationStatus
    validator_type: ValidatorType
    violations: List[GuardrailViolation] = Field(default_factory=list)
    risk_assessment: RiskAssessment
    approval_required: bool = False
    approval_reason: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    hash: str = ""
    schema_version: int = 1

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "validation_id": "val-123e4567-e89b-12d3-a456-426614174000",
                "ticket_id": "ticket-123",
                "plan_id": "plan-456",
                "intent_id": "intent-789",
                "correlation_id": "corr-abc",
                "validated_at": "2025-11-17T10:30:00Z",
                "validation_status": "REJECTED",
                "validator_type": "SECRETS_SCAN",
                "violations": [],
                "risk_assessment": {
                    "risk_score": 0.95,
                    "severity": "CRITICAL",
                    "impact": "Credenciais expostas"
                },
                "approval_required": False,
                "metadata": {"validator_version": "1.0.0"},
                "hash": "abc123...",
                "schema_version": 1
            }
        }
    )

    def calculate_hash(self) -> str:
        """
        Calcula hash SHA-256 dos campos críticos para auditoria.

        Returns:
            Hash hexadecimal dos campos críticos
        """
        critical_fields = {
            "validation_id": self.validation_id,
            "ticket_id": self.ticket_id,
            "validated_at": self.validated_at.isoformat(),
            "validation_status": self.validation_status.value,
            "violations": [v.to_dict() for v in self.violations],
            "risk_assessment": {
                "risk_score": self.risk_assessment.risk_score,
                "severity": self.risk_assessment.severity.value
            }
        }

        hash_input = json.dumps(critical_fields, sort_keys=True)
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def refresh_hash(self) -> None:
        """
        Recalcula e atualiza o hash após mutações nos campos críticos.

        Deve ser chamado após qualquer alteração em:
        - violations
        - risk_assessment
        - validation_status
        """
        self.hash = self.calculate_hash()

    def to_avro_dict(self) -> dict:
        """
        Converte para dicionário compatível com schema Avro.

        Returns:
            Dicionário formatado para serialização Avro
        """
        return {
            "validation_id": self.validation_id,
            "ticket_id": self.ticket_id,
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "validated_at": int(self.validated_at.timestamp() * 1000),
            "validation_status": self.validation_status.value,
            "validator_type": self.validator_type.value,
            "violations": [v.to_dict() for v in self.violations],
            "risk_assessment": {
                "risk_score": self.risk_assessment.risk_score,
                "severity": self.risk_assessment.severity.value,
                "impact": self.risk_assessment.impact
            },
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "metadata": self.metadata,
            "hash": self.hash,
            "schema_version": self.schema_version
        }

    @classmethod
    def from_avro_dict(cls, data: dict) -> "SecurityValidation":
        """
        Cria instância a partir de dicionário Avro.

        Args:
            data: Dicionário deserializado do Avro

        Returns:
            Instância de SecurityValidation
        """
        # Converter timestamp millis para datetime
        validated_at = datetime.fromtimestamp(data["validated_at"] / 1000)

        # Reconstruir violations
        violations = [
            GuardrailViolation(
                violation_id=v["violation_id"],
                violation_type=ViolationType(v["violation_type"]),
                severity=Severity(v["severity"]),
                description=v["description"],
                remediation_suggestion=v["remediation_suggestion"],
                detected_by=v["detected_by"],
                evidence=v["evidence"]
            )
            for v in data.get("violations", [])
        ]

        # Reconstruir risk_assessment
        risk_data = data["risk_assessment"]
        risk_assessment = RiskAssessment(
            risk_score=risk_data["risk_score"],
            severity=Severity(risk_data["severity"]),
            impact=risk_data["impact"]
        )

        return cls(
            validation_id=data["validation_id"],
            ticket_id=data["ticket_id"],
            plan_id=data["plan_id"],
            intent_id=data["intent_id"],
            correlation_id=data["correlation_id"],
            trace_id=data.get("trace_id"),
            span_id=data.get("span_id"),
            validated_at=validated_at,
            validation_status=ValidationStatus(data["validation_status"]),
            validator_type=ValidatorType(data["validator_type"]),
            violations=violations,
            risk_assessment=risk_assessment,
            approval_required=data.get("approval_required", False),
            approval_reason=data.get("approval_reason"),
            metadata=data.get("metadata", {}),
            hash=data.get("hash", ""),
            schema_version=data.get("schema_version", 1)
        )

    def requires_human_approval(self) -> bool:
        """
        Determina se a validação requer aprovação humana.

        Returns:
            True se aprovação humana é necessária
        """
        # Aprovação necessária se risk_score > 0.8
        if self.risk_assessment.risk_score > 0.8:
            return True

        # Aprovação necessária se há violações CRITICAL
        critical_violations = [
            v for v in self.violations
            if v.severity == Severity.CRITICAL
        ]
        if critical_violations:
            return True

        return self.approval_required
