"""Modelos de dados para User Stories."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

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
    acceptance_criteria_ids: list[str] = Field(
        default_factory=list, description="IDs dos critérios de aceitação"
    )
    tasks: list[str] = Field(
        default_factory=list, description="Lista de tarefas técnicas para implementação"
    )
    dependencies: list[str] = Field(
        default_factory=list, description="IDs das user stories das quais depende"
    )

    # Metadados
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")
    epic: str | None = Field(None, description="Epic relacionado (se aplicável)")
    sprint: str | None = Field(None, description="Sprint planejado")
    assignee: str | None = Field(None, description="Responsável pela implementação")
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    cognitive_plan_id: str | None = Field(None, description="ID do CognitivePlan de origem")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(None)
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

    def get_user_story_format(self) -> str:
        """Retorna a user story no formato padrão."""
        return f"Como {self.role}, eu quero {self.action}, para que {self.benefit}."


class UserStorySet(BaseModel):
    """Conjunto de user stories para um RequirementsSet."""

    id: str = Field(..., description="ID único do conjunto")
    requirements_set_id: str = Field(..., description="ID do RequirementsSet")
    stories: list[UserStory] = Field(default_factory=list)
    total_story_points: int = Field(default=0, description="Total de story points")
    breakdown: dict[StorySize, int] = Field(
        default_factory=dict, description="Distribuição por tamanho"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(None)

    def add_story(self, story: UserStory) -> None:
        """Adiciona uma user story ao conjunto."""
        self.stories.append(story)
        self.total_story_points += self._size_to_points(story.size)
        self.breakdown[story.size] = self.breakdown.get(story.size, 0) + 1
        self.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _size_to_points(size: StorySize) -> int:
        """Converte tamanho para pontos."""
        mapping = {
            StorySize.EXTRA_SMALL: 1,
            StorySize.SMALL: 2,
            StorySize.MEDIUM: 3,
            StorySize.LARGE: 5,
            StorySize.EXTRA_LARGE: 8,
        }
        return mapping.get(size, 3)


class UserStoryCreate(BaseModel):
    """DTO para criação de user story."""

    requirement_id: str = Field(..., description="ID do requisito relacionado")
    role: str = Field(..., min_length=2)
    action: str = Field(..., min_length=5)
    benefit: str = Field(..., min_length=10)
    size: StorySize = StorySize.MEDIUM
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    epic: str | None = None


class UserStoryUpdate(BaseModel):
    """DTO para atualização de user story."""

    status: StoryStatus | None = None
    size: StorySize | None = None
    description: str | None = None
    acceptance_criteria_ids: list[str] | None = None
    tasks: list[str] | None = None
    assignee: str | None = None
    sprint: str | None = None


class UserStoryList(BaseModel):
    """Lista de user stories com metadados."""

    total: int
    items: list[UserStory]
    requirement_id: str | None = None
