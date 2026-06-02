"""Fixtures compartilhadas para testes de neural_hive_llm."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from neural_hive_llm import LLMClient, LLMProvider


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Cria event loop para testes assíncronos."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def llm_client() -> AsyncGenerator[LLMClient, None]:
    """Cliente LLM para testes (provedor local sem API key)."""
    client = LLMClient(
        provider=LLMProvider.LOCAL,
        model="llama3",
        endpoint_url="http://localhost:11434/api",
    )
    yield client
    await client.stop()


@pytest.fixture
def mock_openai_response() -> dict[str, Any]:
    """Resposta mockada da API OpenAI."""
    return {
        "choices": [
            {
                "message": {"content": "Texto gerado mockado", "role": "assistant"},
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "model": "gpt-4o",
        "id": "chatcmpl-mock",
    }


@pytest.fixture
def mock_anthropic_response() -> dict[str, Any]:
    """Resposta mockada da API Anthropic."""
    return {
        "content": [{"text": "Texto gerado mockado", "type": "text"}],
        "stop_reason": "end_turn",
        "model": "claude-3-5-sonnet-20241022",
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "id": "msg-mock",
    }


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """Cliente OpenAI mockado."""
    mock = MagicMock()
    mock.chat = MagicMock()
    mock.chat.completions = MagicMock()

    # Mock create method
    create_mock = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(content="Texto gerado mockado"),
            finish_reason="stop",
        )
    ]
    mock_response.usage = MagicMock(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
    )
    create_mock.return_value = mock_response
    mock.chat.completions.create = create_mock

    return mock


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Cliente Anthropic mockado."""
    mock = MagicMock()
    mock.messages = MagicMock()

    create_mock = AsyncMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Texto gerado mockado")]
    mock_message.stop_reason = "end_turn"
    mock_message.usage = MagicMock(
        input_tokens=10,
        output_tokens=20,
    )
    create_mock.return_value = mock_message
    mock.messages.create = create_mock

    return mock


@pytest.fixture
def sample_prompts() -> list[str]:
    """Prompts de exemplo para testes."""
    return [
        "O que é microserviços?",
        "Explique Kubernetes",
        "O que é serverless?",
    ]
