"""
RichContext Models

Modelos de contexto agregado para decisão de roteamento.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class IntentContext(BaseModel):
    """Contexto derivado do intent do usuário."""

    raw_text: str = Field(..., description="Texto original do intent")
    intent_id: Optional[str] = Field(None, description="ID único do intent")
    user_id: Optional[str] = Field(None, description="ID do usuário")
    intent_type: Optional[str] = Field(None, description="Tipo de intent classificado")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Entidades extraídas")
    semantic_features: Dict[str, float] = Field(
        default_factory=dict,
        description="Features semânticas (quando disponível)"
    )


class SystemContext(BaseModel):
    """Contexto do estado do sistema."""

    affected_services: List[str] = Field(
        default_factory=list,
        description="Serviços potencialmente afetados"
    )
    service_states: Dict[str, str] = Field(
        default_factory=dict,
        description="Estado dos serviços (running, stopped, etc)"
    )
    resource_utilization: Dict[str, float] = Field(
        default_factory=dict,
        description="Utilização de recursos por serviço"
    )
    active_workflows: int = Field(
        default=0,
        description="Número de workflows ativos no sistema"
    )


class TemporalContext(BaseModel):
    """Contexto temporal."""

    current_time: str = Field(..., description="Timestamp atual ISO 8601")
    time_of_day: str = Field(
        ...,
        description="Período do dia: morning, afternoon, evening, night"
    )
    day_of_week: str = Field(..., description="Dia da semana")
    is_business_hours: bool = Field(
        default=False,
        description="Se está dentro do horário comercial"
    )


class SecurityContext(BaseModel):
    """Contexto de segurança."""

    user_id: Optional[str] = Field(None, description="ID do usuário")
    session_id: Optional[str] = Field(None, description="ID da sessão")
    risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de risco da requisição"
    )
    requires_approval: bool = Field(
        default=False,
        description="Se a operação requer aprovação humana"
    )


class ConversationContext(BaseModel):
    """Histórico conversacional simplificado."""

    conversation_id: Optional[str] = Field(None, description="ID da conversa")
    user_id: Optional[str] = Field(None, description="ID do usuário")
    turn_count: int = Field(default=0, description="Número de turnos da conversa")
    previous_intents: List[str] = Field(
        default_factory=list,
        description="Intents anteriores na sessão"
    )
    has_repetition: bool = Field(
        default=False,
        description="Se o atual intent é uma repetição"
    )
    has_escalation: bool = Field(
        default=False,
        description="Se houve escalamento para humano"
    )


class RichContext(BaseModel):
    """
    Contexto agregado para decisão de roteamento.

    Este é o modelo principal que passa pelo pipeline de decisão,
    contendo todas as dimensões de contexto relevantes.
    """

    intent: IntentContext = Field(..., description="Contexto do intent")
    system: SystemContext = Field(..., description="Contexto do sistema")
    temporal: TemporalContext = Field(..., description="Contexto temporal")
    security: SecurityContext = Field(..., description="Contexto de segurança")
    conversation: ConversationContext = Field(
        ..., description="Contexto conversacional"
    )

    # Metadata
    context_id: str = Field(..., description="ID único do contexto")
    created_at: str = Field(..., description="Timestamp de criação ISO 8601")
    ttl_seconds: int = Field(default=300, description="TTL em segundos (default 5min)")
