"""
Testes unitários para LLMClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_llm.client import LLMClient, create_client
from neural_hive_llm.exceptions import LLMConfigurationError, LLMError
from neural_hive_llm.models import LLMProvider, LLMRequest, LLMResponse


@pytest.fixture
def mock_provider() -> MagicMock:
    """Mock para provider."""
    provider = MagicMock()
    provider.initialize = AsyncMock()
    provider.shutdown = AsyncMock()
    provider.healthcheck = AsyncMock(return_value=True)
    provider.generate = AsyncMock(
        return_value=LLMResponse(
            text="Response",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model="test",
            provider=LLMProvider.LOCAL,
            latency_ms=100,
        )
    )
    provider.generate_stream = AsyncMock()
    provider.generate_stream.__aiter__ = AsyncMock(return_value=iter([]))
    return provider


@pytest.mark.asyncio
class TestLLMClient:
    """Testes para LLMClient."""

    async def test_create_local_client(self) -> None:
        """Testa criação de cliente local."""
        client = LLMClient(provider=LLMProvider.LOCAL, model="llama2")
        assert client.provider == LLMProvider.LOCAL
        assert client.model == "llama2"
        assert client._is_started is False

    async def test_create_openai_client(self) -> None:
        """Testa criação de cliente OpenAI."""
        client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key="sk-test",
            model="gpt-4",
        )
        assert client.provider == LLMProvider.OPENAI
        assert client.api_key == "sk-test"

    async def test_create_with_settings(self) -> None:
        """Testa criação com settings."""
        from neural_hive_llm.config import LLMSettings

        settings = LLMSettings(
            provider=LLMProvider.LOCAL,
            model="test-model",
        )

        client = LLMClient(settings=settings)
        assert client.provider == LLMProvider.LOCAL
        assert client.settings == settings

    async def test_start_and_stop(self, monkeypatch) -> None:
        """Testa ciclo de vida start/stop."""
        client = LLMClient(provider=LLMProvider.LOCAL)

        # Mock do _create_provider
        mock_provider_instance = MagicMock()
        mock_provider_instance.initialize = AsyncMock()
        mock_provider_instance.shutdown = AsyncMock()

        with patch.object(client, "_create_provider", return_value=mock_provider_instance):
            await client.start()
            assert client._is_started is True
            mock_provider_instance.initialize.assert_called_once()

            await client.stop()
            assert client._is_started is False

    async def test_generate_without_start(self) -> None:
        """Testa erro ao gerar sem start."""
        client = LLMClient(provider=LLMProvider.LOCAL)

        with pytest.raises(LLMError) as exc_info:
            await client.generate("Test")

        assert "não inicializado" in str(exc_info.value)

    async def test_generate_success(self, mock_provider) -> None:
        """Testa geração bem-sucedida."""
        client = LLMClient(provider=LLMProvider.LOCAL)
        client._provider_instance = mock_provider
        client._is_started = True

        response = await client.generate("Test prompt")

        assert response.text == "Response"
        mock_provider.generate.assert_called_once()

        # Verifica que o request foi criado corretamente
        call_args = mock_provider.generate.call_args
        request = call_args[0][0]
        assert isinstance(request, LLMRequest)
        assert request.prompt == "Test prompt"

    async def test_generate_with_system_prompt(self, mock_provider) -> None:
        """Testa geração com prompt de sistema."""
        client = LLMClient(provider=LLMProvider.LOCAL)
        client._provider_instance = mock_provider
        client._is_started = True

        await client.generate(
            prompt="Test",
            system_prompt="You are helpful",
        )

        call_args = mock_provider.generate.call_args
        request = call_args[0][0]
        assert request.system_prompt == "You are helpful"

    async def test_generate_batch(self, mock_provider) -> None:
        """Testa geração em lote."""
        client = LLMClient(provider=LLMProvider.LOCAL)
        client._provider_instance = mock_provider
        client._is_started = True

        responses = await client.generate_batch(
            prompts=["Prompt 1", "Prompt 2", "Prompt 3"],
        )

        assert len(responses) == 3
        assert mock_provider.generate.call_count == 3

    async def test_healthcheck(self, mock_provider) -> None:
        """Testa verificação de saúde."""
        client = LLMClient(provider=LLMProvider.LOCAL)
        client._provider_instance = mock_provider

        result = await client.healthcheck()
        assert result is True

    async def test_healthcheck_not_initialized(self) -> None:
        """Testa healthcheck sem provider."""
        client = LLMClient(provider=LLMProvider.LOCAL)

        result = await client.healthcheck()
        assert result is False

    async def test_context_manager(self, mock_provider) -> None:
        """Testa uso como context manager."""
        with patch.object(LLMClient, "_create_provider", return_value=mock_provider):
            async with LLMClient(provider=LLMProvider.LOCAL) as client:
                assert client._is_started is True

            # Após exit, deve estar parado
            assert client._is_started is False

    async def test_create_provider_openai_missing_key(self) -> None:
        """Testa erro ao criar provider OpenAI sem API key."""
        client = LLMClient(
            provider=LLMProvider.OPENAI,
            # api_key não fornecido
        )

        with pytest.raises(LLMConfigurationError) as exc_info:
            client._create_provider()

        assert "api_key" in str(exc_info.value).lower()

    async def test_create_provider_anthropic_missing_key(self) -> None:
        """Testa erro ao criar provider Anthropic sem API key."""
        client = LLMClient(
            provider=LLMProvider.ANTHROPIC,
            # api_key não fornecido
        )

        with pytest.raises(LLMConfigurationError) as exc_info:
            client._create_provider()

        assert "api_key" in str(exc_info.value).lower()

    def test_repr(self) -> None:
        """Testa representação string."""
        client = LLMClient(provider=LLMProvider.OPENAI, model="gpt-4")
        assert "LLMClient" in repr(client)
        assert "openai" in repr(client).lower()


@pytest.mark.asyncio
class TestCreateClient:
    """Testes para função create_client."""

    async def test_create_and_initialize(self, mock_provider) -> None:
        """Testa criação e inicialização em um passo."""
        with patch.object(LLMClient, "_create_provider", return_value=mock_provider):
            client = await create_client(
                provider=LLMProvider.LOCAL,
                model="llama2",
            )

            assert client._is_started is True
            mock_provider.initialize.assert_called_once()
