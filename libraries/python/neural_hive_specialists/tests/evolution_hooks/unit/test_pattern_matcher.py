"""Unit tests for PatternMatcher."""

import pytest

from neural_hive_specialists.evolution_hooks.models import (
    EvolutionEvaluation,
    Fingerprint,
    TaskCountRange,
)
from neural_hive_specialists.evolution_hooks.pattern_matcher import PatternMatcher


@pytest.fixture()
async def matcher(mongo_client):
    """Matcher com database limpo."""
    # Limpar collection mock
    db = mongo_client["test_neural_hive_specialists"]
    collection = db["evolution_pattern_registry"]
    collection.data.clear()

    matcher = PatternMatcher(mongo_client)
    return matcher


@pytest.mark.asyncio()
class TestPatternMatcher:
    """Testes para PatternMatcher."""

    async def test_find_similar_empty_db(self, matcher):
        """Retorna lista vazia quando DB vazio."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-abcd",
        )

        similar = await matcher.find_similar(fingerprint, limit=10)

        assert similar == []
        assert matcher.get_match_count(fingerprint) == 0

    async def test_find_similar_by_domain(self, matcher):
        """Encontra padroes do mesmo dominio."""
        # Inserir padroes de mesmo dominio
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
            await matcher.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        # Buscar
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-9999",
        )

        similar = await matcher.find_similar(search_fingerprint, limit=10)

        assert len(similar) == 3

    async def test_respects_limit(self, matcher):
        """Respeita limite de resultados."""
        # Inserir 20 padroes
        for i in range(20):
            fingerprint = Fingerprint(
                domain="business",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["ANALYZE"],
                avg_dependency_count=0.5,
                complexity_signature=f"B-M-{i:04d}",
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7, risk_score=0.3, recommendation="approve"
            )
            await matcher.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["ANALYZE"],
            avg_dependency_count=0.5,
            complexity_signature="B-M-9999",
        )

        similar = await matcher.find_similar(search_fingerprint, limit=5)

        assert len(similar) <= 5
