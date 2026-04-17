"""Bounded Context data models."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class UbiquitousLanguageTerm(BaseModel):
    """Termo da linguagem ubíqua do bounded context."""

    term: str = Field(..., description="Termo específico do domínio")
    definition: str = Field(..., description="Definição clara do termo")
    examples: List[str] = Field(default_factory=list, description="Exemplos de uso")


class BoundedContextRelationship(BaseModel):
    """Relacionamento entre bounded contexts."""

    from_context: str = Field(..., alias="from")
    to_context: str = Field(..., alias="to")
    relationship_type: str = Field(
        ...,
        description="Tipo de relacionamento: partnership, shared_kernel, etc."
    )
    direction: Optional[str] = Field(
        None,
        description="Direção do relacionamento: incoming, outgoing, bidirectional"
    )
    description: Optional[str] = Field(None, description="Descrição da integração")


class BoundedContext(BaseModel):
    """Bounded Context (DDD)."""

    name: str = Field(..., description="Nome do contexto (ex: Identity, Billing)")
    description: str = Field(..., description="Descrição do propósito do contexto")
    responsibilities: List[str] = Field(
        ...,
        description="Lista de responsabilidades deste contexto"
    )
    domain_models: List[str] = Field(
        ...,
        description="Lista de modelos de domínio principais"
    )
    relationships: List[BoundedContextRelationship] = Field(
        default_factory=list,
        description="Relacionamentos com outros contextos"
    )
    ubiquitous_language: List[UbiquitousLanguageTerm] = Field(
        default_factory=list,
        description="Termos específicos do domínio"
    )
    is_external: bool = Field(
        default=False,
        description="Indica se este contexto é externo ao sistema (e.g., terceiros)"
    )

    class Config:
        populate_by_name = True


class BoundedContextsAnalysis(BaseModel):
    """Resultado da análise de bounded contexts."""

    contexts: List[BoundedContext]
    total_contexts: int = Field(..., ge=1)
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
