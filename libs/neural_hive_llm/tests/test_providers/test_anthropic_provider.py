"""
Testes unitários para AnthropicProvider.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from neural_hive_llm.providers.anthropic_provider import AnthropicProvider
from neural_hive_llm.models import LLMRequest, LLMProvider
from neural_hive_llm.exceptions import (
    LLMConfigurationError,
    LLMTimeoutError,
    LLMRateLimitError,
)


@pytest.fixture
def anthropic_provider() -> AnthropicProvider:
    """Cria provider Anthropic para testes."""
    return AnthropicProvider(
        api_key="sk-ant-test-key",
        model="claude-3-sonnet-20240229",
    )


@pytest.mark.asyncio
class TestAnthropicProvider:
    """Testes para AnthropicProvider."""

    async def test_initialization_without_sdk(self, anthropic_provider) -> None:
        """Testa erro ao inicializar sem SDK instalado."""
        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError) as exc_info:
                await anthropic_provider.initialize()

            assert "Anthropic SDK não instalado" in str(exc_info.value)

    async def test_extract_text_simple_response(
        self, anthropic_provider
    ) -> None:
        """Testa extração de texto de resposta simples."""
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "Generated text"
        mock_response.content = [mock_block]

        text = anthropic_provider._extract_text_from_response(mock_response)
        assert text == "Generated text"

    async def test_extract_text_multiple_blocks(
        self, anthropic_provider
    ) -> None:
        """Testa extração de texto de múltiplos blocos."""
        mock_response = MagicMock()
        mock_block1 = MagicMock()
        mock_block1.text = "Hello "
        mock_block2 = MagicMock()
        mock_block2.text = "world"
        mock_response.content = [mock_block1, mock_block2]

        text = anthropic_provider._extract_text_from_response(mock_response)
        assert text == "Hello world"

    def test_calculate_cost_opus(self, anthropic_provider) -> None:
        """Testa cálculo de custo para Claude Opus."""
        anthropic_provider.model = "claude-3-opus-20240229"
        cost = anthropic_provider._calculate_cost(
            input_tokens=1000,
            output_tokens=500
        )

        # Opus: $15/M input, $75/M output
        assert cost == (1000 / 1_000_000) * 15.0 + (500 / 1_000_000) * 75.0

    def test_calculate_cost_sonnet(self, anthropic_provider) -> None:
        """Testa cálculo de custo para Claude Sonnet."""
        cost = anthropic_provider._calculate_cost(
            input_tokens=1000,
            output_tokens=500
        )

        # Sonnet: $3/M input, $15/M output
        assert cost == (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0

    def test_calculate_cost_haiku(self, anthropic_provider) -> None:
        """Testa cálculo de custo para Claude Haiku."""
        anthropic_provider.model = "claude-3-haiku-20240307"
        cost = anthropic_provider._calculate_cost(
            input_tokens=1000,
            output_tokens=500
        )

        # Haiku: $0.25/M input, $1.25/M output
        expected = (1000 / 1_000_000) * 0.25 + (500 / 1_000_000) * 1.25
        assert abs(cost - expected) < 0.0001

    async def test_generate_with_mock(
        self, anthropic_provider, mock_anthropic_client
    ) -> None:
        """Testa geração com cliente mockado."""
        anthropic_provider._client = mock_anthropic_client
        anthropic_provider._is_initialized = True

        request = LLMRequest(prompt="Test prompt")
        response = await anthropic_provider.generate(request)

        assert response.text == "Resposta gerada"
        assert response.total_tokens == 30
        assert response.provider == LLMProvider.ANTHROPIC

    def test_repr(self, anthropic_provider) -> None:
        """Testa representação string."""
        assert (
            repr(anthropic_provider)
            == "AnthropicProvider(model=claude-3-sonnet-20240229)"
        )
