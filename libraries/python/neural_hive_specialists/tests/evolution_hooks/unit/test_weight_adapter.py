"""Unit tests for WeightAdapter."""

import pytest

from neural_hive_specialists.evolution_hooks.models import (
    DEFAULT_WEIGHTS,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    Fingerprint,
    TaskCountRange,
)
from neural_hive_specialists.evolution_hooks.weight_adapter import WeightAdapter


@pytest.fixture()
async def adapter(mongo_client):
    """Adapter com database limpo."""
    # Limpar collection mock
    db = mongo_client["test_neural_hive_specialists"]
    collection = db["evolution_pattern_registry"]
    collection.data.clear()

    adapter = WeightAdapter(mongo_client, min_similar_patterns=5)
    return adapter


@pytest.mark.asyncio()
class TestWeightAdapter:
    """Testes para WeightAdapter."""

    async def test_adapt_with_no_history(self, adapter):
        """Sem histórico = retorna pesos default."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-abcd",
        )

        weights = await adapter.adapt_weights(fingerprint)

        assert weights == DEFAULT_WEIGHTS

    async def test_adapt_with_insufficient_similar(self, adapter):
        """Com menos de min_similar_patterns = retorna pesos default."""
        # Inserir apenas 3 padrões
        for i in range(3):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"T-M-{i:04d}",
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7, risk_score=0.3, recommendation="approve"
            )
            await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        assert weights == DEFAULT_WEIGHTS

    async def test_adapt_with_success_history(self, adapter):
        """Com histórico de sucesso = ajusta pesos."""
        # Criar padrões onde maintainability teve sucesso
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"T-M-{i:04d}",
            )

            # Quando maintainability weight é alto, outcome é approve
            weights_high_maintainability = {**DEFAULT_WEIGHTS, "maintainability": 0.30}
            evaluation = EvolutionEvaluation(
                confidence_score=0.8,
                risk_score=0.2,
                recommendation="approve",
                weights_used=weights_high_maintainability,
            )
            pattern_id = await adapter.registry.store_evaluation(
                f"plan-{i}", fingerprint, evaluation
            )

            # Adicionar feedback positivo
            feedback = FeedbackData(outcome=FeedbackOutcome.APPROVE, source=FeedbackSource.SYSTEM)
            await adapter.registry.add_feedback(f"plan-{i}", feedback)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        # maintainability deve ter aumentado
        assert weights["maintainability"] > DEFAULT_WEIGHTS["maintainability"]
        assert weights["maintainability"] <= DEFAULT_WEIGHTS["maintainability"] + 0.05

    async def test_adapt_max_adjustment_limit(self, adapter):
        """Respeita limite máximo de ajuste."""
        # Criar muitos padrões com forte correlação
        for i in range(50):
            fingerprint = Fingerprint(
                domain="business",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["ANALYZE"],
                avg_dependency_count=0.5,
                complexity_signature=f"B-M-{i:04d}",
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.9,
                risk_score=0.1,
                recommendation="approve",
                weights_used={**DEFAULT_WEIGHTS, "extensibility": 0.30},
            )
            pattern_id = await adapter.registry.store_evaluation(
                f"plan-{i}", fingerprint, evaluation
            )

            feedback = FeedbackData(outcome=FeedbackOutcome.APPROVE, source=FeedbackSource.SYSTEM)
            await adapter.registry.add_feedback(f"plan-{i}", feedback)

        search_fingerprint = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["ANALYZE"],
            avg_dependency_count=0.5,
            complexity_signature="B-M-9999",
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        # Ajuste máximo é 0.05
        for weight_name, value in weights.items():
            default = DEFAULT_WEIGHTS[weight_name]
            adjustment = abs(value - default)
            assert adjustment <= 0.05

    async def test_weights_sum_to_one(self, adapter):
        """Pesos ajustados sempre somam 1.0."""
        # Inserir padrões suficientes
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"T-M-{i:04d}",
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7, risk_score=0.3, recommendation="approve"
            )
            await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        total = sum(weights.values())
        assert total == pytest.approx(1.0, abs=0.01)

    async def test_decreases_weight_on_poor_performance(self, adapter):
        """Diminui peso quando taxa de sucesso baixa com peso alto."""
        # Criar padrões onde maintainability teve sucesso quando BAIXO
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"T-M-{i:04d}",
            )

            # Quando maintainability weight é baixo, outcome é approve
            weights_low_maintainability = {**DEFAULT_WEIGHTS, "maintainability": 0.10}
            evaluation = EvolutionEvaluation(
                confidence_score=0.8,
                risk_score=0.2,
                recommendation="approve",
                weights_used=weights_low_maintainability,
            )
            pattern_id = await adapter.registry.store_evaluation(
                f"plan-{i}", fingerprint, evaluation
            )

            # Adicionar feedback positivo
            feedback = FeedbackData(outcome=FeedbackOutcome.APPROVE, source=FeedbackSource.SYSTEM)
            await adapter.registry.add_feedback(f"plan-{i}", feedback)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        # maintainability deve ter diminuído
        assert weights["maintainability"] < DEFAULT_WEIGHTS["maintainability"]

    async def test_returns_copy_of_default_weights(self, adapter):
        """Retorna cópia dos pesos default, não referência."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-abcd",
        )

        weights1 = await adapter.adapt_weights(fingerprint)
        weights2 = await adapter.adapt_weights(fingerprint)

        # Modificar weights1 não deve afetar weights2
        weights1["maintainability"] = 0.99

        assert weights2["maintainability"] == DEFAULT_WEIGHTS["maintainability"]

    async def test_handles_patterns_without_feedback(self, adapter):
        """Ignora padrões sem feedback."""
        # Inserir padrões sem feedback
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"T-M-{i:04d}",
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7, risk_score=0.3, recommendation="approve"
            )
            await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        # Não deve falhar, retorna default
        weights = await adapter.adapt_weights(search_fingerprint)

        assert weights == DEFAULT_WEIGHTS

    async def test_all_weight_names_present(self, adapter):
        """Todos os nomes de peso estão presentes no resultado."""
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"T-M-{i:04d}",
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7, risk_score=0.3, recommendation="approve"
            )
            await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        assert set(weights.keys()) == set(DEFAULT_WEIGHTS.keys())
