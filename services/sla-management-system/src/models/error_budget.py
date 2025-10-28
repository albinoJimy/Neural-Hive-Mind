"""
Modelos Pydantic para error budgets calculados.
"""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
import uuid


class BudgetStatus(str, Enum):
    """Status do budget."""
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXHAUSTED = "EXHAUSTED"


class BurnRateLevel(str, Enum):
    """Nível de burn rate."""
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    FAST = "FAST"
    CRITICAL = "CRITICAL"


class BurnRate(BaseModel):
    """Taxa de consumo do budget."""
    window_hours: int = Field(..., description="Janela de análise")
    rate: float = Field(..., description="Taxa de consumo (multiplicador)")
    level: BurnRateLevel = Field(..., description="Nível da taxa")
    estimated_exhaustion_hours: Optional[float] = Field(
        None,
        description="Horas até esgotar budget"
    )


class ErrorBudget(BaseModel):
    """Budget de erro calculado."""

    budget_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    slo_id: str = Field(..., description="Referência ao SLO")
    service_name: str = Field(...)
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    window_start: datetime = Field(...)
    window_end: datetime = Field(...)
    sli_value: float = Field(..., description="Valor atual do SLI")
    slo_target: float = Field(..., description="Target do SLO")
    error_budget_total: float = Field(..., description="Budget total permitido (%)")
    error_budget_consumed: float = Field(..., description="Budget consumido (%)")
    error_budget_remaining: float = Field(..., description="Budget restante (%)")
    status: BudgetStatus = Field(...)
    burn_rates: List[BurnRate] = Field(default_factory=list)
    violations_count: int = Field(default=0)
    last_violation_at: Optional[datetime] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def calculate_status(self) -> BudgetStatus:
        """Determina status baseado em remaining %."""
        if self.error_budget_remaining > 50:
            return BudgetStatus.HEALTHY
        elif self.error_budget_remaining > 20:
            return BudgetStatus.WARNING
        elif self.error_budget_remaining > 10:
            return BudgetStatus.CRITICAL
        else:
            return BudgetStatus.EXHAUSTED

    def is_freeze_required(self, threshold: float) -> bool:
        """Verifica se deve acionar freeze."""
        return self.error_budget_remaining <= threshold

    def to_dict(self) -> dict:
        """Serialização para JSON."""
        return self.model_dump(mode='json')

    def to_prometheus_metrics(self) -> List[Tuple[str, float, dict]]:
        """Converte para métricas Prometheus."""
        labels = {
            "slo_id": self.slo_id,
            "service_name": self.service_name
        }

        metrics = [
            ("sla_budget_remaining_percent", self.error_budget_remaining, labels),
            ("sla_budget_consumed_percent", self.error_budget_consumed, labels),
            ("sla_budget_status", self._status_to_numeric(), labels),
        ]

        for burn_rate in self.burn_rates:
            burn_labels = {**labels, "window_hours": str(burn_rate.window_hours)}
            metrics.append(("sla_burn_rate", burn_rate.rate, burn_labels))

        return metrics

    def _status_to_numeric(self) -> float:
        """Converte status para valor numérico."""
        status_map = {
            BudgetStatus.HEALTHY: 0,
            BudgetStatus.WARNING: 1,
            BudgetStatus.CRITICAL: 2,
            BudgetStatus.EXHAUSTED: 3
        }
        return status_map.get(self.status, 0)
