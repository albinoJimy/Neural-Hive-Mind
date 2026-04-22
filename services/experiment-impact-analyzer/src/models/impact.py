"""Models for experiment impact analysis."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

UTC = UTC


def utcnow() -> datetime:
    """Retorna datetime UTC atual."""
    return datetime.now(UTC)


class ImpactTimeframe(str, Enum):
    """Timeframe for impact analysis."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    BOTH = "both"


class ImpactDirection(str, Enum):
    """Direction of impact."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class ImpactMagnitude(str, Enum):
    """Magnitude of impact."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class ImpactCategory(str, Enum):
    """Categories of impact."""

    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    COST = "cost"
    USER_EXPERIENCE = "user_experience"
    SECURITY = "security"
    MAINTAINABILITY = "maintainability"
    SCALABILITY = "scalability"
    BUSINESS = "business"


class MetricImpact(BaseModel):
    """Impact on a specific metric."""

    metric_name: str = Field(..., description="Nome da métrica")
    baseline_value: float = Field(..., description="Valor baseline")
    post_experiment_value: float = Field(..., description="Valor após experimento")
    absolute_change: float = Field(..., description="Mudança absoluta")
    relative_change_percent: float = Field(..., description="Mudança relativa em %")
    statistical_significance: bool = Field(default=False, description="Significância estatística")
    confidence_interval: tuple[float, float] | None = Field(
        default=None, description="Intervalo de confiança (lower, upper)"
    )
    p_value: float | None = Field(default=None, description="Valor p (se disponível)")


class ShortTermImpact(BaseModel):
    """Short-term impact analysis (days to weeks)."""

    timeframe_days: int = Field(..., description="Período analisado em dias")
    immediate_effects: list[str] = Field(
        default_factory=list, description="Efeitos imediatos observados"
    )
    metric_impacts: dict[str, MetricImpact] = Field(
        default_factory=dict, description="Impactos por métrica"
    )
    system_stability: str = Field(
        default="unknown", description="Estabilidade do sistema (stable/degraded/improved)"
    )
    error_rate_change: float | None = Field(default=None, description="Mudança na taxa de erro")
    latency_change: float | None = Field(default=None, description="Mudança na latência")
    throughput_change: float | None = Field(default=None, description="Mudança no throughput")
    detected_at: datetime = Field(default_factory=utcnow, description="Data de detecção")


class LongTermImpact(BaseModel):
    """Long-term impact analysis (weeks to months)."""

    timeframe_days: int = Field(..., description="Período analisado em dias")
    sustained_effects: list[str] = Field(
        default_factory=list, description="Efeitos sustentados observados"
    )
    cumulative_benefit: float | None = Field(
        default=None, description="Benefício cumulativo (quando aplicável)"
    )
    degradation_detected: bool = Field(
        default=False, description="Degradação detectada ao longo do tempo"
    )
    adaptation_observed: bool = Field(default=False, description="Adaptação do sistema observada")
    trend_analysis: dict[str, str] = Field(
        default_factory=dict, description="Análise de tendências por métrica"
    )
    seasonal_effects: list[str] = Field(
        default_factory=list, description="Efeitos sazonais detectados"
    )
    learning_curve_observed: bool = Field(
        default=False, description="Curva de aprendizado observada"
    )
    last_analyzed_at: datetime = Field(default_factory=utcnow, description="Última análise")


class ExperimentCorrelation(BaseModel):
    """Correlation between experiments."""

    experiment_id: str = Field(..., description="ID do experimento correlacionado")
    correlation_coefficient: float = Field(..., ge=-1.0, le=1.0)
    correlation_type: str = Field(..., description="Tipo de correlação (positive, negative, none)")
    shared_metrics: list[str] = Field(
        default_factory=list, description="Métricas afetadas por ambos"
    )
    interaction_effect: float | None = Field(
        default=None, description="Efeito de interação (se houver)"
    )
    description: str = Field(default="", description="Descrição da correlação")


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


