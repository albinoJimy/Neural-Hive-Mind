"""
Testes de migração para neural_hive_llm em architect-agent.

Verifica que o wrapper mantém compatibilidade com a API existente.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.planners.llm_client import LLMClient


@pytest.fixture
def mock_settings():
    """Mock settings para LLM."""
    settings = MagicMock()
    settings.llm.provider = "openai"
    settings.llm.api_key = "sk-test"
    settings.llm.model = "gpt-4"
    settings.llm.timeout_seconds = 60.0
    settings.llm.max_tokens = 2048
    return settings


@pytest.fixture
def mock_neural_hive_response():
    """Mock response de neural_hive_llm."""
    mock_response = MagicMock()
    mock_response.text = '{"architecture_type": "microservices"}'
    return mock_response


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_llm_client_initialization(mock_get_settings, mock_settings):
    """Testa que o cliente pode ser inicializado."""
    mock_get_settings.return_value = mock_settings

    client = LLMClient()
    assert client.provider == "openai"
    assert client.api_key == "sk-test"
    assert client.model == "gpt-4"


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_generate_basic(mock_get_settings, mock_settings, mock_neural_hive_response):
    """Testa geração básica de resposta."""
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        result = await client.generate("Create a microservice")

        assert result == '{"architecture_type": "microservices"}'
        mock_instance.generate.assert_called_once()


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_generate_with_system_prompt(
    mock_get_settings, mock_settings, mock_neural_hive_response
):
    """Testa geração com system prompt."""
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        system_prompt = "You are an expert architect."
        await client.generate("Create a microservice", system_prompt)

        # Verificar que system prompt foi passado
        call_kwargs = mock_instance.generate.call_args[1]
        assert call_kwargs["system_prompt"] == system_prompt


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_generate_without_api_key_fallback(mock_get_settings):
    """Testa fallback quando API key não está configurada."""
    # Configurar sem API key
    mock_settings_no_key = MagicMock()
    mock_settings_no_key.llm.provider = None
    mock_settings_no_key.llm.api_key = None
    mock_get_settings.return_value = mock_settings_no_key

    client = LLMClient()
    result = await client.generate("Create a microservice")

    # Deve retornar resposta padrão
    assert result is not None
    assert isinstance(result, str)
    # Verificar que é JSON válido
    parsed = json.loads(result)
    assert "architecture_type" in parsed


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_get_default_response_microservice(mock_get_settings):
    """Testa resposta padrão para microservice."""
    mock_settings_no_key = MagicMock()
    mock_settings_no_key.llm.provider = None
    mock_settings_no_key.llm.api_key = None
    mock_get_settings.return_value = mock_settings_no_key

    client = LLMClient()
    result = client.get_default_response("Create a scalable microservice")

    parsed = json.loads(result)
    assert parsed["architecture_type"] == "microservices"


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_get_default_response_monolith(mock_get_settings):
    """Testa resposta padrão (monolith) para prompts sem keywords."""
    mock_settings_no_key = MagicMock()
    mock_settings_no_key.llm.provider = None
    mock_settings_no_key.llm.api_key = None
    mock_get_settings.return_value = mock_settings_no_key

    client = LLMClient()
    result = client.get_default_response("Create a simple application")

    parsed = json.loads(result)
    assert parsed["architecture_type"] == "monolith"


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_generate_handles_errors(mock_get_settings, mock_settings):
    """Testa que erros são tratados com fallback."""
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(side_effect=Exception("API Error"))
        mock_instance.start = AsyncMock()
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        result = await client.generate("Test")

        # Deve retornar resposta padrão em caso de erro
        assert result is not None
        assert isinstance(result, str)


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_openai_provider_conversion(
    mock_get_settings, mock_settings, mock_neural_hive_response
):
    """Testa que provider OpenAI é convertido corretamente."""
    mock_settings.llm.provider = "openai"
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        await client.generate("Test")

        # Verificar que client foi criado
        mock_client_class.assert_called_once()


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_anthropic_provider_conversion(
    mock_get_settings, mock_settings, mock_neural_hive_response
):
    """Testa que provider Anthropic é convertido corretamente."""
    mock_settings.llm.provider = "anthropic"
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        await client.generate("Test")

        # Verificar que client foi criado
        mock_client_class.assert_called_once()


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_lazy_initialization(mock_get_settings, mock_settings):
    """Testa que o cliente é inicializado de forma lazy."""
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        # Cliente não deve ser inicializado antes do primeiro uso
        assert not mock_instance.start.called

        # Após usar, deve ser inicializado
        with patch.object(client, "_get_default_response", return_value="{}"):
            # Simular erro para testar fallback
            mock_instance.generate = AsyncMock(side_effect=Exception("Error"))
            await client.generate("Test")


@pytest.mark.asyncio
@patch("src.planners.llm_client_wrapper.get_settings")
async def test_client_reuse(mock_get_settings, mock_settings, mock_neural_hive_response):
    """Testa que o cliente é reutilizado entre chamadas."""
    mock_get_settings.return_value = mock_settings

    with patch("src.planners.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient()
        await client.generate("First call")
        await client.generate("Second call")

        # NeuralHiveLLMClient deve ser criado apenas uma vez
        assert mock_client_class.call_count == 1
        # generate deve ser chamado duas vezes
        assert mock_instance.generate.call_count == 2
