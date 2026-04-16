"""Modelos de domínio para entidades extraídas."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Tipo de entidade extraída."""

    FUNCTIONALITY = "functionality"
    REQUIREMENT = "requirement"
    DATA_MODEL = "data_model"
    API = "api"
    TECH_STACK = "tech_stack"
    DEPENDENCY = "dependency"


class ExtractedEntity(BaseModel):
    """Entidade extraída de um documento."""

    id: str = Field(..., description="ID único da entidade")
    type: EntityType = Field(..., description="Tipo da entidade")
    name: str = Field(..., description="Nome da entidade")
    description: str = Field(..., description="Descrição da entidade")
    source_text: str = Field(..., description="Texto original de onde foi extraída")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Grau de confiança da extração"
    )
    document_id: str = Field(..., description="ID do documento de origem")

    # Contexto da extração
    page_number: Optional[int] = Field(None, ge=1, description="Número da página")
    section: Optional[str] = Field(None, description="Seção do documento")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadados adicionais específicos do tipo"
    )

    # Timestamps
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="Data da extração")


class EntitySet(BaseModel):
    """Conjunto de entidades extraídas de um documento."""

    document_id: str = Field(..., description="ID do documento de origem")
    entities: list[ExtractedEntity] = Field(
        default_factory=list, description="Lista de entidades extraídas"
    )
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="Data da extração")

    # Contagens por tipo (calculadas)
    @property
    def functionality_count(self) -> int:
        """Número de entidades do tipo funcionalidade."""
        return sum(1 for e in self.entities if e.type == EntityType.FUNCTIONALITY)

    @property
    def requirement_count(self) -> int:
        """Número de entidades do tipo requisito."""
        return sum(1 for e in self.entities if e.type == EntityType.REQUIREMENT)

    @property
    def data_model_count(self) -> int:
        """Número de entidades do tipo modelo de dados."""
        return sum(1 for e in self.entities if e.type == EntityType.DATA_MODEL)

    @property
    def api_count(self) -> int:
        """Número de entidades do tipo API."""
        return sum(1 for e in self.entities if e.type == EntityType.API)

    @property
    def tech_stack_count(self) -> int:
        """Número de entidades do tipo tech stack."""
        return sum(1 for e in self.entities if e.type == EntityType.TECH_STACK)

    @property
    def dependency_count(self) -> int:
        """Número de entidades do tipo dependência."""
        return sum(1 for e in self.entities if e.type == EntityType.DEPENDENCY)

    @property
    def total_count(self) -> int:
        """Número total de entidades."""
        return len(self.entities)