class ExperimentImpact(BaseModel):
    """Main model for experiment impact analysis."""

    id: PyObjectId | None = Field(None, alias="_id", description="MongoDB ObjectId")
    impact_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique identifier (UUID)"
    )
    experiment_id: str = Field(..., description="ID do experimento analisado")
    hypothesis_id: str | None = Field(None, description="ID da hipótese relacionada")

    # Overall assessment
    overall_direction: ImpactDirection = Field(..., description="Direção geral do impacto")
    overall_magnitude: ImpactMagnitude = Field(..., description="Magnitude geral do impacto")
    categories: list[ImpactCategory] = Field(
        default_factory=list, description="Categorias de impacto"
    )

    # Time-based analysis
    short_term_impact: ShortTermImpact | None = Field(None, description="Análise de curto prazo")
    long_term_impact: LongTermImpact | None = Field(None, description="Análise de longo prazo")

    # Correlations
    correlated_experiments: list[ExperimentCorrelation] = Field(
        default_factory=list, description="Experimentos correlacionados"
    )

    # Recommendations
    recommendation: str = Field(..., description="Recomendação baseada na análise")
    confidence_level: float = Field(
        ..., ge=0.0, le=1.0, description="Nível de confiança na análise"
    )

    # Metadata
    created_at: datetime = Field(default_factory=utcnow, description="Data de criação")
    updated_at: datetime = Field(default_factory=utcnow, description="Última atualização")
    analysis_version: int = Field(default=1, description="Versão da análise")

    # Additional data
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")
    notes: list[str] = Field(default_factory=list, description="Notas adicionais")

    model_config = ConfigDict(populate_by_name=True)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário, serializando ObjectId."""
        data = self.model_dump(exclude={"id"})
        if self.id:
            data["_id"] = str(self.id)
        return data

    @field_validator("confidence_level")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class ImpactAnalysisRequest(BaseModel):
    """Request for impact analysis."""

    experiment_id: str = Field(..., description="ID do experimento")
    hypothesis_id: str | None = Field(None, description="ID da hipótese")
    timeframes: list[ImpactTimeframe] = Field(
        default_factory=lambda: [ImpactTimeframe.SHORT_TERM], description="Timeframes para analisar"
    )
    include_correlations: bool = Field(default=True, description="Incluir análise de correlações")
    force_refresh: bool = Field(default=False, description="Forçar nova análise (ignorar cache)")
    reference_baseline: dict[str, float] | None = Field(
        None, description="Baseline personalizado para comparação"
    )


class ImpactAnalysisResponse(BaseModel):
    """Response for impact analysis."""

    impact_id: str = Field(..., description="ID da análise")
    experiment_id: str = Field(..., description="ID do experimento")
    status: str = Field(..., description="Status da análise")
    overall_direction: ImpactDirection | None = Field(None)
    overall_magnitude: ImpactMagnitude | None = Field(None)
    recommendation: str | None = Field(None)
    confidence_level: float | None = Field(None)
    short_term_available: bool = Field(default=False)
    long_term_available: bool = Field(default=False)
    correlations_available: bool = Field(default=False)


class BatchImpactAnalysisRequest(BaseModel):
    """Request for batch impact analysis."""

    experiment_ids: list[str] = Field(
        ..., min_length=1, max_length=50, description="IDs dos experimentos para analisar"
    )
    timeframes: list[ImpactTimeframe] = Field(
        default_factory=lambda: [ImpactTimeframe.SHORT_TERM], description="Timeframes para analisar"
    )


class ImpactSummary(BaseModel):
    """Summary of impacts across experiments."""

    total_experiments: int = Field(..., description="Total de experimentos analisados")
    positive_impacts: int = Field(..., description="Experimentos com impacto positivo")
    negative_impacts: int = Field(..., description="Experimentos com impacto negativo")
    neutral_impacts: int = Field(..., description="Experimentos com impacto neutro")
    high_magnitude_count: int = Field(..., description="Impactos de alta magnitude")
    average_confidence: float = Field(..., description="Confiança média das análises")
    top_categories: list[tuple[ImpactCategory, int]] = Field(
        default_factory=list, description="Top categorias de impacto"
    )
