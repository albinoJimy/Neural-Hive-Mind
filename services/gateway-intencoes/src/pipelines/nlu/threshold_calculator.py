"""Calculadora de Threshold Adaptativo para NLU.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)
"""

import logging
from typing import Any

from models.intent_envelope import NLUResult

logger = logging.getLogger(__name__)


class ThresholdCalculator:
    """Calcula threshold adaptativo baseado em confiança histórica."""

    def __init__(
        self,
        base_threshold: float = 0.6,
        min_threshold: float = 0.4,
        max_threshold: float = 0.8,
        adjustment_factor: float = 0.05,
        history_size: int = 100,
    ):
        """Inicializa calculadora de threshold.

        Args:
            base_threshold: Threshold base inicial
            min_threshold: Threshold mínimo permitido
            max_threshold: Threshold máximo permitido
            adjustment_factor: Fator de ajuste por feedback
            history_size: Tamanho do histórico de confianças
        """
        self.base_threshold = base_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.adjustment_factor = adjustment_factor
        self.history_size = history_size
        self.confidence_history: list[float] = []
        self.current_threshold = base_threshold

    async def calculate_threshold(self) -> float:
        """Calcula threshold adaptativo baseado no histórico.

        Returns:
            Threshold calculado
        """
        if not self.confidence_history:
            return self.base_threshold

        avg_confidence = sum(self.confidence_history) / len(self.confidence_history)

        # Ajustar threshold baseado na confiança média
        if avg_confidence > 0.8:
            # Alta confiança: aumentar threshold
            new_threshold = min(
                self.current_threshold + self.adjustment_factor,
                self.max_threshold,
            )
        elif avg_confidence < 0.5:
            # Baixa confiança: diminuir threshold
            new_threshold = max(
                self.current_threshold - self.adjustment_factor,
                self.min_threshold,
            )
        else:
            # Confiança média: manter threshold
            new_threshold = self.current_threshold

        self.current_threshold = new_threshold
        logger.debug(f"Threshold adaptativo calculado: {new_threshold:.3f}")
        return new_threshold

    async def record_confidence(self, confidence: float) -> None:
        """Registra confiança para cálculo futuro.

        Args:
            confidence: Valor de confiança a registrar
        """
        self.confidence_history.append(confidence)
        if len(self.confidence_history) > self.history_size:
            self.confidence_history.pop(0)

    def get_current_threshold(self) -> float:
        """Retorna threshold atual.

        Returns:
            Threshold atual
        """
        return self.current_threshold

    def should_accept(self, result: NLUResult) -> bool:
        """Decide se aceita resultado baseado no threshold atual.

        Args:
            result: Resultado NLU para avaliar

        Returns:
            True se resultado deve ser aceito
        """
        return result.confidence >= self.current_threshold

    async def update_from_result(self, result: NLUResult, accepted: bool) -> None:
        """Atualiza threshold baseado em feedback de aceitação.

        Args:
            result: Resultado NLU processado
            accepted: Se o resultado foi aceito
        """
        await self.record_confidence(result.confidence)

        if not accepted and result.confidence < self.current_threshold:
            # Rejeitado abaixo do threshold: reduzir threshold
            self.current_threshold = max(
                self.current_threshold - self.adjustment_factor,
                self.min_threshold,
            )
        elif accepted and result.confidence > self.current_threshold + 0.1:
            # Aceito bem acima do threshold: aumentar threshold
            self.current_threshold = min(
                self.current_threshold + self.adjustment_factor,
                self.max_threshold,
            )

    def reset(self) -> None:
        """Reseta threshold para valor base."""
        self.current_threshold = self.base_threshold
        self.confidence_history.clear()

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do threshold.

        Returns:
            Dicionário com estatísticas
        """
        return {
            "current_threshold": self.current_threshold,
            "base_threshold": self.base_threshold,
            "min_threshold": self.min_threshold,
            "max_threshold": self.max_threshold,
            "history_size": len(self.confidence_history),
            "avg_confidence": (
                sum(self.confidence_history) / len(self.confidence_history)
                if self.confidence_history
                else 0.0
            ),
        }
