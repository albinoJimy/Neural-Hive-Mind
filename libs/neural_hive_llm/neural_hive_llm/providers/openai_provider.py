"""
OpenAI Provider - implementação para OpenAI API.

Usa lazy import do SDK OpenAI para permitir instalação opcional.
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any, Optional

from neural_hive_llm.exceptions import (
    LLMError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from neural_hive_llm.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from neural_hive_llm.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    """
    Provider para OpenAI API.

    Suporta:
    - GPT-4, GPT-4 Turbo, GPT-3.5 Turbo
    - Streaming assíncrono
    - Token counting via SDK
    - Retry automático via tenacity (decorator externo)
    """

    # Tabela de preços por 1M tokens (atualizada 2024)
    PRICING = {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo-preview": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    }

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-3.5-turbo",
        base_url: Optional[str] = None,
        timeout_seconds: float = 60.0,
        organization: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Inicializa provider OpenAI.

        Args:
            api_key: Chave de API OpenAI (obrigatória)
            model: Modelo a utilizar (default: gpt-3.5-turbo)
            base_url: URL base customizada (para proxies/Azure)
            timeout_seconds: Timeout para requisições
            organization: ID da organização OpenAI (opcional)
            **kwargs: Parâmetros adicionais
        """
        super().__init__(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            model=model,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        self.organization = organization
        self._client: Optional[Any] = None

    async def _initialize(self) -> None:
        """Inicializa cliente OpenAI (lazy import)."""
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "OpenAI SDK não instalado. Instale com: pip install 'neural-hive-llm[openai]'"
            ) from exc

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            organization=self.organization,
            timeout=self.timeout_seconds,
        )

    async def _shutdown(self) -> None:
        """Fecha o cliente OpenAI."""
        if self._client:
            await self._client.close()
            self._client = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Gera resposta usando OpenAI API.

        Args:
            request: Requisição de geração

        Returns:
            LLMResponse: Resposta gerada com contagem de tokens

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._client:
            await self.initialize()

        start_time = time.time()

        # Constrói messages
        messages = self._build_messages(request)

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p,
                    frequency_penalty=request.frequency_penalty,
                    presence_penalty=request.presence_penalty,
                    stop=request.stop_sequences,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="openai",
                original_error=exc,
            ) from exc
        except Exception as exc:
            raise self._map_exception(exc) from exc

        latency_ms = (time.time() - start_time) * 1000

        # Extrai resposta
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage

        return LLMResponse(
            text=text,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            model=self.model,
            provider=LLMProvider.OPENAI,
            finish_reason=choice.finish_reason,
            estimated_cost_usd=self._calculate_cost(usage.prompt_tokens, usage.completion_tokens),
            latency_ms=latency_ms,
            raw_response={"model": response.model, "id": response.id},
            metadata=request.metadata,
        )

    async def generate_stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Gera resposta com streaming usando OpenAI API.

        Args:
            request: Requisição de geração

        Yields:
            LLMStreamChunk: Chunks da resposta

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._client:
            await self.initialize()

        messages = self._build_messages(request)

        try:
            stream = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p,
                    frequency_penalty=request.frequency_penalty,
                    presence_penalty=request.presence_penalty,
                    stop=request.stop_sequences,
                    stream=True,
                ),
                timeout=self.timeout_seconds,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # Primeiro chunk pode conter prompt_tokens
                prompt_tokens = None
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens

                yield LLMStreamChunk(
                    delta=delta.content or "",
                    finish_reason=finish_reason,
                    is_complete=finish_reason is not None,
                    prompt_tokens=prompt_tokens,
                )

        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="openai",
                original_error=exc,
            ) from exc
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """
        Constrói lista de messages para OpenAI API.

        Args:
            request: Requisição de geração

        Returns:
            list[dict]: Lista formatada de messages
        """
        messages = []

        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        messages.append({"role": "user", "content": request.prompt})

        return messages

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Calcula custo estimado da requisição.

        Args:
            prompt_tokens: Tokens do prompt
            completion_tokens: Tokens da resposta

        Returns:
            float: Custo em USD
        """
        pricing = self.PRICING.get(self.model, {"input": 0.0, "output": 0.0})
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def _map_exception(self, exc: Exception) -> LLMError:
        """
        Mapeia exceções do SDK OpenAI para exceções da biblioteca.

        Args:
            exc: Exceção original do SDK

        Returns:
            LLMError: Exceção mapeada
        """
        from openai import APIConnectionError, APITimeoutError, RateLimitError

        if isinstance(exc, RateLimitError):
            return LLMRateLimitError(
                "Rate limit da OpenAI excedido",
                provider="openai",
                original_error=exc,
            )
        if isinstance(exc, APITimeoutError):
            return LLMTimeoutError(
                "Timeout da API OpenAI",
                provider="openai",
                original_error=exc,
            )
        if isinstance(exc, APIConnectionError):
            return LLMProviderError(
                "Erro de conexão com API OpenAI",
                provider="openai",
                original_error=exc,
            )

        # Tentar extrair informações da exceção genérica
        error_msg = str(exc)
        if "rate limit" in error_msg.lower():
            return LLMRateLimitError(error_msg, provider="openai", original_error=exc)
        if "timeout" in error_msg.lower():
            return LLMTimeoutError(error_msg, provider="openai", original_error=exc)
        if "invalid" in error_msg.lower() or "validation" in error_msg.lower():
            return LLMInvalidRequestError(error_msg, provider="openai", original_error=exc)

        return LLMProviderError(str(exc), provider="openai", original_error=exc)

    async def generate_embeddings(
        self,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        """
        Gera embeddings usando OpenAI API.

        Args:
            request: Requisição de embedding

        Returns:
            EmbeddingResponse: Embeddings gerados

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._client:
            await self.initialize()

        start_time = time.time()

        # Normaliza input para lista
        input_texts = [request.input] if isinstance(request.input, str) else list(request.input)

        try:
            response = await asyncio.wait_for(
                self._client.embeddings.create(
                    input=input_texts,
                    model=request.model,
                    encoding_format=request.encoding_format,
                    dimensions=request.dimensions,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="openai",
                original_error=exc,
            ) from exc
        except Exception as exc:
            raise self._map_exception(exc) from exc

        latency_ms = (time.time() - start_time) * 1000

        # Extrai embeddings
        data = [
            EmbeddingVector(
                index=idx,
                embedding=item.embedding,
            )
            for idx, item in enumerate(response.data)
        ]

        # Ordena por index (OpenAI pode retornar fora de ordem)
        data.sort(key=lambda x: x.index)

        return EmbeddingResponse(
            object=response.object,
            data=data,
            model=response.model,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=0,
            ),
            provider=LLMProvider.OPENAI,
            latency_ms=latency_ms,
        )
