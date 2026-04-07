"""
Data models for Evolution Hooks.

Este módulo define os modelos Pydantic usados pelo sistema de meta-learning
do Evolution Specialist, incluindo fingerprints de planos, registros de
padrões, avaliações e feedback.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum


class TaskCountRange(str, Enum):
    """Range para contagem de tarefas."""

    SMALL = "small"  # < 5 tasks
    MEDIUM = "medium"  # 5-20 tasks
    LARGE = "large"  # > 20 tasks


class DurationRange(str, Enum):
    """Range para duração estimada."""

    SHORT = "short"  # < 1s
    MEDIUM = "medium"  # 1s - 10s
    LONG = "long"  # > 10s


class Fingerprint(BaseModel):
    """
    Fingerprint de um CognitivePlan para matching.

    O fingerprint é uma assinatura compacta que captura as características
    principais de um plano cognitivo, permitindo buscar planos similares
    no histórico de avaliações.
    """

    domain: str = Field(..., description="Domínio do plano")
    priority: str = Field(..., description="Prioridade: low, normal, high")
    task_count_range: TaskCountRange = Field(..., description="Range de contagem de tarefas")
    task_types: List[str] = Field(default_factory=list, description="Tipos únicos de tarefas")
    avg_dependency_count: float = Field(ge=0, description="Média de dependências")
    has_conditional_deps: bool = Field(default=False, description="Tem dependências condicionais?")
    estimated_duration_range: DurationRange = Field(default=DurationRange.MEDIUM)
    complexity_signature: str = Field(..., description="Hash para matching rápido")

    model_config = ConfigDict(use_enum_values=True)


# Pesos defaults - alinhados com EvolutionSpecialist._evaluate_plan_internal()
# services/specialist-evolution/src/specialist.py linhas 132-138
DEFAULT_WEIGHTS = {
    "maintainability": 0.25,
    "scalability": 0.25,
    "extensibility": 0.20,
    "modularity": 0.15,
    "tech_debt_prevention": 0.15,
}


class EvolutionEvaluation(BaseModel):
    """
    Avaliação do Evolution Specialist.

    Representa o resultado de uma avaliação de plano, incluindo scores,
    recomendação e os pesos que foram utilizados.
    """

    confidence_score: float = Field(ge=0, le=1, description="Score de confiança (0-1)")
    risk_score: float = Field(ge=0, le=1, description="Score de risco (0-1)")
    recommendation: str = Field(
        ..., description="Recomendação: approve, reject, review_required, conditional"
    )
    weights_used: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_WEIGHTS.copy(),
        description="Pesos utilizados nesta avaliação",
    )
    reasoning_factors: List[Dict[str, Any]] = Field(
        default_factory=list, description="Fatores de raciocínio detalhados"
    )

    @field_validator("recommendation")
    @classmethod
    def validate_recommendation(cls, v: str) -> str:
        """Valida que recomendação é um valor válido."""
        valid_recommendations = ["approve", "reject", "review_required", "conditional"]
        if v not in valid_recommendations:
            raise ValueError(
                f"recommendation deve ser um de {valid_recommendations}, recebido: {v}"
            )
        return v


class PatternMetrics(BaseModel):
    """
    Métricas de um padrão de avaliação.

    Acompanha quantas vezes um padrão foi usado como similar e sua
    taxa de sucesso ao longo do tempo.
    """

    times_matched: int = Field(default=0, ge=0, description="Vezes usado como similar")
    success_rate: float = Field(default=0.5, ge=0, le=1, description="Taxa de sucesso")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Última atualização"
    )


class FeedbackOutcome(str, Enum):
    """Outcome do feedback."""

    APPROVE = "approve"
    REJECT = "reject"


class FeedbackSource(str, Enum):
    """Source do feedback."""

    HUMAN = "human"
    AUTOMATED = "automated"
    SYSTEM = "system"


class FeedbackData(BaseModel):
    """
    Dados de feedback recebido.

    Representa o feedback final após aprovação/rejeição, permitindo
    que o sistema aprenda com o resultado.
    """

    outcome: FeedbackOutcome = Field(..., description="Resultado final")
    source: FeedbackSource = Field(..., description="Origem do feedback")
    reasoning: Optional[str] = Field(None, description="Justificativa do feedback")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp do feedback"
    )
    corrected_weights: Optional[Dict[str, float]] = Field(
        None, description="Pesos corrigidos após feedback (se aplicável)"
    )


class PatternRecord(BaseModel):
    """
    Registro completo no pattern registry.

    Um registro completo que inclui fingerprint, avaliação original,
    feedback recebido e métricas de aprendizado.
    """

    id: Optional[str] = Field(None, alias="_id", description="ID do documento MongoDB")
    plan_id: str = Field(..., description="ID do plano cognitivo")
    fingerprint: Fingerprint = Field(..., description="Fingerprint do plano")
    evaluation: EvolutionEvaluation = Field(..., description="Avaliação original")
    feedback: Optional[FeedbackData] = Field(None, description="Feedback recebido")
    metrics: PatternMetrics = Field(
        default_factory=PatternMetrics, description="Métricas de aprendizado"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp de criação"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da última atualização",
    )

    model_config = ConfigDict(populate_by_name=True)


class FeedbackMessage(BaseModel):
    """
    Mensagem Kafka de feedback.

    Schema da mensagem publicada no tópico Kafka evolution.feedback.topic
    pelo Approval Service após decisão final.
    """

    plan_id: str = Field(..., description="ID do plano avaliado")
    fingerprint: Fingerprint = Field(..., description="Fingerprint do plano")
    evaluation: EvolutionEvaluation = Field(..., description="Avaliação original")
    feedback: FeedbackData = Field(..., description="Feedback final")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "plan-uuid-123",
                "fingerprint": {
                    "domain": "technical",
                    "priority": "high",
                    "task_count_range": "medium",
                    "task_types": ["BUILD", "TEST", "DEPLOY"],
                    "avg_dependency_count": 1.5,
                    "has_conditional_deps": True,
                    "complexity_signature": "T-M-B-T-D-H",
                },
                "evaluation": {
                    "confidence_score": 0.75,
                    "risk_score": 0.25,
                    "recommendation": "approve",
                    "weights_used": DEFAULT_WEIGHTS,
                    "reasoning_factors": [],
                },
                "feedback": {
                    "outcome": "approve",
                    "source": "human",
                    "reasoning": "Approved after review",
                    "timestamp": "2026-03-24T10:00:00Z",
                },
            }
        }
    )
