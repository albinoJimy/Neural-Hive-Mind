"""
Enhanced Selection Context with Additional Criteria.

Contexto de seleção expandido com novos critérios.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# Import direto para evitar ciclo de importação
import neural_hive_llm.registry.extended_metrics as em

# Re-exportar Domain para uso externo
Domain = em.Domain

from neural_hive_llm.registry.model_registry import TaskType


class ComplianceRequirement(str, Enum):
    """Requisitos de compliance."""

    GDPR = "gdpr"
    HIPAA = "hipaa"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    NONE = "none"


class DataResidencyRequirement(str, Enum):
    """Requisitos de residência de dados."""

    EU = "eu"
    US = "us"
    GLOBAL = "global"
    NONE = "none"


class PriorityLevel(str, Enum):
    """Nível de prioridade da requisição."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EnhancedSelectionContext(BaseModel):
    """Contexto de seleção expandido com critérios adicionais."""

    # Critérios originais
    task_type: TaskType
    expected_input_tokens: int
    expected_output_tokens: int
    requires_streaming: bool = False
    requires_function_calling: bool = False
    requires_vision: bool = False
    max_latency_ms: Optional[float] = None
    max_cost_usd: Optional[float] = None
    min_quality_score: Optional[float] = None

    # Novos critérios de especialização
    domain: Optional[Domain] = None
    require_domain_expertise: bool = False

    # Requisitos de compliance
    compliance_requirements: list[ComplianceRequirement] = Field(default_factory=list)
    data_residency: Optional[DataResidencyRequirement] = None

    # Prioridade e SLA
    priority: PriorityLevel = PriorityLevel.MEDIUM
    max_retry_attempts: int = Field(default=3, ge=0, le=10)
    require_high_availability: bool = False

    # Preferências do utilizador
    provider_preference: Optional[str] = None
    exclude_providers: set[str] = Field(default_factory=set)
    model_preference: Optional[str] = None

    # Factores dinâmicos
    consider_load: bool = True
    consider_time_of_day: bool = False
    current_hour: Optional[int] = Field(default=None, ge=0, le=23, description="Hora actual (0-23)")

    # Filtros de confiabilidade
    min_uptime_percentage: float = Field(default=95.0, ge=0.0, le=100.0)
    min_success_rate: float = Field(default=0.95, ge=0.0, le=1.0)

    # Feedback do utilizador
    require_positive_user_feedback: bool = False
    min_user_rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)

    # Factores operacionais
    require_enterprise_tier: bool = False
    require_encryption: bool = True

    model_config = {"use_enum_values": True}


class ExtendedSelectionCriteria(str, Enum):
    """Critérios de seleção extendidos."""

    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    HIGHEST_QUALITY = "highest_quality"
    CUSTOM = "custom"

    # Novos critérios
    HIGHEST_DOMAIN_QUALITY = "highest_domain_quality"
    MOST_RELIABLE = "most_reliable"
    BEST_USER_SATISFACTION = "best_user_satisfaction"
    BEST_COMPLIANCE = "best_compliance"
    OPTIMAL_COMPOSITE = "optimal_composite"
    PRIORITY_AWARE = "priority_aware"


class ExtendedSelectionWeights(BaseModel):
    """Pesos extendidos para seleção customizada."""

    # Pesos originais
    performance_weight: float = 0.25
    cost_weight: float = 0.25
    quality_weight: float = 0.20

    # Novos pesos
    domain_quality_weight: float = 0.10
    reliability_weight: float = 0.10
    user_feedback_weight: float = 0.05
    compliance_weight: float = 0.05

    def validate(self) -> None:
        """Valida que soma dos pesos é 1.0."""
        total = (
            self.performance_weight
            + self.cost_weight
            + self.quality_weight
            + self.domain_quality_weight
            + self.reliability_weight
            + self.user_feedback_weight
            + self.compliance_weight
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Soma dos pesos deve ser 1.0, actual: {total}")
