"""
Configuração e fixtures para testes de neural_hive_llm.
"""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Cria event loop para testes assíncronos."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_openai_client() -> AsyncMock:
    """Mock para cliente OpenAI."""
    client = AsyncMock()

    # Mock response para generate
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Resposta gerada"
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 30
    mock_response.model = "gpt-3.5-turbo"
    mock_response.id = "test-id"

    client.chat.completions.create = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture
async def mock_anthropic_client() -> AsyncMock:
    """Mock para cliente Anthropic."""
    client = AsyncMock()

    # Mock response para generate
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Resposta gerada")]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 20
    mock_response.stop_reason = "end_turn"
    mock_response.id = "test-id"

    client.messages.create = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture
def mock_settings_env(monkeypatch) -> None:
    """Configura variáveis de ambiente para testes."""
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_MODEL", "llama2")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")
