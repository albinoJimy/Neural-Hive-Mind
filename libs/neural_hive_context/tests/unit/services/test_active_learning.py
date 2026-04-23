"""
Testes para Active Learning Service.

TDD: Testes escritos antes da implementação final.
"""

import pytest

from neural_hive_context.services.active_learning import StubActiveLearningService
from neural_hive_context.interfaces import (
    ActiveLearningSignal,
    ActiveLearningPriority,
)


@pytest.fixture
def active_learning_service():
    """Fixture para StubActiveLearningService."""
    return StubActiveLearningService()


class TestActiveLearningSignal:
    """Testes para ActiveLearningSignal."""

    def test_signal_none(self):
        """Sinal none deve ter valores padrão."""
        signal = ActiveLearningSignal.none()

        assert signal.priority == ActiveLearningPriority.NONE
        assert signal.information_value == 0.0
        assert signal.should_collect is False
        assert "sem valor" in signal.reason.lower()

    def test_signal_from_value_critical(self):
        """Valor >= 0.8 deve ser CRITICAL."""
        signal = ActiveLearningSignal.from_value(0.85)

        assert signal.priority == ActiveLearningPriority.CRITICAL
        assert signal.should_collect is True
        assert "crítico" in signal.reason.lower()

    def test_signal_from_value_high(self):
        """Valor >= threshold deve ser HIGH."""
        signal = ActiveLearningSignal.from_value(0.7, threshold=0.6)

        assert signal.priority == ActiveLearningPriority.HIGH
        assert signal.should_collect is True

    def test_signal_from_value_medium(self):
        """Valor >= 70% do threshold deve ser MEDIUM."""
        signal = ActiveLearningSignal.from_value(0.45, threshold=0.6)

        assert signal.priority == ActiveLearningPriority.MEDIUM
        assert signal.should_collect is False

    def test_signal_from_value_low(self):
        """Valor >= 50% do threshold deve ser LOW."""
        signal = ActiveLearningSignal.from_value(0.35, threshold=0.6)

        assert signal.priority == ActiveLearningPriority.LOW
        assert signal.should_collect is False

    def test_signal_from_value_none(self):
        """Valor < 50% do threshold deve ser NONE."""
        signal = ActiveLearningSignal.from_value(0.2, threshold=0.6)

        assert signal.priority == ActiveLearningPriority.NONE
        assert signal.should_collect is False

    def test_signal_to_dict(self):
        """Sinal deve ser convertido para dicionário."""
        signal = ActiveLearningSignal.from_value(0.75)
        d = signal.to_dict()

        assert "priority" in d
        assert "information_value" in d
        assert "should_collect" in d
        assert "reason" in d
        assert d["information_value"] == 0.75


class TestStubActiveLearningService:
    """Testes para StubActiveLearningService."""

    @pytest.mark.asyncio
    async def test_calculate_information_value_low_confidence(self, active_learning_service):
        """Baixa confiança deve resultar em alto valor informacional."""
        value = await active_learning_service.calculate_information_value(
            intent_text="gere um relatório",
            confidence=0.3,
            workflow_type="generation",
        )

        # 1.0 - 0.3 = 0.7, * 1.2 (generation) = 0.84
        assert value > 0.7

    @pytest.mark.asyncio
    async def test_calculate_information_value_high_confidence(self, active_learning_service):
        """Alta confiança deve resultar em baixo valor informacional."""
        value = await active_learning_service.calculate_information_value(
            intent_text="analise os dados",
            confidence=0.95,
            workflow_type="orchestration",
        )

        # 1.0 - 0.95 = 0.05
        assert value < 0.1

    @pytest.mark.asyncio
    async def test_calculate_information_value_with_explicit_value(self, active_learning_service):
        """Valor explícito em features deve override cálculo."""
        value = await active_learning_service.calculate_information_value(
            intent_text="teste",
            confidence=0.5,
            workflow_type="generation",
            additional_features={"information_value": 0.9},
        )

        assert value == 0.9

    @pytest.mark.asyncio
    async def test_should_enqueue_for_collection_above_threshold(self, active_learning_service):
        """Valor acima do threshold deve enfileirar."""
        should = await active_learning_service.should_enqueue_for_collection(
            information_value=0.7,
            threshold=0.6,
        )

        assert should is True

    @pytest.mark.asyncio
    async def test_should_enqueue_for_collection_below_threshold(self, active_learning_service):
        """Valor abaixo do threshold não deve enfileirar."""
        should = await active_learning_service.should_enqueue_for_collection(
            information_value=0.5,
            threshold=0.6,
        )

        assert should is False

    @pytest.mark.asyncio
    async def test_should_enqueue_for_collection_at_threshold(self, active_learning_service):
        """Valor igual ao threshold deve enfileirar."""
        should = await active_learning_service.should_enqueue_for_collection(
            information_value=0.6,
            threshold=0.6,
        )

        assert should is True

    @pytest.mark.asyncio
    async def test_extract_signal_high_priority(self, active_learning_service):
        """Extrair sinal com alta prioridade."""
        signal = await active_learning_service.extract_signal(
            intent_text="gere um relatório complexo",
            confidence=0.3,
            workflow_type="generation",
        )

        assert signal.information_value > 0.7
        assert signal.should_collect is True
        assert signal.priority in [ActiveLearningPriority.HIGH, ActiveLearningPriority.CRITICAL]

    @pytest.mark.asyncio
    async def test_extract_signal_low_priority(self, active_learning_service):
        """Extrair sinal com baixa prioridade."""
        signal = await active_learning_service.extract_signal(
            intent_text="analise os dados",
            confidence=0.95,
            workflow_type="orchestration",
        )

        assert signal.information_value < 0.2
        assert signal.should_collect is False
        assert signal.priority == ActiveLearningPriority.NONE

    @pytest.mark.asyncio
    async def test_extract_signal_to_dict(self, active_learning_service):
        """Sinal extraído deve ser conversível para dict."""
        signal = await active_learning_service.extract_signal(
            intent_text="teste",
            confidence=0.5,
            workflow_type="generation",
        )

        d = signal.to_dict()
        assert isinstance(d, dict)
        assert "priority" in d
