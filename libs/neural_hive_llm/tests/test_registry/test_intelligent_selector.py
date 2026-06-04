"""
Unit tests para Intelligent Selector.
"""

import pytest

from neural_hive_llm.registry import (
    RequestMetric,
    SelectionContext,
    SelectionCriteria,
    SelectionWeights,
    SelectionResult,
    TaskType,
    get_selector,
    reset_registry,
    reset_tracker,
)


@pytest.fixture(autouse=True)
def reset_all_before_each():
    """Reseta registry e tracker antes de cada teste."""
    reset_registry()
    reset_tracker()
    yield
    reset_registry()
    reset_tracker()


@pytest.mark.asyncio
async def test_selector_initialization():
    """Testa inicialização do selector."""
    selector = get_selector()

    assert selector._registry is not None
    assert selector._tracker is not None


@pytest.mark.asyncio
async def test_select_fastest_model():
    """Testa seleção de modelo mais rápido."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=100,
        expected_output_tokens=200,
    )

    # Registra métricas para tornar GPT-3.5 mais rápido
    for _ in range(10):
        await selector._tracker.record_request(
            RequestMetric(
                model_id="openai-gpt-3.5-turbo",
                success=True,
                latency_ms=300.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.001,
            )
        )

    # Registra métricas para GPT-4 mais lento
    for _ in range(10):
        await selector._tracker.record_request(
            RequestMetric(
                model_id="openai-gpt-4-turbo",
                success=True,
                latency_ms=800.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )

    result = await selector.select_model(context, criteria=SelectionCriteria.FASTEST)

    assert result is not None
    # Local models podem ser mais rápidos, mas com stats suficientes, deve ser GPT-3.5
    assert result.model_id in ["openai-gpt-3.5-turbo", "local-llama2"]
    assert "latência" in result.selection_reason.lower()


@pytest.mark.asyncio
async def test_select_cheapest_model():
    """Testa seleção de modelo mais barato."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=1000,
        expected_output_tokens=500,
    )

    result = await selector.select_model(context, criteria=SelectionCriteria.CHEAPEST)

    # Local models são gratuitos
    assert result is not None
    assert result.provider == "local"
    assert result.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_select_highest_quality_model():
    """Testa seleção de modelo com maior qualidade."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.ANALYSIS,
        expected_input_tokens=500,
        expected_output_tokens=500,
    )

    result = await selector.select_model(context, criteria=SelectionCriteria.HIGHEST_QUALITY)

    assert result is not None
    # GPT-4 Turbo (0.95) ou Claude 3 Opus (0.98) deve ser selecionado
    assert result.model_id in ["openai-gpt-4-turbo", "anthropic-claude-3-opus"]
    # Verifica que é um modelo com alta qualidade
    model = selector._registry.get_model(result.model_id)
    assert model.capabilities.benchmark_quality_score >= 0.95


@pytest.mark.asyncio
async def test_select_balanced_model():
    """Testa seleção balanceada."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.CHAT,
        expected_input_tokens=200,
        expected_output_tokens=300,
    )

    result = await selector.select_model(context, criteria=SelectionCriteria.BALANCED)

    assert result is not None
    assert result.selection_reason == "Melhor balance performance/custo/qualidade"


@pytest.mark.asyncio
async def test_select_with_custom_weights():
    """Testa seleção com pesos customizados."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=100,
        expected_output_tokens=200,
    )

    weights = SelectionWeights(performance_weight=0.7, cost_weight=0.2, quality_weight=0.1)

    result = await selector.select_model(
        context, criteria=SelectionCriteria.CUSTOM, weights=weights
    )

    assert result is not None
    assert "Pesos customizados" in result.selection_reason


@pytest.mark.asyncio
async def test_filter_by_streaming_capability():
    """Testa filtro por capacidade de streaming."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.CHAT,
        expected_input_tokens=100,
        expected_output_tokens=200,
        requires_streaming=True,
    )

    result = await selector.select_model(context)

    # Todos os modelos padrão suportam streaming
    assert result is not None


@pytest.mark.asyncio
async def test_filter_by_function_calling():
    """Testa filtro por function calling."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TOOL_USE,
        expected_input_tokens=500,
        expected_output_tokens=300,
        requires_function_calling=True,
    )

    result = await selector.select_model(context)

    assert result is not None
    model = selector._registry.get_model(result.model_id)
    assert model.capabilities.supports_function_calling


@pytest.mark.asyncio
async def test_filter_by_vision():
    """Testa filtro por visão."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.ANALYSIS,
        expected_input_tokens=500,
        expected_output_tokens=300,
        requires_vision=True,
    )

    result = await selector.select_model(context)

    assert result is not None
    model = selector._registry.get_model(result.model_id)
    assert model.capabilities.supports_vision


