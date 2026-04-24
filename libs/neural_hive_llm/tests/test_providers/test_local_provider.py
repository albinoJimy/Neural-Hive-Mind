"""
Testes unitários para LocalProvider.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from neural_hive_llm.providers.local_provider import LocalProvider
from neural_hive_llm.models import LLMRequest, LLMProvider


@pytest.fixture
def local_provider() -> LocalProvider:
    """Cria provider Local para testes."""
    return LocalProvider(
        base_url="http://localhost:11434",
        model="llama2",
    )


@pytest.mark.asyncio
class TestLocalProvider:
    """Testes para LocalProvider."""

    async def test_initialization(self, local_provider) -> None:
        """Testa inicialização do cliente HTTP."""
        await local_provider.initialize()
        assert local_provider._client is not None
        assert local_provider._is_initialized is True

        await local_provider.shutdown()
        assert local_provider._client is None

    def test_estimate_tokens(self, local_provider) -> None:
        """Testa estimativa de tokens."""
        # Texto curto
        tokens = local_provider._estimate_tokens("Hello")
        assert tokens >= 1

        # Texto mais longo (aprox 100 caracteres = 25 tokens)
        tokens = local_provider._estimate_tokens("a" * 100)
        assert tokens == 25

    def test_map_rate_limit_error(self, local_provider) -> None:
        """Testa mapeamento de erro 429."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"

        error = httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=mock_response)
        mapped = local_provider._map_exception(error)

        assert mapped.__class__.__name__ == "LLMRateLimitError"
        assert mapped.provider == "local"

    def test_map_invalid_request_error(self, local_provider) -> None:
        """Testa mapeamento de erro 400."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request"

        error = httpx.HTTPStatusError("Invalid", request=MagicMock(), response=mock_response)
        mapped = local_provider._map_exception(error)

        assert mapped.__class__.__name__ == "LLMInvalidRequestError"
        assert mapped.provider == "local"

    def test_map_server_error(self, local_provider) -> None:
        """Testa mapeamento de erro 500."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        mapped = local_provider._map_exception(error)

        assert mapped.__class__.__name__ == "LLMProviderError"
        assert mapped.provider == "local"

    async def test_healthcheck_success(self, local_provider) -> None:
        """Testa healthcheck com resposta positiva."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        local_provider._client = mock_client

        result = await local_provider.healthcheck()
        assert result is True

    async def test_healthcheck_failure(self, local_provider) -> None:
        """Testa healthcheck com falha."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection error"))
        local_provider._client = mock_client

        result = await local_provider.healthcheck()
        assert result is False

    async def test_generate_with_mock(self, local_provider) -> None:
        """Testa geração com cliente HTTP mockado."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Generated response",
            "prompt_eval_count": 10,
            "eval_count": 20,
            "done_reason": "stop",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        local_provider._client = mock_client
        local_provider._is_initialized = True

        request = LLMRequest(prompt="Test prompt")
        response = await local_provider.generate(request)

        assert response.text == "Generated response"
        assert response.total_tokens == 30
        assert response.provider == LLMProvider.LOCAL
        assert response.estimated_cost_usd == 0.0

    def test_repr(self, local_provider) -> None:
        """Testa representação string."""
        assert repr(local_provider) == "LocalProvider(model=llama2)"
