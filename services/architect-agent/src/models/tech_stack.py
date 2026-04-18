"""Tech Stack recommendation models."""

from pydantic import BaseModel, Field


class TechChoice(BaseModel):
    """Escolha tecnológica."""

    category: str = Field(..., description="ex: backend, database, frontend")
    name: str = Field(..., description="ex: FastAPI, PostgreSQL, React")
    version: str | None = Field(None, description="Versão recomendada")
    rationale: str = Field(..., description="Por que esta tecnologia")
    alternatives: list[str] = Field(default_factory=list)


class Constraint(BaseModel):
    """Restrição técnica."""

    type: str = Field(..., description="ex: language, framework, hosting")
    value: str = Field(..., description="Valor da restrição")
    reason: str | None = Field(None, description="Razão da restrição")


class TechStackRecommendation(BaseModel):
    """Recomendação completa de stack tecnológico."""

    choices: list[TechChoice]
    constraints_satisfied: list[str]
    constraints_violated: list[str] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    estimated_cost: str | None = Field(None, description="Estimativa de custo mensal")
    estimated_complexity: str | None = Field(None, description="baixa, media, alta")
