"""
Flow C context models for integration tracking.

Este módulo define os modelos de contexto para rastreamento de execução do Flow C,
incluindo validação robusta de campos de correlação para observabilidade distribuída.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
import uuid


class FlowCContext(BaseModel):
    """
    Context for Flow C execution.

    Mantém o contexto completo de uma execução Flow C, incluindo IDs de correlação
    para rastreamento distribuído e observabilidade end-to-end.

    Attributes:
        intent_id: ID único da intenção original
        plan_id: ID do plano cognitivo gerado
        decision_id: ID da decisão consolidada
        correlation_id: ID de correlação para tracing (gerado se ausente)
        trace_id: OpenTelemetry trace ID
        span_id: OpenTelemetry span ID
        started_at: Timestamp de início da execução
        sla_deadline: Deadline SLA para conclusão
        priority: Prioridade de execução (1-10)
        risk_band: Banda de risco (low, medium, high, critical)
    """
    intent_id: str
    plan_id: str
    decision_id: str
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="ID de correlação para tracing distribuído"
    )
    trace_id: str = Field(default="", description="OpenTelemetry trace ID")
    span_id: str = Field(default="", description="OpenTelemetry span ID")
    started_at: datetime
    sla_deadline: datetime
    priority: int = Field(default=5, ge=1, le=10)
    risk_band: str = Field(default="medium")  # low, medium, high, critical

    @field_validator('correlation_id', mode='before')
    @classmethod
    def ensure_correlation_id(cls, v):
        """
        Garante que correlation_id nunca seja None ou vazio.

        Se o valor recebido for None, string vazia ou apenas whitespace,
        gera um novo UUID para manter a rastreabilidade.
        """
        if v is None or (isinstance(v, str) and not v.strip()):
            return str(uuid.uuid4())
        return v

    @field_validator('trace_id', 'span_id', mode='before')
    @classmethod
    def ensure_string_ids(cls, v):
        """Converte None para string vazia para IDs de tracing."""
        return v if v is not None else ""

    @field_validator('risk_band', mode='before')
    @classmethod
    def normalize_risk_band(cls, v):
        """Normaliza e valida risk_band."""
        valid_bands = {'low', 'medium', 'high', 'critical'}
        if v is None:
            return 'medium'
        normalized = str(v).lower().strip()
        return normalized if normalized in valid_bands else 'medium'


class FlowCStep(BaseModel):
    """Individual step in Flow C execution."""
    step_name: str  # C1, C2, C3, C4, C5, C6
    status: str  # pending, in_progress, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    metadata: dict = {}


class FlowCResult(BaseModel):
    """Complete Flow C execution result."""
    success: bool
    steps: List[FlowCStep]
    total_duration_ms: int
    tickets_generated: int
    tickets_completed: int
    tickets_failed: int
    telemetry_published: bool
    error: Optional[str] = None
    # P3-001: SLA tracking fields
    sla_compliant: Optional[bool] = None
    sla_remaining_seconds: Optional[int] = None
    # Aproval: Indica se está aguardando aprovação humana
    awaiting_approval: Optional[bool] = None
