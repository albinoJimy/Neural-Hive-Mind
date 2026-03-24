"""
Testes unitários para PatternRegistry.

Este módulo testa o repositório MongoDB de padrões de avaliação.
"""

import pytest
from datetime import datetime

from neural_hive_specialists.evolution_hooks.pattern_registry import PatternRegistry
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    TaskCountRange,
    DEFAULT_WEIGHTS,
)


@pytest.mark.asyncio
class TestPatternRegistry:
    """Testes para PatternRegistry."""

    async def test_store_evaluation(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa armazenar uma avaliação."""
        registry = PatternRegistry(mongo_client)

        pattern_id = await registry.store_evaluation(
            "plan-123",
            sample_fingerprint,
            sample_evaluation
        )

        assert pattern_id is not None
        assert isinstance(pattern_id, str)

        # Verificar que foi armazenado
        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc is not None
        assert doc["plan_id"] == "plan-123"
        assert doc["fingerprint"]["domain"] == "technical"

    async def test_store_multiple_evaluations(self, mongo_client):
        """Testa armazenar múltiplas avaliações."""
        registry = PatternRegistry(mongo_client)

        for i in range(5):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"TEST-{i}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7 + (i * 0.05),
                risk_score=0.3 - (i * 0.05),
                recommendation="approve"
            )
            pattern_id = await registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)
            assert pattern_id is not None

        # Contar documentos
        count = await registry.collection.count_documents({})
        assert count == 5

    async def test_add_feedback(self, mongo_client, sample_fingerprint, sample_evaluation, sample_feedback):
        """Testa adicionar feedback a uma avaliação existente."""
        registry = PatternRegistry(mongo_client)

        # Armazenar avaliação
        pattern_id = await registry.store_evaluation(
            "plan-123",
            sample_fingerprint,
            sample_evaluation
        )

        # Adicionar feedback
        updated = await registry.add_feedback("plan-123", sample_feedback)
        assert updated is True

        # Verificar que feedback foi adicionado
        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc["feedback"]["outcome"] == "approve"
        assert doc["feedback"]["source"] == "human"

    async def test_add_feedback_with_corrected_weights(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa adicionar feedback com pesos corrigidos."""
        registry = PatternRegistry(mongo_client)

        await registry.store_evaluation("plan-123", sample_fingerprint, sample_evaluation)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN
        )
        corrected_weights = {"maintainability": 0.30, "scalability": 0.20}

        updated = await registry.add_feedback(
            "plan-123",
            feedback,
            corrected_weights=corrected_weights
        )
        assert updated is True

        # Verificar pesos corrigidos
        doc = await registry.collection.find_one({"plan_id": "plan-123"})
        assert doc["feedback"]["corrected_weights"] == corrected_weights

    async def test_add_feedback_nonexistent_plan(self, mongo_client, sample_feedback):
        """Testa adicionar feedback a plano inexistente."""
        registry = PatternRegistry(mongo_client)

        updated = await registry.add_feedback("nonexistent-plan", sample_feedback)
        assert updated is False

    async def test_find_similar_patterns_by_domain(self, mongo_client):
        """Testa buscar padrões similares por domínio."""
        registry = PatternRegistry(mongo_client)

        # Inserir padrões
        for i in range(5):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"TEST-{i}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7 + (i * 0.05),
                risk_score=0.3 - (i * 0.05),
                recommendation="approve"
            )
            await registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        # Buscar similares
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="TEST-1"
        )

        similar = await registry.find_similar_patterns(search_fingerprint, limit=10)
        assert len(similar) >= 5

    async def test_find_similar_patterns_with_jaccard_filtering(self, mongo_client):
        """Testa filtragem por similaridade Jaccard."""
        registry = PatternRegistry(mongo_client)

        # Inserir padrões com task_types diferentes
        fingerprint1 = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST", "DEPLOY"],
            avg_dependency_count=1.5,
            complexity_signature="TEST-1"
        )
        fingerprint2 = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["CODE_REVIEW"],  # Disjunto
            avg_dependency_count=0.0,
            complexity_signature="TEST-2"
        )

        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )

        await registry.store_evaluation("plan-1", fingerprint1, evaluation)
        await registry.store_evaluation("plan-2", fingerprint2, evaluation)

        # Buscar com similaridade mínima alta
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="TEST-0"
        )

        similar = await registry.find_similar_patterns(
            search_fingerprint,
            limit=10,
            min_similarity=0.5
        )
        # Deve retornar apenas fingerprint1 (similaridade 0.67)
        assert len(similar) >= 1
        # Verificar que task_types têm similaridade
        for pattern in similar:
            if pattern.fingerprint.task_types == ["BUILD", "TEST", "DEPLOY"]:
                # Jaccard({BUILD, TEST}, {BUILD, TEST, DEPLOY}) = 2/3 = 0.67
                assert hasattr(pattern, "_similarity_score")

    async def test_jaccard_similarity_calculation(self, mongo_client):
        """Testa cálculo de similaridade Jaccard."""
        registry = PatternRegistry(mongo_client)

        # Conjuntos idênticos
        assert registry._calculate_jaccard({"A", "B"}, {"A", "B"}) == 1.0

        # Subconjunto
        assert registry._calculate_jaccard(
            {"A", "B", "C"},
            {"A", "B"}
        ) == pytest.approx(0.667, abs=0.01)

        # Conjuntos disjuntos
        assert registry._calculate_jaccard({"A", "B"}, {"C", "D"}) == 0.0

        # Um conjunto vazio
        assert registry._calculate_jaccard(set(), set()) == 1.0

    async def test_update_metrics_success(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa atualizar métricas após feedback positivo."""
        registry = PatternRegistry(mongo_client)

        pattern_id = await registry.store_evaluation(
            "plan-123",
            sample_fingerprint,
            sample_evaluation
        )

        # Atualizar métricas (sucesso)
        await registry.update_metrics(pattern_id, success=True)

        # Verificar atualização
        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc["metrics"]["times_matched"] == 1
        assert doc["metrics"]["success_rate"] == 1.0  # (0.5 * 0 + 1.0) / 1 = 1.0

    async def test_update_metrics_failure(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa atualizar métricas após feedback negativo."""
        registry = PatternRegistry(mongo_client)

        pattern_id = await registry.store_evaluation(
            "plan-123",
            sample_fingerprint,
            sample_evaluation
        )

        # Atualizar métricas (falha)
        await registry.update_metrics(pattern_id, success=False)

        # Verificar atualização
        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc["metrics"]["times_matched"] == 1
        assert doc["metrics"]["success_rate"] == 0.0  # (0.5 * 0 + 0.0) / 1 = 0.0

    async def test_update_metrics_multiple_times(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa atualizar métricas múltiplas vezes."""
        registry = PatternRegistry(mongo_client)

        pattern_id = await registry.store_evaluation(
            "plan-123",
            sample_fingerprint,
            sample_evaluation
        )

        # 3 sucessos, 2 falhas
        for _ in range(3):
            await registry.update_metrics(pattern_id, success=True)
        for _ in range(2):
            await registry.update_metrics(pattern_id, success=False)

        # Verificar métricas finais
        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc["metrics"]["times_matched"] == 5
        # Success rate esperado: (0.5*0 + 1+1+1+0+0) / 5 = 3/5 = 0.6
        assert doc["metrics"]["success_rate"] == pytest.approx(0.6, abs=0.01)

    async def test_get_pattern_by_plan_id(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa buscar padrão por plan_id."""
        registry = PatternRegistry(mongo_client)

        await registry.store_evaluation("plan-123", sample_fingerprint, sample_evaluation)

        pattern = await registry.get_pattern_by_plan_id("plan-123")
        assert pattern is not None
        assert pattern.plan_id == "plan-123"
        assert pattern.fingerprint.domain == "technical"

    async def test_get_pattern_by_nonexistent_plan_id(self, mongo_client):
        """Testa buscar padrão por plan_id inexistente."""
        registry = PatternRegistry(mongo_client)

        pattern = await registry.get_pattern_by_plan_id("nonexistent")
        assert pattern is None

    async def test_count_patterns_by_domain(self, mongo_client):
        """Testa contar padrões por domínio."""
        registry = PatternRegistry(mongo_client)

        # Inserir padrões de diferentes domínios
        for i in range(3):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                avg_dependency_count=1.0,
                complexity_signature=f"TECH-{i}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="approve"
            )
            await registry.store_evaluation(f"tech-plan-{i}", fingerprint, evaluation)

        for i in range(2):
            fingerprint = Fingerprint(
                domain="business",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                avg_dependency_count=0.5,
                complexity_signature=f"BIZ-{i}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="approve"
            )
            await registry.store_evaluation(f"biz-plan-{i}", fingerprint, evaluation)

        # Contar
        tech_count = await registry.count_patterns_by_domain("technical")
        biz_count = await registry.count_patterns_by_domain("business")

        assert tech_count == 3
        assert biz_count == 2

    async def test_get_statistics(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa obter estatísticas gerais."""
        registry = PatternRegistry(mongo_client)

        # Inserir alguns padrões
        for i in range(5):
            await registry.store_evaluation(f"plan-{i}", sample_fingerprint, sample_evaluation)

        # Adicionar feedback a alguns
        await registry.add_feedback("plan-0", FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN
        ))
        await registry.add_feedback("plan-1", FeedbackData(
            outcome=FeedbackOutcome.REJECT,
            source=FeedbackSource.HUMAN
        ))

        # Obter estatísticas
        stats = await registry.get_statistics()

        assert stats["total_patterns"] == 5
        assert stats["patterns_with_feedback"] == 2
        assert stats["approved_count"] == 1
        assert stats["rejected_count"] == 1
        assert "technical" in stats["domain_distribution"]

    async def test_find_similar_empty_result(self, mongo_client):
        """Testa buscar padrões similares quando não existem."""
        registry = PatternRegistry(mongo_client)

        fingerprint = Fingerprint(
            domain="nonexistent",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=0.0,
            complexity_signature="NONE"
        )

        similar = await registry.find_similar_patterns(fingerprint)
        assert len(similar) == 0


class TestPatternRegistryEdgeCases:
    """Testes de casos extremos para PatternRegistry."""

    async def test_store_with_duplicate_plan_id(self, mongo_client, sample_fingerprint, sample_evaluation):
        """Testa armazenar com plan_id duplicado (MongoDB deve permitir)."""
        registry = PatternRegistry(mongo_client)

        # Primeira inserção
        pattern_id1 = await registry.store_evaluation("plan-123", sample_fingerprint, sample_evaluation)
        # Segunda inserção (deve criar novo documento)
        pattern_id2 = await registry.store_evaluation("plan-123", sample_fingerprint, sample_evaluation)

        # Ambos devem ter IDs diferentes
        assert pattern_id1 != pattern_id2

    async def test_find_similar_limit_parameter(self, mongo_client):
        """Testa parâmetro limit em find_similar_patterns."""
        registry = PatternRegistry(mongo_client)

        # Inserir 10 padrões
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                avg_dependency_count=1.0,
                complexity_signature=f"TEST-{i:02d}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="approve"
            )
            await registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        # Buscar com limit=5
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="TEST-00"
        )

        similar = await registry.find_similar_patterns(search_fingerprint, limit=5)
        assert len(similar) <= 5

    async def test_complexity_signature_prefix_matching(self, mongo_client):
        """Testa matching por prefixo de complexity_signature."""
        registry = PatternRegistry(mongo_client)

        # Inserir com signature "T-M-B-T-D"
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=1.5,
            complexity_signature="T-M-B-T-D"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        await registry.store_evaluation("plan-1", fingerprint, evaluation)

        # Buscar com prefixo "T-M" (deve encontrar)
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=1.0,
            complexity_signature="T-M-X-X-X"
        )

        similar = await registry.find_similar_patterns(search_fingerprint)
        assert len(similar) > 0

    async def test_mixed_domain_search(self, mongo_client):
        """Testa busca com domínios diferentes (não deve cruzar)."""
        registry = PatternRegistry(mongo_client)

        # Inserir padrão técnico
        tech_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=1.0,
            complexity_signature="TECH"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        await registry.store_evaluation("tech-plan", tech_fingerprint, evaluation)

        # Buscar com domínio business (não deve encontrar)
        biz_fingerprint = Fingerprint(
            domain="business",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=0.5,
            complexity_signature="TECH"
        )

        similar = await registry.find_similar_patterns(biz_fingerprint)
        assert len(similar) == 0
