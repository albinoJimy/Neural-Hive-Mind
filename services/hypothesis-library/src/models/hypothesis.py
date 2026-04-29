"""Hypothesis models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

UTC = timezone.utc


def utcnow() -> datetime:
    """Retorna datetime UTC atual."""
    return datetime.now(timezone.utc)


class HypothesisStatus(str, Enum):
    """Estados do ciclo de vida de uma hipótese."""

    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    IN_TESTING = "IN_TESTING"
    COMPLETED = "COMPLETED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"

    @classmethod
    def active_states(cls) -> set[HypothesisStatus]:
        """Estados ativos (não terminais)."""
        return {
            cls.DRAFT,
            cls.PROPOSED,
            cls.APPROVED,
            cls.IN_TESTING,
            cls.COMPLETED,
        }

    @classmethod
    def terminal_states(cls) -> set[HypothesisStatus]:
        """Estados terminais (finais)."""
        return {cls.ACCEPTED, cls.REJECTED, cls.ARCHIVED}


class HypothesisPriority(str, Enum):
    """Níveis de prioridade."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class HypothesisResults(BaseModel):
    """Resultados de experimento de hipótese."""

    experiment_id: str | None = Field(None, description="ID do experimento")
    status: str = Field(default="completed", description="Status do experimento")
    outcome: str = Field(
        default="inconclusive", description="Outcome: validated, refuted, inconclusive"
    )
    confidence_level: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Nível de confiança estatística"
    )
    improvement_percentage: float | None = Field(None, description="Melhoria observada")
    statistical_significance: bool = Field(default=False, description="Significância estatística")
    actual_baseline_metrics: dict[str, float] = Field(
        default_factory=dict, description="Métricas baseline observadas"
    )
    actual_target_metrics: dict[str, float] = Field(
        default_factory=dict, description="Métricas target observadas"
    )
    lessons_learned: list[str] = Field(
        default_factory=list, description="Aprendizados do experimento"
    )
    completed_at: datetime | None = Field(None, description="Data de conclusão")

    @field_validator("confidence_level")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class PyObjectId(ObjectId):
    """Wrapper para ObjectId do MongoDB compatível com Pydantic."""

    @classmethod
    def __get_validators__(cls):
        """Obter validadores para Pydantic V1."""
        yield cls.validate

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """Obter schema core para Pydantic V2."""
        from pydantic_core import core_schema

        return core_schema.no_info_before_validator_function(
            cls.validate,
            core_schema.str_schema(),
        )

    @classmethod
    def validate(cls, v: Any) -> ObjectId:
        """Valida e converte para ObjectId."""
        if not isinstance(v, (str, bytes, ObjectId)):
            raise TypeError("ObjectId required")
        if isinstance(v, str):
            return ObjectId(v)
        return v


class Hypothesis(BaseModel):
    """Modelo principal de Hipótese."""

    id: PyObjectId | None = Field(None, alias="_id", description="MongoDB ObjectId")
    hypothesis_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique identifier (UUID)"
    )
    title: str = Field(..., min_length=1, max_length=200, description="Título da hipótese")
    description: str = Field(..., min_length=1, description="Descrição detalhada")
    background: str = Field(default="", description="Contexto e razão para esta hipótese")
    expected_outcome: str = Field(..., min_length=1, description="Resultado esperado")
    metrics: list[str] = Field(default_factory=list, description="Métricas que serão afetadas")
    baseline_metrics: dict[str, float] = Field(
        default_factory=dict, description="Métricas baseline atuais"
    )
    target_metrics: dict[str, float] = Field(
        default_factory=dict, description="Métricas target desejadas"
    )

    status: HypothesisStatus = Field(default=HypothesisStatus.DRAFT, description="Status atual")
    priority: HypothesisPriority = Field(
        default=HypothesisPriority.MEDIUM, description="Prioridade"
    )

    author: str = Field(..., min_length=1, description="Autor da hipótese")
    reviewers: list[str] = Field(default_factory=list, description="Revisores atribuídos")
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")

    created_at: datetime = Field(default_factory=utcnow, description="Data de criação")
    updated_at: datetime = Field(default_factory=utcnow, description="Última atualização")
    proposed_at: datetime | None = Field(None, description="Data de proposta")
    approved_at: datetime | None = Field(None, description="Data de aprovação")
    approved_by: str | None = Field(None, description="Aprovador")
    testing_started_at: datetime | None = Field(None, description="Início do teste")
    completed_at: datetime | None = Field(None, description="Data de conclusão")

    current_version: int = Field(default=1, description="Versão atual")
    versions: list[int] = Field(default_factory=lambda: [1], description="Histórico de versões")

    experiment_id: str | None = Field(None, description="ID do experimento associado")
    results: HypothesisResults | None = Field(None, description="Resultados do experimento")

    requires_experiment: bool = Field(
        default=True, description="Se requer validação via experimento"
    )
    auto_approve: bool = Field(default=False, description="Aprovação automática (bypass revisão)")

    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    model_config = ConfigDict(
        populate_by_name=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário, serializando ObjectId."""
        data = self.model_dump(exclude={"id"})
        if self.id:
            data["_id"] = str(self.id)
        return data

    @field_validator("title", "description", "expected_outcome", "author")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Valida que strings importantes não estão vazias após strip."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class HypothesisCreate(BaseModel):
    """Schema para criação de hipótese."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    background: str = Field(default="")
    expected_outcome: str = Field(..., min_length=1)
    metrics: list[str] = Field(default_factory=list)
    baseline_metrics: dict[str, float] = Field(default_factory=dict)
    target_metrics: dict[str, float] = Field(default_factory=dict)
    priority: HypothesisPriority = Field(default=HypothesisPriority.MEDIUM)
    author: str = Field(..., min_length=1)
    reviewers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    requires_experiment: bool = Field(default=True)
    auto_approve: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description", "expected_outcome", "author")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Valida que strings importantes não estão vazias após strip."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class HypothesisUpdate(BaseModel):
    """Schema para atualização de hipótese."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1)
    background: str | None = None
    expected_outcome: str | None = Field(None, min_length=1)
    metrics: list[str] | None = None
    baseline_metrics: dict[str, float] | None = None
    target_metrics: dict[str, float] | None = None
    priority: HypothesisPriority | None = None
    reviewers: list[str] | None = None
    tags: list[str] | None = None
    requires_experiment: bool | None = None
    metadata: dict[str, Any] | None = None


class HypothesisFilter(BaseModel):
    """Filtros para busca de hipóteses."""

    status: HypothesisStatus | None = None
    priority: HypothesisPriority | None = None
    author: str | None = None
    reviewer: str | None = None
    tags: list[str] | None = None
    search_text: str | None = Field(None, description="Busca em title/description")
    requires_experiment: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    has_experiment: bool | None = Field(None, description="Tem experimento associado")
    outcome: str | None = Field(None, description="Filtrar por outcome dos resultados")

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="created_at", description="Campo para ordenação")
    sort_order: int = Field(default=-1, description="1=asc, -1=desc")

    @field_validator("sort_by")
    @classmethod
    def validate_sort_field(cls, v: str) -> str:
        allowed = {
            "created_at",
            "updated_at",
            "title",
            "priority",
            "status",
            "proposed_at",
            "approved_at",
        }
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v
