"""Modelos de dados para User Stories."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class StorySize(str, Enum):
    """Tamanho estimado da user story (story points)."""

    EXTRA_SMALL = "xs"  # 1 ponto
    SMALL = "s"  # 2 pontos
    MEDIUM = "m"  # 3 pontos
    LARGE = "l"  # 5 pontos
    EXTRA_LARGE = "xl"  # 8+ pontos


class StoryStatus(str, Enum):
    """Status da user story."""

    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class UserStory(BaseModel):
    """User Story representando uma funcionalidade do ponto de vista do utilizador."""

    id: str = Field(..., description="ID único da user story")
    requirement_id: str = Field(..., description="ID do requisito relacionado")
    status: StoryStatus = Field(default=StoryStatus.DRAFT, description="Status da story")
    size: StorySize = Field(default=StorySize.MEDIUM, description="Tamanho estimado")

    # Formato padrão: Como [role], eu quero [feature], para que [benefit]
    role: str = Field(..., description="Papel do utilizador (ex: 'admin', 'utilizador final')")
    action: str = Field(..., description="Acção que o utilizador quer realizar (feature desejada)")
    benefit: str = Field(..., description="Benefício ou valor que o utilizador obtém")

    # Detalhes adicionais
    description: str = Field(default="", description="Descrição detalhada da história")
    acceptance_criteria_ids: List[str] = Field(
        default_factory=list, description="IDs dos critérios de aceitação"
    )
    tasks: List[str] = Field(
        default_factory=list, description="Lista de tarefas técnicas para implementação"
    )
    dependencies: List[str] = Field(
        default_factory=list, description="IDs das user stories das quais depende"
    )

    # Metadados
    tags: List[str] = Field(default_factory=list, description="Tags para categorização")
    epic: Optional[str] = Field(None, description="Epic relacionado (se aplicável)")
    sprint: Optional[str] = Field(None, description="Sprint planejado")
    assignee: Optional[str] = Field(None, description="Responsável pela implementação")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    cognitive_plan_id: Optional[str] = Field(None, description="ID do CognitivePlan de origem")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)
    version: int = Field(default=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Valida formato do ID."""
        if not v.startswith("US-"):
            raise ValueError("ID must start with 'US-'")
        return v

    @property
    def story_statement(self) -> str:
        """Retorna a user story no formato padrão."""
        return f"Como {self.role}, eu quero {self.action}, para que {self.benefit}"


class UserStoryCreate(BaseModel):
    """DTO para criação de user story."""

    requirement_id: str = Field(..., description="ID do requisito relacionado")
    role: str = Field(..., min_length=2)
    action: str = Field(..., min_length=5)
    benefit: str = Field(..., min_length=10)
    size: StorySize = StorySize.MEDIUM
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    epic: Optional[str] = None


class UserStoryUpdate(BaseModel):
    """DTO para atualização de user story."""

    status: Optional[StoryStatus] = None
    size: Optional[StorySize] = None
    description: Optional[str] = None
    acceptance_criteria_ids: Optional[List[str]] = None
    tasks: Optional[List[str]] = None
    assignee: Optional[str] = None
    sprint: Optional[str] = None


class UserStoryList(BaseModel):
    """Lista de user stories com metadados."""

    total: int
    items: List[UserStory]
    requirement_id: Optional[str] = None
