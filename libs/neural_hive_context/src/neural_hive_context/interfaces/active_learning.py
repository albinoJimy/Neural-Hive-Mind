"""
Active Learning Interface for Context Layer.

Define interface para integração com Active Learning services,
permitindo priorizar casos para coleta de feedback estratégico.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ActiveLearningPriority(str, Enum):
    """Prioridade para coleta de feedback."""
    CRITICAL = "critical"  # Caso muito valioso, coleta urgente
    HIGH = "high"  # Acima do threshold
    MEDIUM = "medium"  # Próximo ao threshold
    LOW = "low"  # Abaixo do threshold
    NONE = "none"  # Sem valor informacional


@dataclass
class ActiveLearningSignal:
    """Sinal de Active Learning para decisão de roteamento."""

    priority: ActiveLearningPriority
    information_value: float  # 0.0-1.0
    should_collect: bool  # Se deve ser enfileirado para coleta
    reason: str = ""  # Explicação da prioridade

    @classmethod
    def none(cls) -> "ActiveLearningSignal":
        """Retorna sinal sem prioridade."""
        return cls(
            priority=ActiveLearningPriority.NONE,
            information_value=0.0,
            should_collect=False,
            reason="Sem valor informacional",
        )

    @classmethod
    def from_value(cls, value: float, threshold: float = 0.6) -> "ActiveLearningSignal":
        """Cria sinal a partir do valor informacional."""
        if value >= 0.8:
            priority = ActiveLearningPriority.CRITICAL
        elif value >= threshold:
            priority = ActiveLearningPriority.HIGH
        elif value >= threshold * 0.7:
            priority = ActiveLearningPriority.MEDIUM
        elif value >= threshold * 0.5:
            priority = ActiveLearningPriority.LOW
        else:
            priority = ActiveLearningPriority.NONE

        should_collect = value >= threshold

        reason_parts = []
        if value >= 0.8:
            reason_parts.append("valor informacional crítico")
        elif value >= threshold:
            reason_parts.append("acima do threshold")
        else:
            reason_parts.append("valor informacional baixo")

        return cls(
            priority=priority,
            information_value=value,
            should_collect=should_collect,
            reason=f"{', '.join(reason_parts)} (value={value:.2f})",
        )

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "priority": self.priority.value,
            "information_value": self.information_value,
            "should_collect": self.should_collect,
            "reason": self.reason,
        }


class IActiveLearningService(ABC):
    """
    Interface para serviços de Active Learning.

    Permite calcular valor informacional de casos
    para priorizar coleta de feedback estratégico.
    """

    @abstractmethod
    async def calculate_information_value(
        self,
        intent_text: str,
        confidence: float,
        workflow_type: str,
        additional_features: Optional[dict] = None,
    ) -> float:
        """
        Calcula valor informacional de um caso.

        Args:
            intent_text: Texto do intent
            confidence: Confiança da classificação (0-1)
            workflow_type: Tipo de workflow (orchestration/generation)
            additional_features: Features adicionais (representation, novelty, etc)

        Returns:
            Valor informacional (0.0-1.0)
        """
        pass

    @abstractmethod
    async def should_enqueue_for_collection(
        self,
        information_value: float,
        threshold: float = 0.6,
    ) -> bool:
        """
        Determina se caso deve ser enfileirado para coleta.

        Args:
            information_value: Valor informacional calculado
            threshold: Threshold mínimo para coleta

        Returns:
            True se deve enfileirar
        """
        pass

    @abstractmethod
    async def extract_signal(
        self,
        intent_text: str,
        confidence: float,
        workflow_type: str,
        additional_features: Optional[dict] = None,
    ) -> ActiveLearningSignal:
        """
        Extrai sinal completo de Active Learning.

        Args:
            intent_text: Texto do intent
            confidence: Confiança da classificação
            workflow_type: Tipo de workflow
            additional_features: Features adicionais

        Returns:
            ActiveLearningSignal com prioridade e decisão
        """
        pass
