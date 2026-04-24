"""
Testes unitários para BaseProvider.
"""

import pytest
from neural_hive_llm.providers.base import BaseProvider
from neural_hive_llm.models import LLMRequest, LLMStreamChunk


class DummyProvider(BaseProvider):
    """Provider dummy para testes."""

    async def _initialize(self) -> None:
        """Inicialização dummy."""
        self.initialized = True

    async def _shutdown(self) -> None:
        """Shutdown dummy."""
        self.initialized = False

    async def generate(self, request: LLMRequest):
        """Generate dummy."""
        from neural_hive_llm.models import LLMResponse, LLMProvider
        return LLMResponse(
            text="Dummy response",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model="dummy",
            provider=LLMProvider.LOCAL,
            latency_ms=100,
        )

    async def generate_stream(self, request: LLMRequest):
        """Generate stream dummy."""
        yield LLMStreamChunk(delta="Dummy")


class TestBaseProvider:
    """Testes para BaseProvider."""

    @pytest.mark.asyncio
    async def test_initialization(self) -> None:
        """Testa inicialização do provider."""
        provider = DummyProvider(model="dummy")
        assert provider._is_initialized is False

        await provider.initialize()
        assert provider._is_initialized is True
        assert provider.initialized is True

    @pytest.mark.asyncio
    async def test_shutdown(self) -> None:
        """Testa shutdown do provider."""
        provider = DummyProvider(model="dummy")
        await provider.initialize()
        assert provider._is_initialized is True

        await provider.shutdown()
        assert provider._is_initialized is False
        assert provider.initialized is False

    @pytest.mark.asyncio
    async def test_generate(self) -> None:
        """Testa método generate."""
        provider = DummyProvider(model="dummy")
        await provider.initialize()

        request = LLMRequest(prompt="Test")
        response = await provider.generate(request)

        assert response.text == "Dummy response"
        assert response.total_tokens == 15

    @pytest.mark.asyncio
    async def test_generate_stream(self) -> None:
        """Testa método generate_stream."""
        provider = DummyProvider(model="dummy")
        await provider.initialize()

        request = LLMRequest(prompt="Test")
        chunks = []
        async for chunk in provider.generate_stream(request):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].delta == "Dummy"

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Testa uso como context manager."""
        async with DummyProvider(model="dummy") as provider:
            assert provider._is_initialized is True
            assert provider.initialized is True

        # Após exit, deve estar desligado
        assert provider._is_initialized is False

    def test_repr(self) -> None:
        """Testa representação string."""
        provider = DummyProvider(model="dummy-model")
        assert repr(provider) == "DummyProvider(model=dummy-model)"
