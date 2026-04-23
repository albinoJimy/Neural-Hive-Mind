"""
Active Learning Service - Default Implementation.

Implementação stub para quando não há serviço de Active Learning configurado.
Em produção, integrar com neural_hive_specialists.feedback.active_learning.
"""

import random
from typing import Optional

from neural_hive_context.interfaces.active_learning import (
    IActiveLearningService,
    ActiveLearningSignal,
)
from neural_hive_context.models import WorkflowType


class StubActiveLearningService(IActiveLearningService):
    """
    Implementação stub de Active Learning.

    Esta implementação não requer dependências externas e pode ser usada
    como fallback quando o serviço completo não está disponível.

    Em produção, substituir por integração com:
    - neural_hive_specialists.feedback.active_learning.ActiveLearningStrategy
    """

    def __init__(
        self,
        enable_randomness: bool = False,
        default_threshold: float = 0.6,
    ):
        """
        Inicializa o serviço stub.

        Args:
            enable_randomness: Se True, adiciona variação aleatória para testes
            default_threshold: Threshold padrão para coleta
        """
        self.enable_randomness = enable_randomness
        self.default_threshold = default_threshold

    async def calculate_information_value(
        self,
        intent_text: str,
        confidence: float,
        workflow_type: str,
        additional_features: Optional[dict] = None,
    ) -> float:
        """
        Calcula valor informacional baseado em heurística simples.

        Heurística stub:
        - Baixa confiança aumenta valor
        - Features adicionais podem override

        Args:
            intent_text: Texto do intent
            confidence: Confiança da classificação (0-1)
            workflow_type: Tipo de workflow
            additional_features: Features adicionais

        Returns:
            Valor informacional (0.0-1.0)
        """
        # Se há valor explícito em features, usa ele
        if additional_features and "information_value" in additional_features:
            return additional_features["information_value"]

        # Caso contrário, usa heurística baseada em incerteza
        uncertainty_value = 1.0 - confidence

        # Ajuste baseado no tipo de workflow
        # Generation intents tendem a ser mais valiosos para coleta
        if workflow_type == WorkflowType.GENERATION or workflow_type == "generation":
            uncertainty_value *= 1.2

        # Adiciona variação aleatória se habilitado
        if self.enable_randomness:
            uncertainty_value += random.uniform(-0.1, 0.1)

        return max(0.0, min(1.0, uncertainty_value))

    async def should_enqueue_for_collection(
        self,
        information_value: float,
        threshold: float = 0.6,
    ) -> bool:
        """
        Determina se caso deve ser enfileirado para coleta.

        Args:
            information_value: Valor informacional
            threshold: Threshold mínimo

        Returns:
            True se deve enfileirar
        """
        return information_value >= threshold

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
            ActiveLearningSignal completo
        """
        info_value = await self.calculate_information_value(
            intent_text=intent_text,
            confidence=confidence,
            workflow_type=workflow_type,
            additional_features=additional_features,
        )

        should_collect = await self.should_enqueue_for_collection(
            information_value=info_value,
            threshold=self.default_threshold,
        )

        return ActiveLearningSignal.from_value(
            value=info_value,
            threshold=self.default_threshold,
        )
