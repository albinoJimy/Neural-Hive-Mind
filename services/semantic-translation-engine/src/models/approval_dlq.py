"""
Approval DLQ Entry Model

Define o modelo Pydantic para entradas da Dead Letter Queue de aprovações.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ApprovalDLQEntry(BaseModel):
    """
    Entrada da Dead Letter Queue para planos aprovados que falharam na republicação.

    Armazena informações completas sobre a falha para análise e reprocessamento.
    """

    plan_id: str = Field(..., description='ID do plano que falhou')
    intent_id: str = Field(..., description='ID do intent original')
    failure_reason: str = Field(..., description='Mensagem de erro da última falha')
    retry_count: int = Field(default=3, description='Número de tentativas realizadas')
    original_approval_response: Dict[str, Any] = Field(
        ...,
        description='Resposta de aprovação original completa'
    )
    failed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description='Timestamp da falha final'
    )

    # Trace context para rastreabilidade
    correlation_id: Optional[str] = Field(None, description='Correlation ID')
    trace_id: Optional[str] = Field(None, description='OpenTelemetry trace ID')
    span_id: Optional[str] = Field(None, description='OpenTelemetry span ID')

    # Informações adicionais de contexto
    approved_by: Optional[str] = Field(None, description='Quem aprovou o plano')
    risk_band: Optional[str] = Field(None, description='Risk band do plano')
    is_destructive: Optional[bool] = Field(None, description='Se o plano é destrutivo')

    def to_avro_dict(self) -> Dict[str, Any]:
        """Converte para dicionário compatível com Avro"""
        return {
            'plan_id': self.plan_id,
            'intent_id': self.intent_id,
            'failure_reason': self.failure_reason,
            'retry_count': self.retry_count,
            'original_approval_response': self.original_approval_response,
            'failed_at': int(self.failed_at.timestamp() * 1000),
            'correlation_id': self.correlation_id,
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'approved_by': self.approved_by,
            'risk_band': self.risk_band,
            'is_destructive': self.is_destructive,
            'schema_version': 1
        }

    class Config:
        validate_assignment = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
