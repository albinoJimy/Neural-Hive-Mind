"""
Base Provider - classe abstrata para todos os providers LLM.

Define a interface comum que todos os providers devem implementar.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Optional

from neural_hive_llm.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)


class BaseProvider(ABC):
    """
    Classe abstrata base para providers LLM.

    Todos os providers devem herdar desta classe e implementar os métodos
    abstratos definidos abaixo.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "default",
        timeout_seconds: float = 60.0,
        **kwargs,
    ) -> None:
        """
        Inicializa o provider.

        Args:
            api_key: Chave de API (para providers remotos)
            base_url: URL base (para providers locais)
            model: Nome do modelo a utilizar
            timeout_seconds: Timeout padrão para requisições
            **kwargs: Parâmetros adicionais específicos do provider
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.kwargs = kwargs
        self._is_initialized = False

    async def initialize(self) -> None:
        """
        Inicializa o provider (lazy initialization de SDKs, etc).

        Este método deve ser chamado antes de qualquer operação.
        """
        if not self._is_initialized:
            await self._initialize()
            self._is_initialized = True

    async def _initialize(self) -> None:
        """
        Implementação específica da inicialização.

        Override este método para inicializar clientes, conectar a serviços, etc.
        """
        pass

    async def shutdown(self) -> None:
        """
        Fecha conexões e limpa recursos.

        Este método deve ser chamado ao encerrar o uso do provider.
        """
        if self._is_initialized:
            await self._shutdown()
            self._is_initialized = False

    async def _shutdown(self) -> None:
        """
        Implementação específica do shutdown.

        Override este método para fechar clientes, desconectar, etc.
        """
        pass

    @abstractmethod
    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        Gera resposta assíncrona (non-streaming).

        Args:
            request: Requisição de geração

        Returns:
            LLMResponse: Resposta gerada

        Raises:
            LLMError: Em caso de erro na geração
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        request: LLMRequest,
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Gera resposta assíncrona com streaming.

        Args:
            request: Requisição de geração

        Yields:
            LLMStreamChunk: Chunks da resposta

        Raises:
            LLMError: Em caso de erro na geração
        """
        pass

    async def healthcheck(self) -> bool:
        """
        Verifica se o provider está saudável.

        Returns:
            bool: True se o provider está saudável
        """
        try:
            # Implementação padrão: tentar gerar resposta simples
            test_request = LLMRequest(prompt="test", max_tokens=5)
            await self.generate(test_request)
            return True
        except Exception:
            return False

    async def generate_embeddings(
        self,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        """
        Gera embeddings para textos.

        Args:
            request: Requisição de embedding

        Returns:
            EmbeddingResponse: Embeddings gerados

        Raises:
            NotImplementedError: Se provider não suportar embeddings
        """
        raise NotImplementedError(f"{self.__class__.__name__} não suporta embeddings")

    def __repr__(self) -> str:
        """Representação string do provider."""
        return f"{self.__class__.__name__}(model={self.model})"

    async def __aenter__(self):
        """Suporte para async context manager."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Suporte para async context manager."""
        await self.shutdown()
