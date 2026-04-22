"""
Modelos de alertas proativos para SLA Management System.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertSeverity(str, Enum):
    """Severidade de alertas."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertChannel(str, Enum):
    """Canais de notificação."""

    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    EMAIL = "email"
    WEBHOOK = "webhook"
    ALERTMANAGER = "alertmanager"


class AlertConditionType(str, Enum):
    """Tipos de condição para alertas."""

    BUDGET_BELOW_THRESHOLD = "budget_below_threshold"
    BURN_RATE_EXCEEDS = "burn_rate_exceeds"
    SLO_VIOLATION_COUNT = "slo_violation_count"
    STATUS_CHANGE = "status_change"
    PREDICTIVE_EXHAUSTION = "predictive_exhaustion"


class AlertCondition(BaseModel):
    """Condição para disparar alerta."""

    condition_type: AlertConditionType
    threshold: float
    window_hours: Optional[int] = None

    # Filtros opcionais
    service_name: Optional[str] = None
    slo_id: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)


class AlertRule(BaseModel):
    """Regra de alerta proativo."""

    rule_id: str
    name: str
    description: Optional[str] = None
    enabled: bool = True

    # Condições
    condition: AlertCondition
    severity: AlertSeverity

    # Canais de notificação
    channels: list[AlertChannel]

    # Configurações específicas por canal
    channel_config: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Janela de cooldown (evitar spam)
    cooldown_minutes: int = Field(default=30, ge=0)

    # Metadata
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: str = "system"

    # Último disparo
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = Field(default=0)

    model_config = ConfigDict(use_enum_values=True)


class Alert(BaseModel):
    """Alerta disparado."""

    alert_id: str
    rule_id: str
    rule_name: str

    # Severidade e conteúdo
    severity: AlertSeverity
    title: str
    message: str
    details: dict[str, Any]

    # Contexto
    slo_id: Optional[str] = None
    service_name: Optional[str] = None
    triggered_at: datetime

    # Status
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    # Canais usados
    dispatched_channels: list[AlertChannel] = Field(default_factory=list)
    dispatch_errors: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class AlertDispatchRequest(BaseModel):
    """Request para despachar alerta."""

    alert: Alert
    channels: list[AlertChannel]
    channel_config: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class AlertDispatchResult(BaseModel):
    """Resultado de despacho de alerta."""

    alert_id: str
    channel: AlertChannel
    success: bool
    error_message: Optional[str] = None
    dispatched_at: datetime

    model_config = ConfigDict(use_enum_values=True)


class AlertStatistics(BaseModel):
    """Estatísticas de alertas."""

    total_rules: int
    active_rules: int
    total_alerts: int
    alerts_by_severity: dict[str, int]
    alerts_by_channel: dict[str, int]
    recent_alerts: list[Alert]

    model_config = ConfigDict(use_enum_values=True)


class SlackMessage(BaseModel):
    """Mensagem para Slack."""

    webhook_url: str
    text: str
    blocks: Optional[list[dict[str, Any]]] = None
    attachments: Optional[list[dict[str, Any]]] = None


class PagerDutyEvent(BaseModel):
    """Evento para PagerDuty."""

    routing_key: str
    event_action: str = "trigger"
    payload: dict[str, Any]
    dedup_key: Optional[str] = None


class EmailMessage(BaseModel):
    """Mensagem de email."""

    to: list[str]
    subject: str
    body: str
    is_html: bool = True


class WebhookPayload(BaseModel):
    """Payload para webhook genérico."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any]
    method: str = "POST"

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Valida URL."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v
