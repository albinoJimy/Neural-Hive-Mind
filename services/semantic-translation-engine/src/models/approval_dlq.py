"""
Approval DLQ Entry Model

Define o modelo Pydantic para entradas da Dead Letter Queue de aprovações.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_serializers import field_serializer


class ApprovalDLQEntry(BaseModel):
    """
    Entrada da Dead Letter Queue para planos aprovados que falharam na republicação.

    Armazena informações completas sobre a falha para análise e reprocessamento.
    """

    plan_id: str = Field(..., description="ID do plano que falhou")
    intent_id: str = Field(..., description="ID do intent original")
    failure_reason: str = Field(..., description="Mensagem de erro da última falha")
    retry_count: int = Field(default=3, description="Número de tentativas realizadas")
    original_approval_response: dict[str, Any] = Field(
        ..., description="Resposta de aprovação original completa"
    )
    failed_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp da falha final"
    )

    # Trace context para rastreabilidade
    correlation_id: str | None = Field(None, description="Correlation ID")
    trace_id: str | None = Field(None, description="OpenTelemetry trace ID")
    span_id: str | None = Field(None, description="OpenTelemetry span ID")

    # Informações adicionais de contexto
    approved_by: str | None = Field(None, description="Quem aprovou o plano")
    risk_band: str | None = Field(None, description="Risk band do plano")
    is_destructive: bool | None = Field(None, description="Se o plano é destrutivo")

    def to_avro_dict(self) -> dict[str, Any]:
        """Converte para dicionário compatível com Avro"""
        return {
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
            "original_approval_response": self.original_approval_response,
            "failed_at": int(self.failed_at.timestamp() * 1000),
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "approved_by": self.approved_by,
            "risk_band": self.risk_band,
            "is_destructive": self.is_destructive,
            "schema_version": 1,
        }

    model_config = ConfigDict(validate_assignment=True)

    @field_serializer("failed_at")
    @classmethod
    def serialize_datetime(cls, dt: datetime) -> str:
        """Serialize datetime to ISO format"""
        return dt.isoformat() if dt else None
