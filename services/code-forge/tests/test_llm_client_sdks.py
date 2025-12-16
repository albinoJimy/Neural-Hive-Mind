"""Testes unitários para LLM Client com SDKs oficiais."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.llm_client import LLMClient, LLMProvider


@pytest.fixture
def mock_openai_response():
    """Mock de resposta OpenAI."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "def hello():\n    return 'Hello, World!'"
    response.usage.prompt_tokens = 50
    response.usage.completion_tokens = 20
    return response


@pytest.fixture
def mock_anthropic_response():
    """Mock de resposta Anthropic."""
    response = MagicMock()
    response.content = [MagicMock()]
    response.content[0].text = "def hello():\n    return 'Hello, World!'"
    response.usage.input_tokens = 50
    response.usage.output_tokens = 20
    return response


@pytest.mark.asyncio
async def test_openai_sdk_call_success(mock_openai_response):
    """Testar chamada OpenAI SDK com sucesso."""
    with patch('src.clients.llm_client.AsyncOpenAI') as MockOpenAI:
        # Setup mock
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
        MockOpenAI.return_value = mock_client

        # Criar LLMClient
        llm_client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key="sk-test-key",
            model_name="gpt-4"
        )
        await llm_client.start()

        # Executar
        result = await llm_client.generate_code(
            prompt="Create a hello world function",
            constraints={"language": "python"}
        )

        # Validações
        assert result is not None
        assert "code" in result
        assert "def hello()" in result["code"]
        assert result["prompt_tokens"] == 50
        assert result["completion_tokens"] == 20

        await llm_client.stop()


@pytest.mark.asyncio
async def test_anthropic_sdk_call_success(mock_anthropic_response):
    """Testar chamada Anthropic SDK com sucesso."""
    with patch('src.clients.llm_client.AsyncAnthropic') as MockAnthropic:
        # Setup mock
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)
        MockAnthropic.return_value = mock_client

        # Criar LLMClient
        llm_client = LLMClient(
            provider=LLMProvider.ANTHROPIC,
            api_key="sk-ant-test-key",
            model_name="claude-3-opus-20240229"
        )
        await llm_client.start()

        # Executar
        result = await llm_client.generate_code(
            prompt="Create a hello world function",
            constraints={"language": "python"}
        )

        # Validações
        assert result is not None
        assert "code" in result
        assert "def hello()" in result["code"]
        assert result["prompt_tokens"] == 50
        assert result["completion_tokens"] == 20

        await llm_client.stop()


@pytest.mark.asyncio
async def test_openai_rate_limit_retry():
    """Testar retry em rate limit OpenAI."""
    with patch('src.clients.llm_client.AsyncOpenAI') as MockOpenAI:
        from openai import RateLimitError

        # Setup mock: falha 2x, sucesso na 3ª
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                RateLimitError("Rate limit exceeded"),
                RateLimitError("Rate limit exceeded"),
                MagicMock(
                    choices=[MagicMock(message=MagicMock(content="Success"))],
                    usage=MagicMock(prompt_tokens=10, completion_tokens=5)
                )
            ]
        )
        MockOpenAI.return_value = mock_client

        llm_client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key="sk-test-key",
            model_name="gpt-4"
        )
        await llm_client.start()

        # Executar (deve ter sucesso após retries)
        result = await llm_client.generate_code(
            prompt="Test",
            constraints={"language": "python"}
        )

        assert result is not None
        assert result["code"] == "Success"

        # Verificar que foi chamado 3 vezes
        assert mock_client.chat.completions.create.call_count == 3

        await llm_client.stop()


@pytest.mark.asyncio
async def test_missing_api_key():
    """Testar comportamento sem API key."""
    llm_client = LLMClient(
        provider=LLMProvider.OPENAI,
        api_key=None,  # Sem API key
        model_name="gpt-4"
    )
    await llm_client.start()

    result = await llm_client.generate_code(
        prompt="Test",
        constraints={"language": "python"}
    )

    # Deve retornar None
    assert result is None

    await llm_client.stop()


@pytest.mark.asyncio
async def test_streaming_mode():
    """Testar modo streaming (OpenAI)."""
    with patch('src.clients.llm_client.AsyncOpenAI') as MockOpenAI:
        # Setup mock streaming
        async def mock_stream():
            chunks = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="def "))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content="hello():"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content="\n    pass"))])
            ]
            for chunk in chunks:
                yield chunk

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
        MockOpenAI.return_value = mock_client

        llm_client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key="sk-test-key",
            model_name="gpt-4"
        )
        await llm_client.start()

        result = await llm_client.generate_code(
            prompt="Test",
            constraints={"language": "python"},
            stream=True
        )

        assert result is not None
        assert "def hello():" in result["code"]

        await llm_client.stop()
