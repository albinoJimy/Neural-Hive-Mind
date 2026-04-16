"""Modelos de dados para requisitos funcionais."""

from datetime import datetime
from enum import Enum
from typing import Any

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
        default=RequirementType.FUNCTIONAL, description="Tipo do requisito"
    )
    priority: RequirementPriority = Field(
        default=RequirementPriority.MEDIUM, description="Prioridade do requisito"
    )
    status: RequirementStatus = Field(
        default=RequirementStatus.DRAFT, description="Status do requisito"
    )
    title: str = Field(..., min_length=5, max_length=200, description="Título do requisito")
    description: str = Field(..., min_length=20, description="Descrição detalhada do requisito")
    rationale: str = Field(
        default="", description="Justificativa do requisito (por que é necessário)"
    )
    acceptance_criteria_ids: list[str] = Field(
        default_factory=list, description="IDs dos critérios de aceitação"
    )
    user_story_ids: list[str] = Field(
        default_factory=list, description="IDs das user stories relacionadas"
    )
    dependencies: list[str] = Field(
        default_factory=list, description="IDs dos requisitos dos quais depende"
    )
    conflicts: list[str] = Field(
        default_factory=list, description="IDs dos requisitos com os quais conflita"
    )
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")
    cognitive_plan_id: str | None = Field(None, description="ID do CognitivePlan de origem")
    architecture_plan_id: str | None = Field(None, description="ID do ArchitecturePlan relacionado")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de criação")
    updated_at: datetime | None = Field(None, description="Data da última atualização")
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
    tags: list[str] = Field(default_factory=list)
    cognitive_plan_id: str | None = None
    architecture_plan_id: str | None = None


class RequirementUpdate(BaseModel):
    """DTO para atualização de requisito."""

    title: str | None = Field(None, min_length=5, max_length=200)
    description: str | None = Field(None, min_length=20)
    priority: RequirementPriority | None = None
    status: RequirementStatus | None = None
    rationale: str | None = None
    tags: list[str] | None = None
    acceptance_criteria_ids: list[str] | None = None
    user_story_ids: list[str] | None = None


class RequirementList(BaseModel):
    """Lista de requisitos com metadados."""

    total: int
    items: list[Requirement]
    filters: dict[str, Any] = Field(default_factory=dict)


class RequirementsSet(BaseModel):
    """Conjunto de requisitos gerados a partir de um plano."""

    id: str = Field(..., description="ID único do conjunto")
    cognitive_plan_id: str = Field(..., description="ID do CognitivePlan de origem")
    requirements: list[Requirement] = Field(default_factory=list)
    functional_count: int = Field(default=0, description="Contagem de requisitos funcionais")
    non_functional_count: int = Field(
        default=0, description="Contagem de requisitos não-funcionais"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def add_requirement(self, requirement: Requirement) -> None:
        """Adiciona um requisito ao conjunto."""
        self.requirements.append(requirement)
        if requirement.requirement_type == RequirementType.FUNCTIONAL:
            self.functional_count += 1
        else:
            self.non_functional_count += 1
