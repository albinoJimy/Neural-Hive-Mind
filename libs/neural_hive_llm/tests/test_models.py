"""
Testes unitários para modelos Pydantic.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from neural_hive_llm.models import (
    LLMProvider,
    LLMModel,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)


class TestLLMProvider:
    """Testes para enum LLMProvider."""

    def test_provider_values(self) -> None:
        """Testa valores do enum."""
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.ANTHROPIC == "anthropic"
        assert LLMProvider.LOCAL == "local"


class TestLLMModel:
    """Testes para enum LLMModel."""

    def test_openai_models(self) -> None:
        """Testa modelos OpenAI."""
        assert LLMModel.GPT4 == "gpt-4"
        assert LLMModel.GPT4_TURBO == "gpt-4-turbo-preview"
        assert LLMModel.GPT35_TURBO == "gpt-3.5-turbo"

    def test_anthropic_models(self) -> None:
        """Testa modelos Anthropic."""
        assert LLMModel.CLAUDE_3_OPUS == "claude-3-opus-20240229"
        assert LLMModel.CLAUDE_3_SONNET == "claude-3-sonnet-20240229"


class TestLLMRequest:
    """Testes para modelo LLMRequest."""

    def test_minimal_request(self) -> None:
        """Testa criação de requisição mínima."""
        request = LLMRequest(prompt="Test prompt")
        assert request.prompt == "Test prompt"
        assert request.system_prompt is None
        assert request.temperature == 0.7

    def test_full_request(self) -> None:
        """Testa criação de requisição completa."""
        request = LLMRequest(
            prompt="Test prompt",
            system_prompt="You are a helpful assistant",
            temperature=0.5,
            max_tokens=1000,
            top_p=0.9,
        )
        assert request.prompt == "Test prompt"
        assert request.system_prompt == "You are a helpful assistant"
        assert request.temperature == 0.5
        assert request.max_tokens == 1000

    def test_empty_prompt_validation(self) -> None:
        """Testa validação de prompt vazio."""
        with pytest.raises(ValidationError):
            LLMRequest(prompt="")

    def test_whitespace_only_prompt_validation(self) -> None:
        """Testa validação de prompt com apenas espaços."""
        with pytest.raises(ValidationError):
            LLMRequest(prompt="   ")

    def test_prompt_trimming(self) -> None:
        """Testa que prompts são trimmados."""
        request = LLMRequest(prompt="  Test prompt  ")
        assert request.prompt == "Test prompt"

    def test_temperature_validation(self) -> None:
        """Testa validação de temperatura."""
        with pytest.raises(ValidationError):
            LLMRequest(prompt="Test", temperature=3.0)

        with pytest.raises(ValidationError):
            LLMRequest(prompt="Test", temperature=-0.1)

    def test_max_tokens_validation(self) -> None:
        """Testa validação de max_tokens."""
        with pytest.raises(ValidationError):
            LLMRequest(prompt="Test", max_tokens=0)


class TestLLMResponse:
    """Testes para modelo LLMResponse."""

    def test_response_creation(self) -> None:
        """Testa criação de resposta."""
        response = LLMResponse(
            text="Generated text",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            model="gpt-3.5-turbo",
            provider=LLMProvider.OPENAI,
            latency_ms=500.0,
        )

        assert response.text == "Generated text"
        assert response.total_tokens == 30
        assert response.provider == LLMProvider.OPENAI

    def test_tokens_per_second_calculation(self) -> None:
        """Testa cálculo de tokens por segundo."""
        response = LLMResponse(
            text="Generated text",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            model="gpt-3.5-turbo",
            provider=LLMProvider.OPENAI,
            latency_ms=1000.0,  # 1 segundo
        )

        assert response.tokens_per_second == 20.0

    def test_tokens_per_second_zero_latency(self) -> None:
        """Testa cálculo com latência zero."""
        response = LLMResponse(
            text="Generated text",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            model="gpt-3.5-turbo",
            provider=LLMProvider.OPENAI,
            latency_ms=0.0,
        )

        assert response.tokens_per_second == 0.0

    def test_default_values(self) -> None:
        """Testa valores padrão."""
        response = LLMResponse(
            text="Generated text",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            model="gpt-3.5-turbo",
            provider=LLMProvider.OPENAI,
            latency_ms=500.0,
        )

        assert response.estimated_cost_usd == 0.0
        assert response.finish_reason is None
        assert isinstance(response.timestamp, datetime)


class TestLLMStreamChunk:
    """Testes para modelo LLMStreamChunk."""

    def test_chunk_creation(self) -> None:
        """Testa criação de chunk."""
        chunk = LLMStreamChunk(delta="Hello")
        assert chunk.delta == "Hello"
        assert chunk.is_complete is False
        assert chunk.finish_reason is None

    def test_final_chunk(self) -> None:
        """Testa chunk final."""
        chunk = LLMStreamChunk(
            delta="", finish_reason="stop", is_complete=True
        )
        assert chunk.is_complete is True
        assert chunk.finish_reason == "stop"


class TestTokenUsage:
    """Testes para modelo TokenUsage."""

    def test_usage_creation(self) -> None:
        """Testa criação de uso de tokens."""
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30  # Calculado como property

    def test_usage_addition(self) -> None:
        """Testa soma de usos de tokens."""
        usage1 = TokenUsage(prompt_tokens=10, completion_tokens=20)
        usage2 = TokenUsage(prompt_tokens=5, completion_tokens=15)

        combined = usage1 + usage2
        assert combined.prompt_tokens == 15
        assert combined.completion_tokens == 35
        assert combined.total_tokens == 50  # Property calcula soma
