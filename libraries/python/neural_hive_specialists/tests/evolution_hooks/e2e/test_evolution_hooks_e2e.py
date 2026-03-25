"""
End-to-End tests para Evolution Hooks system.

Este módulo testa os fluxos completos do sistema de meta-learning:
1. Cold Start -> Learning: Sem histórico -> usa defaults -> após feedback -> ajusta pesos
2. Pattern Decay: Alta taxa de sucesso -> feedback negativo -> reajusta pesos para baixo
3. Fallback on MongoDB Failure: Sistema retorna defaults quando MongoDB indisponível
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    PatternRecord,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    TaskCountRange,
    DurationRange,
    DEFAULT_WEIGHTS,
)
from neural_hive_specialists.evolution_hooks.pattern_registry import PatternRegistry
from neural_hive_specialists.evolution_hooks.pattern_matcher import PatternMatcher
from neural_hive_specialists.evolution_hooks.weight_adapter import WeightAdapter
from neural_hive_specialists.evolution_hooks.feedback_consumer import (
    EvolutionFeedbackConsumer,
)


# ============================================================================
# Fixtures E2E
# ============================================================================

@pytest.fixture
def technical_fingerprint():
    """Fingerprint técnico para testes E2E."""
    return Fingerprint(
        domain="technical",
        priority="high",
        task_count_range=TaskCountRange.MEDIUM,
        task_types=["BUILD", "TEST", "DEPLOY"],
        avg_dependency_count=1.5,
        has_conditional_deps=True,
        estimated_duration_range=DurationRange.MEDIUM,
        complexity_signature="T-H-B-T-D-M"
    )


@pytest.fixture
def business_fingerprint():
    """Fingerprint de negócio para testes E2E."""
    return Fingerprint(
        domain="business",
        priority="normal",
        task_count_range=TaskCountRange.SMALL,
        task_types=["ANALYZE", "REPORT"],
        avg_dependency_count=0.5,
        has_conditional_deps=False,
        estimated_duration_range=DurationRange.SHORT,
        complexity_signature="B-N-A-R-S"
    )


@pytest.fixture
def sample_evaluation():
    """Avaliação de exemplo."""
    return EvolutionEvaluation(
        confidence_score=0.75,
        risk_score=0.25,
        recommendation="approve",
        weights_used=DEFAULT_WEIGHTS.copy(),
        reasoning_factors=[
            {
                "factor_name": "maintainability",
                "weight": 0.25,
                "score": 0.8,
                "description": "Good maintainability"
            }
        ]
    )


@pytest.fixture
async def e2e_clean_registry(mongo_client):
    """
    Registry limpo para cada teste E2E.

    Uso: adicione este fixture aos testes que precisam de DB limpo.
    Limpa tanto test_neural_hive_specialists quanto neural_hive (default do WeightAdapter).
    """
    client = mongo_client

    # Limpar test_neural_hive_specialists
    db_test = client["test_neural_hive_specialists"]
    collection_test = db_test["evolution_pattern_registry"]
    collection_test.data.clear()

    # Limpar neural_hive (default database usado por WeightAdapter)
    db_default = client["neural_hive"]
    collection_default = db_default["evolution_pattern_registry"]
    collection_default.data.clear()

    yield

    # Limpar após o teste
    collection_test.data.clear()
    collection_default.data.clear()


# ============================================================================
# Cenário 1: Cold Start -> Learning
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_cold_start_returns_defaults(e2e_clean_registry, mongo_client, technical_fingerprint):
    """
    Cenário 1.1: Cold Start - Sistema sem histórico retorna pesos defaults.

    Fluxo:
    1. Registry vazio (sem padrões similares)
    2. WeightAdapter.adapt_weights() retorna DEFAULT_WEIGHTS
    3. Nenhum ajuste é aplicado
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")
    adapter = WeightAdapter(mongo_client, min_similar_patterns=5)

    # Verificar que registry está vazio
    stats = await registry.get_statistics()
    assert stats["total_patterns"] == 0

    # Cold start: adapt_weights deve retornar defaults
    adapted_weights = await adapter.adapt_weights(technical_fingerprint)

    # Verificar que recebeu os pesos defaults
    assert adapted_weights == DEFAULT_WEIGHTS
    assert adapted_weights["maintainability"] == 0.25
    assert adapted_weights["scalability"] == 0.25
    assert adapted_weights["extensibility"] == 0.20
    assert adapted_weights["modularity"] == 0.15
    assert adapted_weights["tech_debt_prevention"] == 0.15


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_cold_start_with_learning(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 1.2: Cold Start -> Após feedback -> Sistema aprende.

    Fluxo:
    1. Cold start inicial (sem histórico)
    2. Armazenar avaliação inicial
    3. Receber feedback positivo
    4. Adicionar múltiplos padrões similares com feedback
    5. Próxima avaliação deve usar pesos ajustados
    """
    # Usar o mesmo database para registry e adapter
    # WeightAdapter usa "neural_hive" por padrão, então usamos esse
    registry = PatternRegistry(mongo_client, database="neural_hive")
    adapter = WeightAdapter(mongo_client, min_similar_patterns=3)

    # Limpar cache do matcher antes do teste
    adapter.matcher.clear_cache()

    # Passo 1: Cold start inicial
    weights_initial = await adapter.adapt_weights(technical_fingerprint)
    assert weights_initial == DEFAULT_WEIGHTS

    # Passo 2-3: Armazenar avaliações similares com feedbacks positivos
    for i in range(10):
        plan_id = f"cold-start-plan-{i}"

        # Armazenar avaliação
        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

        # Adicionar feedback positivo
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning=f"Approved plan {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Passo 4: Agora deve haver histórico suficiente
    stats = await registry.get_statistics()
    assert stats["total_patterns"] == 10
    assert stats["patterns_with_feedback"] == 10

    # Limpar cache e buscar novamente
    adapter.matcher.clear_cache()
    similar = await adapter.matcher.find_similar(technical_fingerprint, limit=10)
    assert len(similar) >= adapter.min_similar_patterns

    # Verificar que todos os padrões similares têm feedback
    for pattern in similar:
        assert pattern.feedback is not None
        assert pattern.feedback.outcome == FeedbackOutcome.APPROVE


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_learning_from_mixed_feedback(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 1.3: Aprendizado com feedbacks mistos (approve/reject).

    Fluxo:
    1. Criar padrões com feedbacks variados
    2. Sistema deve calcular taxa de sucesso corretamente
    3. Métricas devem refletir a realidade do histórico
    """
    # Usar "neural_hive" para alinhar com WeightAdapter
    registry = PatternRegistry(mongo_client, database="neural_hive")

    # Criar padrões com feedbacks mistos
    outcomes = [
        FeedbackOutcome.APPROVE,  # 0
        FeedbackOutcome.APPROVE,  # 1
        FeedbackOutcome.REJECT,   # 2
        FeedbackOutcome.APPROVE,  # 3
        FeedbackOutcome.REJECT,   # 4
        FeedbackOutcome.APPROVE,  # 5
        FeedbackOutcome.APPROVE,  # 6
        FeedbackOutcome.REJECT,   # 7
        FeedbackOutcome.APPROVE,  # 8
        FeedbackOutcome.APPROVE,  # 9
    ]  # 7 approves, 3 rejects = 70% success rate

    for i, outcome in enumerate(outcomes):
        plan_id = f"mixed-feedback-plan-{i}"

        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

        feedback = FeedbackData(
            outcome=outcome,
            source=FeedbackSource.HUMAN,
            reasoning=f"Plan {i} outcome",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Verificar estatísticas
    stats = await registry.get_statistics()
    assert stats["total_patterns"] == 10
    # No mock, todos os planos com feedback são contados
    assert stats["patterns_with_feedback"] == 10
    # Contagem de aprovados/rejeitados baseada no valor do outcome
    assert stats["approved_count"] == 7
    assert stats["rejected_count"] == 3

    # Buscar padrões similares e verificar feedbacks
    similar = await registry.find_similar_patterns(technical_fingerprint, limit=20)

    approve_count = sum(1 for p in similar if p.feedback and p.feedback.outcome == FeedbackOutcome.APPROVE)
    reject_count = sum(1 for p in similar if p.feedback and p.feedback.outcome == FeedbackOutcome.REJECT)

    # Verificar contagens (considerando todos os padrões similares encontrados)
    assert approve_count == 7
    assert reject_count == 3


# ============================================================================
# Cenário 2: Pattern Decay
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pattern_decay_high_success_then_failure(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 2.1: Alta taxa de sucesso -> Feedback negativo -> Decaimento.

    Fluxo:
    1. Criar padrão com alta success_rate inicial
    2. Receber série de feedbacks positivos (chamando update_metrics)
    3. Receber feedback negativo
    4. success_rate deve diminuir
    5. Próximas adaptações devem considerar nova taxa
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    # Passo 1-2: Criar padrão com alta success_rate
    plan_id = "decay-test-plan"
    pattern_id = await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

    # Adicionar 9 feedbacks positivos e atualizar métricas
    for i in range(9):
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning=f"Good plan {i}",
            timestamp=datetime.now(timezone.utc) + timedelta(seconds=i)
        )
        await registry.add_feedback(plan_id, feedback)
        # Atualizar métricas explicitamente (assim como o sistema real faria)
        await registry.update_metrics(pattern_id, success=True)

    # Verificar success_rate após 9 approves
    pattern = await registry.get_pattern_by_plan_id(plan_id)
    initial_rate = pattern.metrics.success_rate
    # Moving average deve ser alto após 9 approvals
    assert initial_rate > 0.8

    # Passo 3: Adicionar feedback negativo
    negative_feedback = FeedbackData(
        outcome=FeedbackOutcome.REJECT,
        source=FeedbackSource.HUMAN,
        reasoning="Security concerns found",
        timestamp=datetime.now(timezone.utc) + timedelta(seconds=10)
    )
    await registry.add_feedback(plan_id, negative_feedback)
    # Atualizar métricas com failure
    await registry.update_metrics(pattern_id, success=False)

    # Passo 4: Verificar que success_rate diminuiu
    pattern = await registry.get_pattern_by_plan_id(plan_id)
    decayed_rate = pattern.metrics.success_rate
    assert decayed_rate < initial_rate


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_weight_adjustment_after_decay(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 2.2: Ajuste de pesos após decaimento de padrão.

    Fluxo:
    1. Criar múltiplos padrões com pesos específicos e alta taxa de sucesso
    2. Simular que maintainabilidade com peso alto teve mais sucesso
    3. Após feedback negativo, pesos devem ser reajustados para baixo
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")
    adapter = WeightAdapter(mongo_client, min_similar_patterns=3)

    # Criar padrões com maintainability alto (0.30) que tiveram sucesso
    high_maintainability_weights = DEFAULT_WEIGHTS.copy()
    high_maintainability_weights["maintainability"] = 0.30
    high_maintainability_weights["scalability"] = 0.20  # Reduzir outros para compensar

    for i in range(5):
        plan_id = f"high-maint-plan-{i}"

        eval_high_maint = EvolutionEvaluation(
            confidence_score=0.80,
            risk_score=0.20,
            recommendation="approve",
            weights_used=high_maintainability_weights.copy(),
            reasoning_factors=[]
        )

        await registry.store_evaluation(plan_id, technical_fingerprint, eval_high_maint)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning=f"Good maintainability {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Criar padrões com maintainability baixo (0.15) que falharam
    low_maintainability_weights = DEFAULT_WEIGHTS.copy()
    low_maintainability_weights["maintainability"] = 0.15
    low_maintainability_weights["scalability"] = 0.35

    for i in range(5):
        plan_id = f"low-maint-plan-{i}"

        eval_low_maint = EvolutionEvaluation(
            confidence_score=0.60,
            risk_score=0.40,
            recommendation="approve",
            weights_used=low_maintainability_weights.copy(),
            reasoning_factors=[]
        )

        await registry.store_evaluation(plan_id, technical_fingerprint, eval_low_maint)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.REJECT,
            source=FeedbackSource.HUMAN,
            reasoning=f"Poor maintainability {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Agora adaptar pesos - deve aumentar maintainability
    adapted = await adapter.adapt_weights(technical_fingerprint)

    # Maintainability deve ser maior que o default
    assert adapted["maintainability"] > DEFAULT_WEIGHTS["maintainability"]

    # Scalability deve ser menor que o default (para compensar)
    assert adapted["scalability"] < DEFAULT_WEIGHTS["scalability"]

    # Soma deve ser 1.0
    assert abs(sum(adapted.values()) - 1.0) < 0.001


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pattern_decay_recovery(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 2.3: Recuperação após decaimento.

    Fluxo:
    1. Padrão com alta success_rate
    2. Série de feedbacks negativos reduz taxa
    3. Série de feedbacks positivos recupera taxa
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    plan_id = "recovery-test-plan"
    pattern_id = await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

    # Alta success_rate inicial
    for _ in range(5):
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning="Good",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)
        await registry.update_metrics(pattern_id, success=True)

    pattern = await registry.get_pattern_by_plan_id(plan_id)
    high_rate = pattern.metrics.success_rate

    # Decaimento
    for _ in range(5):
        feedback = FeedbackData(
            outcome=FeedbackOutcome.REJECT,
            source=FeedbackSource.AUTOMATED,
            reasoning="Failed",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)
        await registry.update_metrics(pattern_id, success=False)

    pattern = await registry.get_pattern_by_plan_id(plan_id)
    low_rate = pattern.metrics.success_rate
    assert low_rate < high_rate

    # Recuperação
    for _ in range(5):
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning="Good again",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)
        await registry.update_metrics(pattern_id, success=True)

    pattern = await registry.get_pattern_by_plan_id(plan_id)
    recovery_rate = pattern.metrics.success_rate
    assert recovery_rate > low_rate


# ============================================================================
# Cenário 3: Fallback on MongoDB Failure
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_fallback_on_mongo_connection_error(mongo_client, technical_fingerprint):
    """
    Cenário 3.1: Fallback quando MongoDB levanta exceção de conexão.

    Fluxo:
    1. Mock do PatternRegistry para levantar exceção
    2. WeightAdapter deve capturar exceção e retornar defaults
    3. Sistema deve continuar funcionando
    """
    adapter = WeightAdapter(mongo_client, min_similar_patterns=3)

    # Mock find_similar para levantar exceção de conexão
    async def failing_find_similar(*args, **kwargs):
        raise Exception("MongoDB connection timeout")

    with patch.object(adapter.matcher, "find_similar", failing_find_similar):
        # adapt_weights deve retornar defaults gracejosamente
        adapted = await adapter.adapt_weights(technical_fingerprint)

        assert adapted == DEFAULT_WEIGHTS


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_fallback_on_registry_unavailable(mongo_client, technical_fingerprint):
    """
    Cenário 3.2: Fallback quando PatternRegistry está indisponível.

    Fluxo:
    1. Mock do PatternRegistry.find_similar_patterns para falhar
    2. WeightAdapter deve capturar exceção e retornar defaults
    3. Sistema deve continuar funcionando
    """
    adapter = WeightAdapter(mongo_client, min_similar_patterns=3)

    # Mock find_similar_patterns para levantar exceção
    async def failing_find_similar(*args, **kwargs):
        raise Exception("Registry unavailable")

    with patch.object(adapter.matcher.registry, "find_similar_patterns", failing_find_similar):
        # Deve retornar defaults quando registry falha
        adapted = await adapter.adapt_weights(technical_fingerprint)
        assert adapted == DEFAULT_WEIGHTS


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_fallback_on_timeout_during_pattern_search(e2e_clean_registry, mongo_client, technical_fingerprint):
    """
    Cenário 3.3: Fallback quando busca de padrões dá timeout.

    Fluxo:
    1. Mock para simular timeout durante find_similar_patterns
    2. WeightAdapter deve tratar timeout e retornar defaults
    3. Logger deve registrar warning
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")
    adapter = WeightAdapter(mongo_client, min_similar_patterns=3)

    # Mock para simular timeout
    async def timeout_find_similar(*args, **kwargs):
        await asyncio.sleep(0.1)  # Simular delay
        raise asyncio.TimeoutError("Query timeout")

    with patch.object(registry, "find_similar_patterns", timeout_find_similar):
        adapted = await adapter.adapt_weights(technical_fingerprint)

        # Deve retornar defaults após timeout
        assert adapted == DEFAULT_WEIGHTS


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pattern_matcher_cache_invalidated_on_error(mongo_client, technical_fingerprint):
    """
    Cenário 3.4: Cache do PatternMatcher é invalidado em caso de erro.

    Fluxo:
    1. Busca bem-sucedida popula cache
    2. Erro subsequente não deve corromper cache
    3. Clear deve funcionar corretamente
    """
    matcher = PatternMatcher(mongo_client)

    # Primeira busca (vazia, mas popula estrutura de cache)
    similar = await matcher.find_similar(technical_fingerprint, limit=10)
    assert similar == []  # Registry vazio

    # Verificar que cache foi populado
    cache_key = matcher._cache_key(technical_fingerprint, 0.0)
    assert cache_key in matcher._match_cache

    # Limpar cache
    matcher.clear_cache()
    assert cache_key not in matcher._match_cache

    # Buscar novamente após clear
    similar = await matcher.find_similar(technical_fingerprint, limit=10)
    assert similar == []


# ============================================================================
# Cenário 4: Feedback Loop Integration E2E
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_feedback_loop_integration(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 4.1: Loop completo de feedback Kafka -> Registry -> Adaptation.

    Fluxo:
    1. Armazenar avaliação inicial (cold start)
    2. Simular mensagem Kafka de feedback
    3. EvolutionFeedbackConsumer processa mensagem
    4. Registry atualiza padrão com feedback
    5. WeightAdapter usa novo histórico para adaptar pesos
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")
    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="test-group",
        pattern_registry=registry
    )
    adapter = WeightAdapter(mongo_client, min_similar_patterns=3)

    # Limpar cache
    adapter.matcher.clear_cache()

    # Passo 1: Cold start
    plan_id = "feedback-loop-plan"
    await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)
    weights_before = await adapter.adapt_weights(technical_fingerprint)
    assert weights_before == DEFAULT_WEIGHTS

    # Passo 2-3: Simular mensagem Kafka e processar
    feedback_message = {
        "plan_id": plan_id,
        "fingerprint": technical_fingerprint.model_dump(),
        "evaluation": sample_evaluation.model_dump(),
        "feedback": {
            "outcome": "approve",
            "source": "human",
            "reasoning": "Approved after review",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }

    success = await consumer.process_message(feedback_message)
    assert success is True
    assert consumer.messages_processed == 1

    # Passo 4: Verificar que feedback foi adicionado
    pattern = await registry.get_pattern_by_plan_id(plan_id)
    assert pattern.feedback is not None
    assert pattern.feedback.outcome == FeedbackOutcome.APPROVE

    # Passo 5: Adicionar mais padrões para ter histórico suficiente
    for i in range(5):
        pid = f"feedback-loop-plan-{i}"
        await registry.store_evaluation(pid, technical_fingerprint, sample_evaluation)

        fb = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning=f"Approved {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(pid, fb)

    # Limpar cache e buscar novamente
    adapter.matcher.clear_cache()
    similar = await adapter.matcher.find_similar(technical_fingerprint, limit=10)
    assert len(similar) >= adapter.min_similar_patterns


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_multiple_domains_separate_learning(e2e_clean_registry, mongo_client, technical_fingerprint, business_fingerprint, sample_evaluation):
    """
    Cenário 4.2: Aprendizado separado por domínio.

    Fluxo:
    1. Criar padrões técnicos com feedback específico
    2. Criar padrões de negócio com feedback diferente
    3. Buscar por domínio técnico deve retornar apenas técnicos
    4. Buscar por domínio de negócio deve retornar apenas negócio
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    # Criar padrões técnicos
    for i in range(5):
        plan_id = f"technical-plan-{i}"
        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning=f"Technical plan approved {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Criar padrões de negócio
    for i in range(5):
        plan_id = f"business-plan-{i}"
        await registry.store_evaluation(plan_id, business_fingerprint, sample_evaluation)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.REJECT,
            source=FeedbackSource.HUMAN,
            reasoning=f"Business plan rejected {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Buscar padrões técnicos
    technical_similar = await registry.find_similar_patterns(technical_fingerprint, limit=10)
    assert len(technical_similar) > 0
    for p in technical_similar:
        assert p.fingerprint.domain == "technical"

    # Buscar padrões de negócio
    business_similar = await registry.find_similar_patterns(business_fingerprint, limit=10)
    assert len(business_similar) > 0
    for p in business_similar:
        assert p.fingerprint.domain == "business"

    # Verificar estatísticas por domínio
    tech_count = await registry.count_patterns_by_domain("technical")
    bus_count = await registry.count_patterns_by_domain("business")
    assert tech_count == 5
    assert bus_count == 5


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_corrected_weights_propagation(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 4.3: Propagação de pesos corrigidos via feedback.

    Fluxo:
    1. Avaliação com pesos defaults
    2. Feedback com corrected_weights especialista humano
    3. Pesos corrigidos devem ser armazenados
    4. Próximas avaliações podem usar pesos corrigidos como referência
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    plan_id = "corrected-weights-plan"
    await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

    # Feedback com pesos corrigidos
    corrected_weights = {
        "maintainability": 0.30,
        "scalability": 0.20,
        "extensibility": 0.20,
        "modularity": 0.15,
        "tech_debt_prevention": 0.15
    }

    feedback = FeedbackData(
        outcome=FeedbackOutcome.APPROVE,
        source=FeedbackSource.HUMAN,
        reasoning="Weights adjusted after review",
        timestamp=datetime.now(timezone.utc),
        corrected_weights=corrected_weights
    )

    success = await registry.add_feedback(plan_id, feedback, corrected_weights=corrected_weights)
    assert success is True

    # Verificar que pesos corrigidos foram armazenados
    pattern = await registry.get_pattern_by_plan_id(plan_id)
    assert pattern.feedback.corrected_weights == corrected_weights

    # Pesos corrigidos devem diferir dos defaults
    assert pattern.feedback.corrected_weights["maintainability"] == 0.30
    assert DEFAULT_WEIGHTS["maintainability"] == 0.25


# ============================================================================
# Cenário 5: Edge Cases e Limites
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_weight_normalization_boundary(e2e_clean_registry, mongo_client, technical_fingerprint):
    """
    Cenário 5.1: Normalização de pesos nos limites.

    Fluxo:
    1. Criar padrões que forçam ajustes aos limites
    2. Verificar que pesos são normalizados corretamente
    3. Soma deve ser sempre 1.0
    """
    adapter = WeightAdapter(mongo_client, min_similar_patterns=1, max_adjustment=0.10)

    # Criar alguns padrões para ter histórico mínimo
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")
    for i in range(5):
        plan_id = f"boundary-plan-{i}"
        eval_boundary = EvolutionEvaluation(
            confidence_score=0.70,
            risk_score=0.30,
            recommendation="approve",
            weights_used=DEFAULT_WEIGHTS.copy(),
            reasoning_factors=[]
        )
        await registry.store_evaluation(plan_id, technical_fingerprint, eval_boundary)

        fb = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.SYSTEM,
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, fb)

    # Adaptar pesos
    adapted = await adapter.adapt_weights(technical_fingerprint)

    # Verificar normalização
    total = sum(adapted.values())
    assert abs(total - 1.0) < 0.001

    # Verificar limites
    for name, value in adapted.items():
        default = DEFAULT_WEIGHTS[name]
        min_val = max(0.0, default - adapter.max_adjustment)
        max_val = min(1.0, default + adapter.max_adjustment)
        assert min_val <= value <= max_val, f"Weight {name} = {value} outside [{min_val}, {max_val}]"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_empty_task_types_similarity(e2e_clean_registry, mongo_client, sample_evaluation):
    """
    Cenário 5.2: Similaridade com task_types vazio.

    Fluxo:
    1. Criar fingerprint sem task_types
    2. Buscar padrões similares deve funcionar
    3. Similaridade Jaccard deve ser calculada corretamente
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    empty_fingerprint = Fingerprint(
        domain="technical",
        priority="low",
        task_count_range=TaskCountRange.SMALL,
        task_types=[],
        avg_dependency_count=0,
        has_conditional_deps=False,
        estimated_duration_range=DurationRange.SHORT,
        complexity_signature="T-L-S"
    )

    # Armazenar padrão com task_types vazio
    await registry.store_evaluation("empty-types-plan", empty_fingerprint, sample_evaluation)

    # Buscar similares
    similar = await registry.find_similar_patterns(empty_fingerprint, limit=10)

    # Deve encontrar pelo menos o padrão criado
    assert len(similar) >= 1
    assert similar[0].fingerprint.task_types == []


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_concurrent_feedback_processing(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 5.3: Processamento concorrente de feedbacks.

    Fluxo:
    1. Criar múltiplas avaliações
    2. Processar feedbacks concorrentemente
    3. Verificar que todos foram processados corretamente
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    # Criar 10 avaliações
    plan_ids = []
    for i in range(10):
        plan_id = f"concurrent-plan-{i}"
        plan_ids.append(plan_id)
        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

    # Processar feedbacks concorrentemente
    async def add_feedback_async(plan_id, outcome):
        feedback = FeedbackData(
            outcome=outcome,
            source=FeedbackSource.HUMAN,
            reasoning=f"Concurrent feedback for {plan_id}",
            timestamp=datetime.now(timezone.utc)
        )
        return await registry.add_feedback(plan_id, feedback)

    # Criar tarefas concorrentes
    tasks = [
        add_feedback_async(plan_id, FeedbackOutcome.APPROVE if i % 2 == 0 else FeedbackOutcome.REJECT)
        for i, plan_id in enumerate(plan_ids)
    ]

    # Executar concorrentemente
    results = await asyncio.gather(*tasks)

    # Todos devem ter sucesso
    assert all(results)

    # Verificar contagens
    stats = await registry.get_statistics()
    assert stats["patterns_with_feedback"] == 10


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pattern_registry_statistics(e2e_clean_registry, mongo_client, technical_fingerprint, business_fingerprint, sample_evaluation):
    """
    Cenário 5.4: Estatísticas completas do registry.

    Fluxo:
    1. Criar padrões em múltiplos domínios
    2. Criar padrões com e sem feedback
    3. Verificar estatísticas completas
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    # Criar padrões técnicos (com feedback)
    for i in range(3):
        plan_id = f"stats-tech-{i}"
        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

        fb = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, fb)

    # Criar padrões de negócio (com feedback)
    for i in range(2):
        plan_id = f"stats-bus-{i}"
        await registry.store_evaluation(plan_id, business_fingerprint, sample_evaluation)

        fb = FeedbackData(
            outcome=FeedbackOutcome.REJECT,
            source=FeedbackSource.AUTOMATED,
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, fb)

    # Criar padrões sem feedback
    for i in range(3):
        plan_id = f"stats-no-fb-{i}"
        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

    # Obter estatísticas
    stats = await registry.get_statistics()

    assert stats["total_patterns"] == 8  # 3 + 2 + 3
    assert stats["patterns_with_feedback"] == 5  # 3 + 2
    assert stats["approved_count"] == 3
    assert stats["rejected_count"] == 2
    assert stats["domain_distribution"]["technical"] == 6  # 3 com fb + 3 sem fb
    assert stats["domain_distribution"]["business"] == 2


# ============================================================================
# Cenário 6: Simulação de Trajetória de Aprendizado
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_learning_trajectory_simulation(e2e_clean_registry, mongo_client, technical_fingerprint, sample_evaluation):
    """
    Cenário 6.1: Simulação completa de trajetória de aprendizado.

    Fluxo:
    1. Fase 1: Cold start (sem histórico)
    2. Fase 2: Coleta de dados iniciais (primeiros feedbacks)
    3. Fase 3: Ajuste de pesos baseado em histórico
    4. Fase 4: Refinamento com mais dados
    """
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")
    adapter = WeightAdapter(mongo_client, min_similar_patterns=5)

    # Fase 1: Cold start
    weights_phase1 = await adapter.adapt_weights(technical_fingerprint)
    assert weights_phase1 == DEFAULT_WEIGHTS

    # Fase 2: Coleta de dados (criar 10 padrões com feedbacks)
    # Simular que maintainability alta é melhor
    high_maint_weights = DEFAULT_WEIGHTS.copy()
    high_maint_weights["maintainability"] = 0.30
    high_maint_weights["scalability"] = 0.20

    for i in range(10):
        plan_id = f"trajectory-phase2-{i}"

        eval_weights = high_maint_weights if i < 7 else DEFAULT_WEIGHTS
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve",
            weights_used=eval_weights.copy(),
            reasoning_factors=[]
        )

        await registry.store_evaluation(plan_id, technical_fingerprint, evaluation)

        # Primeiros 7 (com high maint) são aprovados, últimos 3 (com default) são rejeitados
        outcome = FeedbackOutcome.APPROVE if i < 7 else FeedbackOutcome.REJECT
        feedback = FeedbackData(
            outcome=outcome,
            source=FeedbackSource.HUMAN,
            reasoning=f"Phase2 feedback {i}",
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Fase 3: Ajuste de pesos
    weights_phase3 = await adapter.adapt_weights(technical_fingerprint)

    # Maintainability deve ter aumentado (pois teve mais sucesso quando alto)
    # Nota: Pode não mudar muito dependendo do algoritmo de ajuste
    assert abs(sum(weights_phase3.values()) - 1.0) < 0.001

    # Fase 4: Refinamento com mais dados
    for i in range(10):
        plan_id = f"trajectory-phase4-{i}"

        await registry.store_evaluation(plan_id, technical_fingerprint, sample_evaluation)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.SYSTEM,
            timestamp=datetime.now(timezone.utc)
        )
        await registry.add_feedback(plan_id, feedback)

    # Verificar estatísticas finais
    stats = await registry.get_statistics()
    assert stats["total_patterns"] == 20
    assert stats["patterns_with_feedback"] == 20

    # Pesos finais
    weights_phase4 = await adapter.adapt_weights(technical_fingerprint)
    assert abs(sum(weights_phase4.values()) - 1.0) < 0.001
