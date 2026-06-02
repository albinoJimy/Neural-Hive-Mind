"""Testes unitários para LLMClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_llm import (
    LLMClient,
    LLMProvider,
    LLMTimeoutError,
)
from neural_hive_llm.models import LLMResponse


@pytest.mark.asyncio
class TestLLMClient:
    """Testes unitários para LLMClient."""

    async def test_init_local_provider(self):
        """Testa inicialização com provedor local."""
        client = LLMClient(
            provider=LLMProvider.LOCAL,
            model="llama3",
        )
        assert client.provider == LLMProvider.LOCAL
        assert client.model == "llama3"
        assert client.api_key is None

    async def test_init_openai_provider_requires_api_key(self):
        """Testa que provedor OpenAI requer API key."""
        with pytest.raises(Exception) as exc_info:
            LLMClient(
                provider=LLMProvider.OPENAI,
                api_key=None,
            )
        assert "api_key" in str(exc_info.value).lower()

    async def test_init_with_settings_override(self, llm_client):
        """Testa inicialização com override de configurações."""
        settings = llm_client.settings
        assert settings is not None

    async def test_start_and_stop(self, llm_client):
        """Testa métodos start e stop."""
        await llm_client.start()
        assert llm_client._started is True
        await llm_client.stop()
        assert llm_client._started is False

    async def test_generate_local_mock(self, llm_client):
        """Testa geração com provedor local (mockado)."""
        # Mockar HTTP client antes do start
        with patch("httpx.AsyncClient") as mock_http_client_cls:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "Texto de teste"}
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_http_client_cls.return_value = mock_client

            await llm_client.start()

            response = await llm_client.generate(
                prompt="Teste",
                system_prompt="Você é um assistente",
                temperature=0.7,
            )

            assert isinstance(response, LLMResponse)
            assert response.provider == LLMProvider.LOCAL
            assert response.text == "Texto de teste"

    async def test_circuit_breaker_initialization(self, llm_client):
        """Testa que circuit breaker é inicializado quando habilitado."""
        if llm_client.circuit_breaker:
            assert llm_client.circuit_breaker.provider == llm_client.provider.value

    async def test_token_counter_initialization(self, llm_client):
        """Testa que token counter é inicializado."""
        assert llm_client.token_counter is not None

    async def test_repr(self, llm_client):
        """Testa representação string do cliente."""
        repr_str = repr(llm_client)
        assert "LLMClient" in repr_str
        assert llm_client.provider.value in repr_str
        assert llm_client.model in repr_str


@pytest.mark.asyncio
class TestLLMClientRetry:
    """Testes de lógica de retry."""

    async def test_retry_on_rate_limit(self):
        """Testa retry em caso de rate limit."""
        client = LLMClient(
            provider=LLMProvider.LOCAL,
            model="llama3",
            settings=None,  # Usará padrões
        )

        # Sobrescrever retry policy para testar
        client.retry_policy.max_retries = 1

        with patch.object(client, "_execute_generate", new=AsyncMock()) as mock_generate:
            # Primeira chamada succeed (sem retry necessário neste teste)
            mock_generate.return_value = LLMResponse(
                text="Sucesso",
                model="llama3",
                provider=LLMProvider.LOCAL,
            )

            await client.start()

            response = await client.generate(prompt="Teste")
            assert response.text == "Sucesso"
            assert mock_generate.call_count >= 1

    async def test_retry_exhausted(self):
        """Testa erro quando retries esgotados."""
        client = LLMClient(provider=LLMProvider.LOCAL, model="llama3")

        with patch.object(client, "_execute_generate", new=AsyncMock()) as mock_generate:
            # Todas as chamadas falham
            mock_generate.side_effect = LLMTimeoutError("Timeout", provider="local")

            await client.start()

            with pytest.raises(LLMTimeoutError):
                await client.generate(prompt="Teste")


@pytest.mark.asyncio
class TestLLMClientObservability:
    """Testes de observabilidade."""

    async def test_tracer_initialization(self, llm_client):
        """Testa que tracer é inicializado quando habilitado."""
        if llm_client.settings.enable_tracing:
            assert llm_client.tracer is not None

    async def test_token_counter_records_usage(self, llm_client):
        """Testa que token counter registra uso."""
        counter = llm_client.token_counter

        # Registrar uso
        result = counter.record_usage(
            model="gpt-4o",
            input_tokens=100,
            output_tokens=200,
        )

        assert result["total_tokens"] == 300
        assert result["provider"] == "openai"

    async def test_token_counter_calculates_cost(self, llm_client):
        """Testa cálculo de custo."""
        counter = llm_client.token_counter

        cost_usd, provider = counter.calculate_cost(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )

        assert provider is not None
        assert cost_usd > 0