@pytest.mark.asyncio
async def test_filter_by_context_size():
    """Testa filtro por tamanho de contexto."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.RAG,
        expected_input_tokens=50000,
        expected_output_tokens=5000,
    )

    result = await selector.select_model(context)

    assert result is not None
    model = selector._registry.get_model(result.model_id)
    total_tokens = 55000
    assert model.capabilities.max_context_tokens >= total_tokens


@pytest.mark.asyncio
async def test_filter_by_max_latency():
    """Testa filtro por latência máxima."""
    selector = get_selector()

    # Registra métricas de latência para vários modelos
    for _ in range(10):
        await selector._tracker.record_request(
            RequestMetric(
                model_id="openai-gpt-3.5-turbo",
                success=True,
                latency_ms=400.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.001,
            )
        )
        await selector._tracker.record_request(
            RequestMetric(
                model_id="openai-gpt-4-turbo",
                success=True,
                latency_ms=800.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )
        await selector._tracker.record_request(
            RequestMetric(
                model_id="anthropic-claude-3-haiku",
                success=True,
                latency_ms=300.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.001,
            )
        )

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=100,
        expected_output_tokens=200,
        max_latency_ms=500.0,
    )

    result = await selector.select_model(context)

    assert result is not None
    # O modelo seleccionado deve ter latência < 500ms
    assert result.performance_metrics["avg_latency_ms"] < 500.0


@pytest.mark.asyncio
async def test_filter_by_max_cost():
    """Testa filtro por custo máximo."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=1000,
        expected_output_tokens=500,
        max_cost_usd=0.01,
    )

    result = await selector.select_model(context)

    assert result is not None
    # O custo estimado deve ser <= 0.01
    assert result.estimated_cost_usd <= 0.01
    # Claude 3 Haiku é muito barato (input: 0.00025, output: 0.00125)
    # Custo para 1500 tokens: (1000 * 0.00025 + 500 * 0.00125) / 1000 = 0.000875


@pytest.mark.asyncio
async def test_filter_by_min_quality():
    """Testa filtro por qualidade mínima."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.ANALYSIS,
        expected_input_tokens=500,
        expected_output_tokens=500,
        min_quality_score=0.90,
    )

    result = await selector.select_model(context)

    assert result is not None
    model = selector._registry.get_model(result.model_id)
    assert model.capabilities.benchmark_quality_score >= 0.90


@pytest.mark.asyncio
async def test_exclude_models():
    """Testa exclusão de modelos da seleção."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=100,
        expected_output_tokens=200,
    )

    excluded = {"openai-gpt-3.5-turbo", "openai-gpt-4-turbo"}

    result = await selector.select_model(context, excluded_models=excluded)

    assert result is not None
    assert result.model_id not in excluded


@pytest.mark.asyncio
async def test_no_model_available():
    """Testa quando nenhum modelo está disponível."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.EMBEDDING,
        expected_input_tokens=100,
        expected_output_tokens=50,
    )

    result = await selector.select_model(context)

    # Nenhum modelo padrão suporta embedding
    assert result is None


@pytest.mark.asyncio
async def test_context_too_large_for_all_models():
    """Testa quando contexto é muito grande para todos os modelos."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.RAG,
        expected_input_tokens=500000,
        expected_output_tokens=10000,
    )

    result = await selector.select_model(context)

    # Nenhum modelo suporta 510k tokens
    assert result is None


@pytest.mark.asyncio
async def test_selection_result_structure():
    """Testa estrutura do resultado de seleção."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=100,
        expected_output_tokens=200,
    )

    result = await selector.select_model(context)

    assert isinstance(result, SelectionResult)
    assert result.model_id is not None
    assert result.provider is not None
    assert result.api_name is not None
    assert result.score >= 0
    assert result.selection_reason is not None
    assert result.timestamp is not None


@pytest.mark.asyncio
async def test_custom_weights_validation():
    """Testa validação de pesos customizados."""
    weights = SelectionWeights(performance_weight=0.5, cost_weight=0.3, quality_weight=0.2)
    weights.validate()

    # Soma incorreta deve falhar
    invalid_weights = SelectionWeights(performance_weight=0.5, cost_weight=0.3, quality_weight=0.3)

    with pytest.raises(ValueError):
        invalid_weights.validate()


@pytest.mark.asyncio
async def test_insufficient_stats_uses_registry():
    """Testa que stats insuficientes usam defaults do registry."""
    selector = get_selector()

    context = SelectionContext(
        task_type=TaskType.TEXT_GENERATION,
        expected_input_tokens=100,
        expected_output_tokens=200,
    )

    # Sem stats suficientes, deve usar qualidade do registry
    result = await selector.select_model(context, criteria=SelectionCriteria.HIGHEST_QUALITY)

    assert result is not None
    # Deve selecionar um modelo com alta qualidade no registry
    model = selector._registry.get_model(result.model_id)
    assert model.capabilities.benchmark_quality_score >= 0.95
