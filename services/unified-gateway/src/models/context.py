"""Modelos de contexto para requisições."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TenantContext(BaseModel):
    """Contexto do tenant (organização/cliente)."""

    tenant_id: str = Field(..., min_length=1)
    name: str | None = None
    settings: dict = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class ActorType(str, Enum):
    """Tipos de ator."""

    USER = "user"
    SYSTEM = "system"
    API_KEY = "api_key"
    SERVICE = "service"


class ActorContext(BaseModel):
    """Contexto do ator (usuário/serviço)."""

    actor_id: str = Field(..., min_length=1)
    actor_type: ActorType
    permissions: list[str] = Field(default_factory=list)

    @field_validator("actor_type", mode="before")
    def parse_actor_type(cls, v):
        """Parse string para ActorType."""
        if isinstance(v, str):
            return ActorType(v.lower())
        return v


class SessionContext(BaseModel):
    """Contexto da sessão."""

    session_id: str = Field(..., min_length=1)
    actor_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    model_config = {"extra": "allow"}


class RequestContext(BaseModel):
    """Contexto da requisição."""

    request_id: str = Field(..., min_length=1)
    input_text: str | None = None
    input_files: list[str] = Field(default_factory=list)
    tenant: TenantContext | None = None
    session: SessionContext | None = None
    actor: ActorContext | None = None
    metadata: dict = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class SystemContext(BaseModel):
    """Contexto do sistema."""

    service: str = Field(default="unified-gateway")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    hostname: str | None = None
    region: str | None = None


class TemporalContext(BaseModel):
    """Contexto temporal."""

    requested_at: datetime = Field(default_factory=datetime.utcnow)
    received_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: datetime | None = None
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=1)
    )


class SecurityContext(BaseModel):
    """Contexto de segurança."""

    authenticated: bool = False
    auth_method: Literal["jwt", "api_key", "oauth2", "none"] = "none"
    permissions: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class RichContext(BaseModel):
    """Contexto rico com todas as dimensões."""

    request: RequestContext
    tenant: TenantContext | None = None
    session: SessionContext | None = None
    actor: ActorContext | None = None
    system: SystemContext = Field(default_factory=SystemContext)
    temporal: TemporalContext = Field(default_factory=TemporalContext)
    security: SecurityContext = Field(default_factory=SecurityContext)

    @classmethod
    def from_request(cls, request: RequestContext) -> "RichContext":
        """Constroi RichContext a partir de RequestContext."""
        return cls(
            request=request,
            tenant=request.tenant,
            session=request.session,
            actor=request.actor,
        )
