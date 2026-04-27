"""
Testes unitários para OpenAIProvider.
"""

from unittest.mock import patch

import pytest

from neural_hive_llm.exceptions import (
    LLMRateLimitError,
    LLMTimeoutError,
)
from neural_hive_llm.models import LLMProvider, LLMRequest
from neural_hive_llm.providers.openai_provider import OpenAIProvider


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    """Cria provider OpenAI para testes."""
    return OpenAIProvider(
        api_key="sk-test-key",
        model="gpt-3.5-turbo",
    )


@pytest.mark.asyncio
class TestOpenAIProvider:
    """Testes para OpenAIProvider."""

    async def test_initialization_without_sdk(self, openai_provider) -> None:
        """Testa erro ao inicializar sem SDK instalado."""
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError) as exc_info:
                await openai_provider.initialize()

            assert "OpenAI SDK não instalado" in str(exc_info.value)

    async def test_build_messages_without_system(self, openai_provider) -> None:
        """Testa construção de messages sem prompt de sistema."""
        request = LLMRequest(prompt="Hello")
        messages = openai_provider._build_messages(request)

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    async def test_build_messages_with_system(self, openai_provider) -> None:
        """Testa construção de messages com prompt de sistema."""
        request = LLMRequest(prompt="Hello", system_prompt="You are helpful")
        messages = openai_provider._build_messages(request)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"

    def test_calculate_cost_gpt35(self, openai_provider) -> None:
        """Testa cálculo de custo para GPT-3.5."""
        cost = openai_provider._calculate_cost(prompt_tokens=1000, completion_tokens=500)

        # GPT-3.5: $0.50/M input, $1.50/M output
        assert cost == (1000 / 1_000_000) * 0.5 + (500 / 1_000_000) * 1.5

    def test_calculate_cost_gpt4(self, openai_provider) -> None:
        """Testa cálculo de custo para GPT-4."""
        openai_provider.model = "gpt-4"
        cost = openai_provider._calculate_cost(prompt_tokens=1000, completion_tokens=500)

        # GPT-4: $30/M input, $60/M output
        assert cost == (1000 / 1_000_000) * 30.0 + (500 / 1_000_000) * 60.0

    def test_calculate_cost_unknown_model(self, openai_provider) -> None:
        """Testa cálculo de custo para modelo desconhecido."""
        openai_provider.model = "unknown-model"
        cost = openai_provider._calculate_cost(prompt_tokens=1000, completion_tokens=500)

        # Modelo desconhecido = grátis
        assert cost == 0.0

    async def test_generate_with_mock(self, openai_provider, mock_openai_client) -> None:
        """Testa geração com cliente mockado."""
        openai_provider._client = mock_openai_client
        openai_provider._is_initialized = True

        request = LLMRequest(prompt="Test prompt")
        response = await openai_provider.generate(request)

        assert response.text == "Resposta gerada"
        assert response.total_tokens == 30
        assert response.provider == LLMProvider.OPENAI

    async def test_map_rate_limit_error(self, openai_provider) -> None:
        """Testa mapeamento de erro de rate limit."""
        from unittest.mock import MagicMock

        from openai import RateLimitError

        # Criar mock response e body necessários para o OpenAI SDK
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_body = {"error": {"message": "Rate limit exceeded"}}

        original_error = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body=mock_body,
        )
        mapped = openai_provider._map_exception(original_error)

        assert isinstance(mapped, LLMRateLimitError)
        assert mapped.provider == "openai"

    async def test_map_timeout_error(self, openai_provider) -> None:
        """Testa mapeamento de erro de timeout."""
        from unittest.mock import MagicMock

        # Criar mock request necessário para o OpenAI SDK
        mock_request = MagicMock()

        # APITimeoutError tem assinatura diferente, vamos usar um genérico
        # Exception para testar o mapeamento de texto
        original_error = Exception("Request timeout")
        mapped = openai_provider._map_exception(original_error)

        # Como "timeout" está na mensagem, deve mapear para LLMTimeoutError
        assert isinstance(mapped, LLMTimeoutError)
        assert mapped.provider == "openai"

    def test_repr(self, openai_provider) -> None:
        """Testa representação string."""
        assert repr(openai_provider) == "OpenAIProvider(model=gpt-3.5-turbo)"
