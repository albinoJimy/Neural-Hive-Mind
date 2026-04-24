"""
Testes de migração para neural_hive_llm em code-forge.

Verifica que o wrapper mantém compatibilidade com a API existente.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.llm_client import LLMClient, LLMProvider


@pytest.fixture
def mock_neural_hive_response():
    """Mock response de neural_hive_llm."""
    mock_response = MagicMock()
    mock_response.text = '```python\ndef hello():\n    """Say hello."""\n    return "Hello"\n```'
    mock_response.prompt_tokens = 100
    mock_response.completion_tokens = 50
    mock_response.total_tokens = 150
    return mock_response


@pytest.mark.asyncio
async def test_llm_client_initialization():
    """Testa que o cliente pode ser inicializado com diferentes providers."""
    # Testar com provider local
    client = LLMClient(provider=LLMProvider.LOCAL, model_name="llama2")
    assert client.provider == LLMProvider.LOCAL
    assert client.model_name == "llama2"

    # Testar com provider OpenAI
    client = LLMClient(
        provider=LLMProvider.OPENAI, api_key="sk-test", model_name="gpt-4"
    )
    assert client.provider == LLMProvider.OPENAI
    assert client.api_key == "sk-test"


@pytest.mark.asyncio
async def test_llm_client_start_stop():
    """Testa ciclo de vida do cliente."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.LOCAL)
        await client.start()

        # Verificar que neural_hive_llm foi inicializado
        mock_instance.start.assert_called_once()

        await client.stop()
        mock_instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_generate_code_basic(mock_neural_hive_response):
    """Testa geração básica de código."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.LOCAL)
        client._client = mock_instance  # Set internal client directly

        result = await client.generate_code(
            prompt="Create a hello world function",
            constraints={"language": "python"},
        )

        assert result is not None
        assert "code" in result
        assert "confidence_score" in result
        assert result["confidence_score"] > 0
        assert "def hello()" in result["code"]


@pytest.mark.asyncio
async def test_generate_code_with_constraints(mock_neural_hive_response):
    """Testa geração de código com constraints específicas."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.LOCAL)
        client._client = mock_instance

        constraints = {
            "language": "python",
            "framework": "fastapi",
            "patterns": ["repository", "dependency_injection"],
            "max_lines": 500,
        }

        result = await client.generate_code(
            prompt="Create a REST API",
            constraints=constraints,
            temperature=0.3,
        )

        assert result is not None
        # Verificar que system prompt foi construído corretamente
        mock_instance.generate.assert_called_once()
        call_kwargs = mock_instance.generate.call_args[1]
        assert call_kwargs["temperature"] == 0.3
        assert "fastapi" in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_generate_code_extracts_markdown_blocks():
    """Testa que markdown code blocks são extraídos corretamente."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_response = MagicMock()
        # Resposta com markdown code blocks
        mock_response.text = 'Aqui está o código:\n```python\ndef func():\n    pass\n```\nEspero que ajude!'
        mock_response.prompt_tokens = 50
        mock_response.completion_tokens = 20

        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.LOCAL)
        client._client = mock_instance

        result = await client.generate_code(
            prompt="Create a function", constraints={"language": "python"}
        )

        assert result is not None
        # Verificar que markdown foi removido
        assert "```" not in result["code"]
        assert "def func():" in result["code"]


@pytest.mark.asyncio
async def test_calculate_confidence():
    """Testa cálculo de confiança."""
    client = LLMClient(provider=LLMProvider.LOCAL)

    # Código com boas práticas
    good_code = '''"""Módulo exemplo."""
from typing import Optional

def process(data: str) -> Optional[str]:
    """Processa dados."""
    try:
        return data.upper()
    except ValueError as e:
        return None
'''

    confidence = await client.calculate_confidence(good_code, {"language": "python"})
    assert confidence > 0.7  # Deve ter alta confiança


@pytest.mark.asyncio
async def test_calculate_confidence_low_quality():
    """Testa confiança baixa para código de baixa qualidade."""
    client = LLMClient(provider=LLMProvider.LOCAL)

    # Código simples sem boas práticas
    simple_code = "x=1"

    confidence = await client.calculate_confidence(simple_code, {"language": "python"})
    assert confidence < 0.7  # Deve ter baixa confiança


@pytest.mark.asyncio
async def test_validate_code():
    """Testa validação básica de código."""
    client = LLMClient(provider=LLMProvider.LOCAL)

    # Código válido
    assert await client.validate_code("def hello(): pass", "python")

    # Código invazio
    assert not await client.validate_code("", "python")

    # Código muito curto
    assert not await client.validate_code("x", "python")


@pytest.mark.asyncio
async def test_generate_code_handles_errors():
    """Testa que erros são tratados graciosamente."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(side_effect=Exception("API Error"))
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.LOCAL)
        client._client = mock_instance

        result = await client.generate_code(
            prompt="Test", constraints={"language": "python"}
        )

        # Deve retornar None em caso de erro
        assert result is None


@pytest.mark.asyncio
async def test_generate_code_without_initialization():
    """Testa que geração sem inicialização retorna None."""
    client = LLMClient(provider=LLMProvider.LOCAL)
    # Não chamar start()

    result = await client.generate_code(
        prompt="Test", constraints={"language": "python"}
    )

    assert result is None


@pytest.mark.asyncio
async def test_openai_provider_conversion():
    """Testa que provider string é convertido corretamente."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.OPENAI, api_key="sk-test")
        await client.start()

        # Verificar que neural_hive_llm foi chamado com provider correto
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        # O enum deve ter sido convertido
        assert "provider" in call_kwargs


@pytest.mark.asyncio
async def test_anthropic_provider_conversion():
    """Testa que provider Anthropic é convertido corretamente."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.ANTHROPIC, api_key="sk-ant-test")
        await client.start()

        # Verificar que neural_hive_llm foi chamado
        mock_client_class.assert_called_once()


@pytest.mark.asyncio
async def test_generate_code_returns_token_counts(mock_neural_hive_response):
    """Testa que contagem de tokens é retornada."""
    with patch("src.clients.llm_client_wrapper.NeuralHiveLLMClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=mock_neural_hive_response)
        mock_client_class.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.LOCAL)
        client._client = mock_instance

        result = await client.generate_code(
            prompt="Test", constraints={"language": "python"}
        )

        assert result is not None
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
