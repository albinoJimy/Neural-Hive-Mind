"""Tech Stack recommendation models."""

from pydantic import BaseModel, Field
from typing import List, Optional


class TechChoice(BaseModel):
    """Escolha tecnológica."""

    category: str = Field(..., description="ex: backend, database, frontend")
    name: str = Field(..., description="ex: FastAPI, PostgreSQL, React")
    version: Optional[str] = Field(None, description="Versão recomendada")
    rationale: str = Field(..., description="Por que esta tecnologia")
    alternatives: List[str] = Field(default_factory=list)


class Constraint(BaseModel):
    """Restrição técnica."""

    type: str = Field(..., description="ex: language, framework, hosting")
    value: str = Field(..., description="Valor da restrição")
    reason: Optional[str] = Field(None, description="Razão da restrição")


class TechStackRecommendation(BaseModel):
    """Recomendação completa de stack tecnológico."""

    choices: List[TechChoice]
    constraints_satisfied: List[str]
    constraints_violated: List[str] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    estimated_cost: Optional[str] = Field(None, description="Estimativa de custo mensal")
    estimated_complexity: Optional[str] = Field(None, description="baixa, media, alta")
