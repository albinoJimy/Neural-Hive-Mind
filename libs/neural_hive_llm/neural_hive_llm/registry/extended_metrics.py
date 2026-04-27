"""
Extended Model Quality Metrics.

Métricas adicionais de qualidade específicas por domínio.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Domain(str, Enum):
    """Domínios de especialização do modelo."""

    CODING = "coding"
    ANALYSIS = "analysis"
    MATH = "math"
    REASONING = "reasoning"
    CHAT = "chat"
    WRITING = "writing"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"


class ModelQualityScores(BaseModel):
    """Scores de qualidade específicos por domínio."""

    coding_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em geração de código"
    )
    analysis_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em análise"
    )
    math_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em matemática"
    )
    reasoning_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em raciocínio"
    )
    chat_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em chat/conversação"
    )
    writing_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em escrita"
    )
    translation_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em tradução"
    )
    summarization_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Score em sumarização"
    )

    @property
    def average_score(self) -> float:
        """Calcula score médio."""
        scores = [
            s
            for s in [
                self.coding_score,
                self.analysis_score,
                self.math_score,
                self.reasoning_score,
                self.chat_score,
                self.writing_score,
                self.translation_score,
                self.summarization_score,
            ]
            if s is not None
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def get_score_for_domain(self, domain: Domain | str) -> float | None:
        """Retorna score para um domínio específico.

        Aceita tanto Domain (Enum) quanto string (para compatibilidade com use_enum_values).
        """
        # Normaliza para string se for Enum
        domain_value = domain.value if isinstance(domain, Domain) else domain

        score_map = {
            Domain.CODING.value: self.coding_score,
            Domain.ANALYSIS.value: self.analysis_score,
            Domain.MATH.value: self.math_score,
            Domain.REASONING.value: self.reasoning_score,
            Domain.CHAT.value: self.chat_score,
            Domain.WRITING.value: self.writing_score,
            Domain.TRANSLATION.value: self.translation_score,
            Domain.SUMMARIZATION.value: self.summarization_score,
        }
        return score_map.get(domain_value)


class ReliabilityMetrics(BaseModel):
    """Métricas de confiabilidade do modelo/provider."""

    success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    uptime_percentage: float = Field(default=99.9, ge=0.0, le=100.0)
    avg_rate_limit_wait_ms: float = Field(default=0.0, ge=0.0)
    quota_available: bool = Field(default=True)
    geographic_regions: list[str] = Field(default_factory=list)
    last_health_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_distribution: dict[str, float] = Field(
        default_factory=dict,
        description="Distribuição de erros por tipo (timeout, rate_limit, etc)",
    )


class ComplianceInfo(BaseModel):
    """Informações de compliance do modelo/provider."""

    data_residency: str | None = Field(
        default=None, description="Região onde os dados são processados"
    )
    compliance_standards: list[str] = Field(
        default_factory=list,
        description="Standards de compliance (GDPR, HIPAA, SOC2, etc)",
    )
    data_retention_days: int | None = Field(default=None, description="Dias de retenção de logs")
    enterprise_tier: bool = Field(default=False)
    security_certifications: list[str] = Field(
        default_factory=list,
        description="Certificações de segurança",
    )
    encryption_at_rest: bool = Field(default=True)
    encryption_in_transit: bool = Field(default=True)


class UserFeedbackMetrics(BaseModel):
    """Métricas de feedback do utilizador."""

    avg_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    total_feedback_count: int = Field(default=0, ge=0)
    helpful_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    task_completion_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    user_satisfaction_score: float = Field(default=0.0, ge=0.0, le=1.0)
    last_feedback_update: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DynamicFactors(BaseModel):
    """Factores dinâmicos que variam com o tempo."""

    current_load_percentage: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Carga atual do provider"
    )
    time_based_performance_multiplier: float = Field(
        default=1.0, ge=0.0, description="Multiplicador baseado em hora/dia"
    )
    seasonal_performance_factor: float = Field(default=1.0, ge=0.0, description="Factor sazonal")
    feature_flags: dict[str, bool] = Field(
        default_factory=dict, description="Features experimentais disponíveis"
    )
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtendedModelMetadata(BaseModel):
    """Metadados extendidos do modelo com critérios adicionais."""

    model_id: str
    quality_scores: ModelQualityScores
    reliability: ReliabilityMetrics
    compliance: ComplianceInfo
    user_feedback: UserFeedbackMetrics | None = None
    dynamic_factors: DynamicFactors | None = None

    @property
    def composite_quality_score(self) -> float:
        """Calcula score de qualidade composto."""
        base_quality = self.quality_scores.average_score
        reliability_boost = self.reliability.success_rate * 0.2
        feedback_boost = (
            self.user_feedback.user_satisfaction_score * 0.3 if self.user_feedback else 0.0
        )
        return min(base_quality + reliability_boost + feedback_boost, 1.0)

    @property
    def operational_health_score(self) -> float:
        """Calcula score de saúde operacional."""
        uptime_score = self.reliability.uptime_percentage / 100.0
        load_score = (
            1.0 - (self.dynamic_factors.current_load_percentage / 100.0)
            if self.dynamic_factors
            else 1.0
        )
        success_score = self.reliability.success_rate

        return (uptime_score * 0.4) + (load_score * 0.3) + (success_score * 0.3)
