"""
LLMClient - Cliente principal para neural_hive_llm.

Coordena providers e expõe API unificada para geração de texto.
"""

from collections.abc import AsyncGenerator
from typing import Optional, Union

from neural_hive_llm.config import LLMSettings
from neural_hive_llm.exceptions import LLMConfigurationError, LLMError
from neural_hive_llm.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)
from neural_hive_llm.providers.anthropic_provider import AnthropicProvider
from neural_hive_llm.providers.base import BaseProvider
from neural_hive_llm.providers.local_provider import LocalProvider
from neural_hive_llm.providers.openai_provider import OpenAIProvider


class LLMClient:
    """
    Cliente principal para geração de texto com LLMs.

    Oferece interface unificada para múltiplos providers com:
    - Geração síncrona e streaming
    - Retry automático
    - Observabilidade integrada
    - Type safety completo

    Example:
        >>> client = LLMClient(provider=LLMProvider.OPENAI, api_key="sk-...")
        >>> await client.start()
        >>> response = await client.generate("Explique microserviços")
        >>> print(response.text)
        >>> await client.stop()
    """

    def __init__(
        self,
        provider: Union[LLMProvider, str] = LLMProvider.LOCAL,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Optional[LLMSettings] = None,
        **kwargs,
    ) -> None:
        """
        Inicializa cliente LLM.

        Args:
            provider: Provider a utilizar (enum ou string)
            api_key: API key para providers remotos
            model: Modelo específico a utilizar
            base_url: URL base (para provider local)
            settings: Configurações completas (sobrescreve outros args)
            **kwargs: Parâmetros adicionais para o provider
        """
        # Se settings é fornecido, usa ele prioritariamente
        if settings:
            self.settings = settings
            self.provider = settings.provider
        else:
            self.provider = LLMProvider(provider) if isinstance(provider, str) else provider
            self.settings = None

        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.extra_kwargs = kwargs

        self._provider_instance: Optional[BaseProvider] = None
        self._is_started = False

    async def start(self) -> None:
        """
        Inicializa o cliente e o provider subjacente.

        Deve ser chamado antes de qualquer operação de geração.
        """
        if self._is_started:
            return

        self._provider_instance = self._create_provider()
        await self._provider_instance.initialize()
        self._is_started = True

    async def stop(self) -> None:
        """
        Para o cliente e limpa recursos.

        Deve ser chamado ao encerrar o uso do cliente.
        """
        if self._provider_instance:
            await self._provider_instance.shutdown()
            self._provider_instance = None
        self._is_started = False

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Gera resposta de forma não-streaming.

        Args:
            prompt: Prompt principal do usuário
            system_prompt: Prompt de sistema (contexto/role)
            temperature: Temperatura de amostragem (0-2)
            max_tokens: Máximo de tokens a gerar
            **kwargs: Parâmetros adicionais

        Returns:
            LLMResponse: Resposta gerada

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._is_started:
            raise LLMError("Cliente não inicializado. Chame await client.start()")

        # Usa valores do settings se não fornecidos
        if self.settings:
            temperature = temperature if temperature is not None else self.settings.temperature
            max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens

        request = LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature or 0.7,
            max_tokens=max_tokens,
            **kwargs,
        )

        return await self._provider_instance.generate(request)

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Gera resposta com streaming.

        Args:
            prompt: Prompt principal do usuário
            system_prompt: Prompt de sistema (contexto/role)
            temperature: Temperatura de amostragem (0-2)
            max_tokens: Máximo de tokens a gerar
            **kwargs: Parâmetros adicionais

        Yields:
            LLMStreamChunk: Chunks da resposta

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._is_started:
            raise LLMError("Cliente não inicializado. Chame await client.start()")

        if self.settings:
            temperature = temperature if temperature is not None else self.settings.temperature
            max_tokens = max_tokens if max_tokens is not None else self.settings.max_tokens

        request = LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature or 0.7,
            max_tokens=max_tokens,
            **kwargs,
        )

        async for chunk in self._provider_instance.generate_stream(request):
            yield chunk

    async def generate_batch(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> list[LLMResponse]:
        """
        Gera respostas para múltiplos prompts em paralelo.

        Args:
            prompts: Lista de prompts
            system_prompt: Prompt de sistema compartilhado
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens
            **kwargs: Parâmetros adicionais

        Returns:
            list[LLMResponse]: Respostas geradas

        Raises:
            LLMError: Em caso de erro
        """
        import asyncio

        tasks = [
            self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            for prompt in prompts
        ]

        return await asyncio.gather(*tasks)

    async def healthcheck(self) -> bool:
        """
        Verifica se o provider está saudável.

        Returns:
            bool: True se saudável
        """
        if not self._provider_instance:
            return False
        return await self._provider_instance.healthcheck()

    async def generate_embeddings(
        self,
        input: str | list[str],
        model: str | None = None,
        encoding_format: str = "float",
        dimensions: int | None = None,
        **kwargs,
    ) -> EmbeddingResponse:
        """
        Gera embeddings para textos.

        Args:
            input: Texto ou lista de textos para gerar embeddings
            model: Modelo de embedding (default: text-embedding-3-small)
            encoding_format: Formato do embedding ('float' ou 'base64')
            dimensions: Dimensões do embedding (para modelos que suportam)
            **kwargs: Parâmetros adicionais

        Returns:
            EmbeddingResponse: Embeddings gerados

        Raises:
            LLMError: Em caso de erro na geração
            NotImplementedError: Se provider não suportar embeddings
        """
        if not self._is_started:
            raise LLMError("Cliente não inicializado. Chame await client.start()")

        request = EmbeddingRequest(
            input=input,
            model=model or "text-embedding-3-small",
            encoding_format=encoding_format,
            dimensions=dimensions,
            **kwargs,
        )

        return await self._provider_instance.generate_embeddings(request)

    def _create_provider(self) -> BaseProvider:
        """
        Cria instância do provider baseado na configuração.

        Returns:
            BaseProvider: Provider instanciado

        Raises:
            LLMConfigurationError: Se configuração for inválida
        """
        # Determina parâmetros
        if self.settings:
            provider = self.settings.provider
            api_key = self.settings.api_key
            model = self.settings.model
            base_url = self.settings.base_url
            timeout = self.settings.timeout_seconds
        else:
            provider = self.provider
            api_key = self.api_key
            model = self.model or "default"
            base_url = self.base_url
            timeout = 60.0

        # Cria provider específico
        if provider == LLMProvider.OPENAI:
            if not api_key:
                raise LLMConfigurationError("api_key é obrigatório para OpenAI")
            return OpenAIProvider(
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout_seconds=timeout,
                **self.extra_kwargs,
            )

        if provider == LLMProvider.ANTHROPIC:
            if not api_key:
                raise LLMConfigurationError("api_key é obrigatório para Anthropic")
            return AnthropicProvider(
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout_seconds=timeout,
                **self.extra_kwargs,
            )

        if provider == LLMProvider.LOCAL:
            return LocalProvider(
                base_url=base_url or "http://localhost:11434",
                model=model,
                timeout_seconds=timeout,
                **self.extra_kwargs,
            )

        raise LLMConfigurationError(f"Provider não suportado: {provider}")

    async def __aenter__(self):
        """Suporte para async context manager."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Suporte para async context manager."""
        await self.stop()

    def __repr__(self) -> str:
        """Representação string do cliente."""
        provider_name = (
            self.provider.value if isinstance(self.provider, LLMProvider) else self.provider
        )
        return f"LLMClient(provider={provider_name}, model={self.model})"


# Função de conveniência para criação rápida
async def create_client(
    provider: Union[LLMProvider, str] = LLMProvider.LOCAL,
    **kwargs,
) -> LLMClient:
    """
    Cria e inicializa um cliente LLM.

    Args:
        provider: Provider a utilizar
        **kwargs: Parâmetros adicionais para o cliente

    Returns:
        LLMClient: Cliente inicializado

    Example:
        >>> client = await create_client(
        ...     provider=LLMProvider.OPENAI,
        ...     api_key="sk-...",
        ...     model="gpt-4"
        ... )
        >>> response = await client.generate("Olá")
        >>> await client.stop()
    """
    client = LLMClient(provider=provider, **kwargs)
    await client.start()
    return client
