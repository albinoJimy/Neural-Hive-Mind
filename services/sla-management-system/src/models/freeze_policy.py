"""
Modelos Pydantic para políticas de congelamento.
"""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid


class FreezeScope(str, Enum):
    """Escopo do freeze."""
    NAMESPACE = "NAMESPACE"
    SERVICE = "SERVICE"
    GLOBAL = "GLOBAL"


# Alias for backward compatibility with operator
PolicyScope = FreezeScope


class FreezeAction(str, Enum):
    """Ação de freeze."""
    BLOCK_DEPLOY = "BLOCK_DEPLOY"
    BLOCK_SCALE = "BLOCK_SCALE"
    ALERT_ONLY = "ALERT_ONLY"


# Alias for backward compatibility with operator
PolicyAction = FreezeAction


class FreezePolicy(BaseModel):
    """Política de congelamento."""

    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Nome da política")
    description: str = Field(default="")
    scope: FreezeScope = Field(..., description="Escopo do freeze")
    target: str = Field(..., description="Namespace, service ou '*' para global")
    actions: List[FreezeAction] = Field(..., description="Ações a executar")
    trigger_threshold_percent: float = Field(
        default=20,
        description="% de budget para acionar"
    )
    auto_unfreeze: bool = Field(default=True)
    unfreeze_threshold_percent: float = Field(
        default=50,
        description="% para descongelar"
    )
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def should_trigger(self, budget) -> bool:
        """Verifica se deve acionar freeze."""
        from .error_budget import ErrorBudget
        if not isinstance(budget, ErrorBudget):
            return False
        return budget.error_budget_remaining <= self.trigger_threshold_percent

    def should_unfreeze(self, budget) -> bool:
        """Verifica se deve descongelar."""
        from .error_budget import ErrorBudget
        if not isinstance(budget, ErrorBudget) or not self.auto_unfreeze:
            return False
        return budget.error_budget_remaining >= self.unfreeze_threshold_percent

    def to_kubernetes_annotation(self) -> Dict[str, str]:
        """Converte para annotation K8s."""
        return {
            "neural-hive.io/sla-freeze": "true",
            "neural-hive.io/freeze-policy-id": self.policy_id,
            "neural-hive.io/freeze-threshold": str(self.trigger_threshold_percent),
            "neural-hive.io/freeze-actions": ",".join([a.value for a in self.actions])
        }


class FreezeEvent(BaseModel):
    """Evento de freeze."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_id: str = Field(...)
    slo_id: str = Field(...)
    service_name: str = Field(...)
    action: FreezeAction = Field(...)
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(None)
    trigger_reason: str = Field(...)
    budget_remaining_percent: float = Field(...)
    burn_rate: float = Field(default=0)
    active: bool = Field(default=True)
    metadata: Dict[str, Any] = Field(default_factory=dict)
