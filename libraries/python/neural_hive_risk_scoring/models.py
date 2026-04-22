"""
Risk Scoring Models

Modelos Pydantic para representação de avaliações de risco.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from neural_hive_domain import UnifiedDomain

from .config import RiskBand


class RiskFactor(BaseModel):
    """Fator individual de risco."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    description: str
    contribution: str  # 'positive', 'negative', 'neutral'


class RiskAssessment(BaseModel):
    """Avaliação de risco completa."""

    model_config = ConfigDict(use_enum_values=False)

    score: float = Field(ge=0.0, le=1.0, description="Score de risco agregado")
    band: RiskBand = Field(description="Classificação de risco")
    domain: UnifiedDomain = Field(description="Domínio de avaliação")
    factors: dict[str, float] = Field(description="Fatores individuais")
    reasoning: str = Field(description="Justificativa da avaliação")
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskMatrix(BaseModel):
    """Matriz de risco multi-domínio."""

    model_config = ConfigDict(use_enum_values=False)

    entity_id: str
    entity_type: str  # 'plan', 'decision', 'execution'
    assessments: dict[str, RiskAssessment]  # Por domínio
    overall_score: float = Field(ge=0.0, le=1.0)
    overall_band: RiskBand
    highest_risk_domain: UnifiedDomain
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
