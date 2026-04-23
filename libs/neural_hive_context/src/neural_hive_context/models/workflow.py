"""
Workflow Models

Modelos relacionados à classificação e execução de workflows.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from enum import Enum


class WorkflowType(str, Enum):
    """Tipos de workflow disponíveis."""

    ORCHESTRATION = "orchestration"
    """Workflow de orquestração: aprovação, coordenação, múltiplos especialistas."""

    GENERATION = "generation"
    """Workflow de geração: criação de conteúdo, código, relatórios."""


class WorkflowSignal(BaseModel):
    """Sinal individual usado na classificação."""

    name: str = Field(..., description="Nome do sinal")
    value: float = Field(..., ge=0.0, le=1.0, description="Valor normalizado do sinal")
    weight: float = Field(
        ..., ge=0.0, le=1.0, description="Peso do sinal no cálculo final"
    )
    contribution: float = Field(
        ..., description="Contribuição ponderada (value * weight)"
    )
    description: Optional[str] = Field(None, description="Descrição do sinal")


class WorkflowClassification(BaseModel):
    """
    Resultado da classificação de workflow.

    Este modelo é retornado pelo WorkflowClassifier e contém
    a decisão tomada junto com a justificativa.
    """

    workflow_type: WorkflowType = Field(
        ..., description="Workflow classificado (ORCHESTRATION ou GENERATION)"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confiança da classificação (0.0 a 1.0)"
    )
    reasoning: str = Field(..., description="Explicação em linguagem natural da decisão")
    signals: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sinais extraídos e seus valores brutos"
    )
    raw_score: float = Field(
        ..., description="Score bruto calculado (antes da decisão binária)"
    )

    model_config = ConfigDict(use_enum_values=True)


class ClassificationDecision(str, Enum):
    """Decisão baseada na confiança."""

    AUTO_ORCHESTRATION = "auto_orchestration"
    """Confiança alta para ORCHESTRATION - executar automaticamente."""

    AUTO_GENERATION = "auto_generation"
    """Confiança alta para GENERATION - executar automaticamente."""

    REVIEW_NEEDED = "review_needed"
    """Confiança média - requer revisão humana ou heurística adicional."""
