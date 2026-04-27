"""
Unit tests para Model Registry.
"""

import pytest

from neural_hive_llm.registry import (
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    ModelRegistry,
    TaskType,
    get_registry,
    reset_registry,
)


@pytest.fixture(autouse=True)
def reset_registry_before_each():
    """Reseta registry antes de cada teste."""
    reset_registry()
    yield
    reset_registry()


def test_registry_initialization():
    """Testa inicialização do registry com modelos padrão."""
    registry = get_registry()

    all_models = registry.list_models()
    assert len(all_models) >= 6

    # Verifica OpenAI models
    openai_models = registry.list_models(provider="openai")
    assert len(openai_models) >= 2

    # Verifica Anthropic models
    anthropic_models = registry.list_models(provider="anthropic")
    assert len(anthropic_models) >= 3

    # Verifica Local models
    local_models = registry.list_models(provider="local")
    assert len(local_models) >= 2


def test_register_model():
    """Testa registro de novo modelo."""
    registry = get_registry()

    new_model = ModelMetadata(
        model_id="test-model",
        provider="test",
        display_name="Test Model",
        api_name="test-model-v1",
        capabilities=ModelCapabilities(
            max_context_tokens=4096,
            supports_streaming=True,
            supports_function_calling=False,
            benchmark_quality_score=0.8,
        ),
        pricing=ModelPricing(
            input_price_per_1k_usd=0.001, output_price_per_1k_usd=0.002
        ),
        supported_tasks=[TaskType.TEXT_GENERATION],
    )

    registry.register_model(new_model)

    retrieved = registry.get_model("test-model")
    assert retrieved is not None
    assert retrieved.model_id == "test-model"
    assert retrieved.provider == "test"


def test_list_models_with_filters():
    """Testa listagem de modelos com filtros."""
    registry = get_registry()

    # Filtro por provider
    openai_models = registry.list_models(provider="openai")
    assert all(m.provider == "openai" for m in openai_models)

    # Filtro por tarefa
    code_models = registry.list_models(task=TaskType.CODE_GENERATION)
    assert all(TaskType.CODE_GENERATION in m.supported_tasks for m in code_models)

    # Filtro disponíveis
    available = registry.list_models(available_only=True)
    assert all(m.is_available for m in available)


def test_get_models_for_task():
    """Testa obtenção de modelos por tarefa."""
    registry = get_registry()

    # Code generation
    code_models = registry.get_models_for_task(TaskType.CODE_GENERATION)
    assert len(code_models) >= 2

    # Embedding
    embedding_models = registry.get_models_for_task(TaskType.EMBEDDING)
    # Provavelmente vazio pois nenhum modelo default suporta embedding

    # RAG
    rag_models = registry.get_models_for_task(TaskType.RAG)
    assert len(rag_models) >= 2


def test_update_model_availability():
    """Testa atualização de disponibilidade de modelo."""
    registry = get_registry()

    # Torna modelo indisponível
    registry.update_model_availability("openai-gpt-4-turbo", False)

    model = registry.get_model("openai-gpt-4-turbo")
    assert model is not None
    assert not model.is_available

    # Verifica que não aparece em lista de disponíveis
    available = registry.list_models(available_only=True)
    assert "openai-gpt-4-turbo" not in [m.model_id for m in available]

    # Restaura disponibilidade
    registry.update_model_availability("openai-gpt-4-turbo", True)

    model = registry.get_model("openai-gpt-4-turbo")
    assert model is not None
    assert model.is_available


def test_model_capabilities():
    """Testa capacidades de modelo."""
    registry = get_registry()

    gpt4 = registry.get_model("openai-gpt-4-turbo")
    assert gpt4 is not None

    assert gpt4.capabilities.max_context_tokens == 128000
    assert gpt4.capabilities.supports_streaming
    assert gpt4.capabilities.supports_function_calling
    assert gpt4.capabilities.supports_vision
    assert gpt4.capabilities.benchmark_quality_score == 0.95


def test_model_pricing():
    """Testa preços de modelo."""
    registry = get_registry()

    gpt4 = registry.get_model("openai-gpt-4-turbo")
    assert gpt4 is not None

    assert gpt4.pricing.input_price_per_1k_usd == 0.01
    assert gpt4.pricing.output_price_per_1k_usd == 0.03

    gpt35 = registry.get_model("openai-gpt-3.5-turbo")
    assert gpt35 is not None

    assert gpt35.pricing.input_price_per_1k_usd == 0.0005
    assert gpt35.pricing.output_price_per_1k_usd == 0.0015


def test_anthropic_models():
    """Testa modelos Anthropic."""
    registry = get_registry()

    claude_opus = registry.get_model("anthropic-claude-3-opus")
    assert claude_opus is not None

    assert claude_opus.capabilities.max_context_tokens == 200000
    assert claude_opus.capabilities.benchmark_quality_score == 0.98

    claude_haiku = registry.get_model("anthropic-claude-3-haiku")
    assert claude_haiku is not None

    assert claude_haiku.pricing.input_price_per_1k_usd == 0.00025
    assert claude_haiku.capabilities.benchmark_quality_score == 0.82


def test_local_models():
    """Testa modelos locais."""
    registry = get_registry()

    llama2 = registry.get_model("local-llama2")
    assert llama2 is not None

    assert llama2.pricing.input_price_per_1k_usd == 0.0
    assert llama2.pricing.output_price_per_1k_usd == 0.0

    mistral = registry.get_model("local-mistral")
    assert mistral is not None

    assert mistral.capabilities.benchmark_quality_score == 0.78
