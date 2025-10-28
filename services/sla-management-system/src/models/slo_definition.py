"""
Modelos Pydantic para definições de SLO.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid


class SLOType(str, Enum):
    """Tipos de SLO."""
    AVAILABILITY = "AVAILABILITY"
    LATENCY = "LATENCY"
    ERROR_RATE = "ERROR_RATE"
    CUSTOM = "CUSTOM"


class SLOTarget(float, Enum):
    """Targets padrão de SLO."""
    FOUR_NINES = 0.9999  # 99.99%
    THREE_NINES_FIVE = 0.9995  # 99.95%
    THREE_NINES = 0.999  # 99.9%
    TWO_NINES_FIVE = 0.995  # 99.5%
    TWO_NINES = 0.99  # 99%


class SLIQuery(BaseModel):
    """Query para calcular SLI."""
    metric_name: str = Field(..., description="Nome da métrica Prometheus")
    query: str = Field(..., description="Query PromQL completa")
    aggregation: str = Field(default="avg", description="Tipo de agregação")
    labels: Dict[str, str] = Field(default_factory=dict, description="Labels para filtrar")


class SLODefinition(BaseModel):
    """Definição de um SLO."""

    slo_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único")
    name: str = Field(..., description="Nome descritivo")
    description: str = Field(default="", description="Descrição detalhada")
    slo_type: SLOType = Field(..., description="Tipo do SLO")
    service_name: str = Field(..., description="Serviço alvo")
    component: Optional[str] = Field(None, description="Componente específico")
    layer: str = Field(..., description="Camada arquitetural")
    target: float = Field(..., ge=0, le=1, description="Target do SLO (0-1)")
    window_days: int = Field(default=30, gt=0, description="Janela de avaliação")
    sli_query: SLIQuery = Field(..., description="Query para calcular SLI")
    error_budget_percent: float = Field(default=0, description="% de budget permitido")
    enabled: bool = Field(default=True, description="SLO ativo")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context):
        """Calcula error budget após inicialização."""
        if self.error_budget_percent == 0:
            self.error_budget_percent = self.calculate_error_budget()

    def calculate_error_budget(self) -> float:
        """Calcula error budget em % (1 - target) * 100."""
        return (1 - self.target) * 100

    def to_dict(self) -> dict:
        """Serializa para JSON."""
        return self.model_dump(mode='json')

    @classmethod
    def from_crd(cls, crd_spec: dict) -> "SLODefinition":
        """Factory method para criar de CRD Kubernetes."""
        return cls(
            name=crd_spec["name"],
            description=crd_spec.get("description", ""),
            slo_type=SLOType(crd_spec["sloType"]),
            service_name=crd_spec["serviceName"],
            component=crd_spec.get("component"),
            layer=crd_spec.get("layer", ""),
            target=crd_spec["target"],
            window_days=crd_spec.get("windowDays", 30),
            sli_query=SLIQuery(**crd_spec["sliQuery"]),
            enabled=crd_spec.get("enabled", True),
            metadata=crd_spec.get("metadata", {})
        )
