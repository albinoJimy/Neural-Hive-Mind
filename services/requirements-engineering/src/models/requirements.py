"""Modelos de dados para requisitos funcionais."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class RequirementPriority(str, Enum):
    """Prioridade de requisito."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequirementType(str, Enum):
    """Tipo de requisito."""

    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"


class RequirementStatus(str, Enum):
    """Status de requisito."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class Requirement(BaseModel):
    """Requisito funcional ou não-funcional."""

    id: str = Field(..., description="ID único do requisito")
    requirement_type: RequirementType = Field(
        default=RequirementType.FUNCTIONAL,
        description="Tipo do requisito"
    )
    priority: RequirementPriority = Field(
        default=RequirementPriority.MEDIUM,
        description="Prioridade do requisito"
    )
    status: RequirementStatus = Field(
        default=RequirementStatus.DRAFT,
        description="Status do requisito"
    )
    title: str = Field(..., min_length=5, max_length=200, description="Título do requisito")
    description: str = Field(
        ...,
        min_length=20,
        description="Descrição detalhada do requisito"
    )
    rationale: str = Field(
        default="",
        description="Justificativa do requisito (por que é necessário)"
    )
    acceptance_criteria_ids: List[str] = Field(
        default_factory=list,
        description="IDs dos critérios de aceitação"
    )
    user_story_ids: List[str] = Field(
        default_factory=list,
        description="IDs das user stories relacionadas"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="IDs dos requisitos dos quais depende"
    )
    conflicts: List[str] = Field(
        default_factory=list,
        description="IDs dos requisitos com os quais conflita"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags para categorização"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais"
    )
    cognitive_plan_id: Optional[str] = Field(
        None,
        description="ID do CognitivePlan de origem"
    )
    architecture_plan_id: Optional[str] = Field(
        None,
        description="ID do ArchitecturePlan relacionado"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Data de criação"
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Data da última atualização"
    )
    version: int = Field(default=1, description="Versão do requisito")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Valida formato do ID."""
        if not v.startswith("REQ-"):
            raise ValueError("ID must start with 'REQ-'")
        return v


class RequirementCreate(BaseModel):
    """DTO para criação de requisito."""

    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20)
    requirement_type: RequirementType = RequirementType.FUNCTIONAL
    priority: RequirementPriority = RequirementPriority.MEDIUM
    rationale: str = ""
    tags: List[str] = Field(default_factory=list)
    cognitive_plan_id: Optional[str] = None
    architecture_plan_id: Optional[str] = None


class RequirementUpdate(BaseModel):
    """DTO para atualização de requisito."""

    title: Optional[str] = Field(None, min_length=5, max_length=200)
    description: Optional[str] = Field(None, min_length=20)
    priority: Optional[RequirementPriority] = None
    status: Optional[RequirementStatus] = None
    rationale: Optional[str] = None
    tags: Optional[List[str]] = None
    acceptance_criteria_ids: Optional[List[str]] = None
    user_story_ids: Optional[List[str]] = None


class RequirementList(BaseModel):
    """Lista de requisitos com metadados."""

    total: int
    items: List[Requirement]
    filters: Dict[str, Any] = Field(default_factory=dict)
