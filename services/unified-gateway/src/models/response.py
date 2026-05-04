"""Modelos de resposta unificada do Unified Gateway."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResponseStatus(str, Enum):
    """Status da resposta."""

    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class UnifiedResponse(BaseModel):
    """Resposta unificada do Unified Gateway."""

    status: ResponseStatus
    flow_type: str = Field(description="Flow type que processou o request (A-F, G, H)")
    request_id: str = Field(description="ID único do request")
    processing_time_ms: int = Field(description="Tempo de processamento em ms")

    # Conteúdo da resposta
    data: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Dados da resposta do gateway downstream"
    )
    error: str | None = Field(default=None, description="Mensagem de erro se status=error")

    # Metadados de rastreamento
    gateway_used: str | None = Field(default=None, description="Gateway que processou (para debugging)")
    trace_id: str | None = Field(default=None, description="Distributed trace ID")

    # Informações do fallback (se aplicável)
    fallback_used: bool = Field(default=False, description="Se fallback para flow alternativo foi usado")
    original_flow_type: str | None = Field(
        default=None, description="Flow type original antes do fallback"
    )

    model_config = {"extra": "ignore"}


class KafkaEvent(BaseModel):
    """Evento Kafka para rastreamento."""

    event_type: str = Field(description="Tipo do evento (request_completed, request_failed, etc)")
    request_id: str
    flow_type: str
    status: ResponseStatus
    tenant_id: str | None = None
    user_id: str | None = None
    processing_time_ms: int
    timestamp: str
    gateway_used: str | None = None
    error_message: str | None = None

    model_config = {"extra": "allow"}
