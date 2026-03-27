"""Schemas Pydantic para API REST."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from src.models.architecture import ArchitectureType, Pattern
from src.models.validation import Severity


# Request Schemas
class ArchitectureRequest(BaseModel):
    """Schema para requisição de criação de arquitetura."""

    intent: str = Field(..., description="Intent do usuário", min_length=1)
    context: dict = Field(default_factory=dict, description="Contexto adicional")
    cognitive_plan_id: Optional[str] = Field(None, description="ID do plano cognitivo")


class ValidationRequest(BaseModel):
    """Schema para requisição de validação."""

    repo_url: str = Field(..., description="URL do repositório")
    branch: str = Field(default="main", description="Branch para analisar")


class RefineRequest(BaseModel):
    """Schema para refinamento de plano."""

    plan_id: str = Field(..., description="ID do plano a refinar")
    feedback: str = Field(..., description="Feedback do usuário")
    new_intent: str = Field(..., description="Novo intent")


# Response Schemas
class ComponentResponse(BaseModel):
    """Schema de resposta para componente."""

    name: str
    stack: str
    replicas: Optional[int] = None
    ha: Optional[bool] = None


class ArchitectureResponse(BaseModel):
    """Schema de resposta para plano de arquitetura."""

    plan_id: str
    cognitive_plan_id: Optional[str]
    architecture_type: str
    components: list[ComponentResponse]
    patterns: list[str]
    rationale: str
    created_at: datetime


class ViolationResponse(BaseModel):
    """Schema de resposta para violação."""

    type: str
    severity: str
    location: str
    description: str
    suggestion: Optional[str] = None


class SuggestionResponse(BaseModel):
    """Schema de resposta para sugestão."""

    priority: int
    description: str
    effort: str
    affected_files: list[str]


class ValidationResponse(BaseModel):
    """Schema de resposta para validação."""

    report_id: str
    repo_url: str
    branch: str
    health_score: int
    trend: str
    violations: list[ViolationResponse]
    suggestions: list[SuggestionResponse]
    created_at: datetime


class DriftDetectionResponse(BaseModel):
    """Schema de resposta para detecção de drift."""

    drift_type: str
    severity: str
    description: str
    expected: str
    actual: str


class EvolutionResponse(BaseModel):
    """Schema de resposta para histórico de evolução."""

    history_id: str
    plan_id: str
    version: int
    changes: list[str]
    drifts: list[DriftDetectionResponse]
    created_at: datetime
