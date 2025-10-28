"""
Risk Scoring Models

Modelos Pydantic para representação de avaliações de risco.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime
from .config import RiskDomain, RiskBand


class RiskFactor(BaseModel):
    """Fator individual de risco."""
    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    description: str
    contribution: str  # 'positive', 'negative', 'neutral'


class RiskAssessment(BaseModel):
    """Avaliação de risco completa."""
    score: float = Field(ge=0.0, le=1.0, description='Score de risco agregado')
    band: RiskBand = Field(description='Classificação de risco')
    domain: RiskDomain = Field(description='Domínio de avaliação')
    factors: Dict[str, float] = Field(description='Fatores individuais')
    reasoning: str = Field(description='Justificativa da avaliação')
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class RiskMatrix(BaseModel):
    """Matriz de risco multi-domínio."""
    entity_id: str
    entity_type: str  # 'plan', 'decision', 'execution'
    assessments: Dict[str, RiskAssessment]  # Por domínio
    overall_score: float = Field(ge=0.0, le=1.0)
    overall_band: RiskBand
    highest_risk_domain: RiskDomain
    created_at: datetime = Field(default_factory=datetime.utcnow)
