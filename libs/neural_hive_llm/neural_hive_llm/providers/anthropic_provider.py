"""
Anthropic Provider - implementação para Anthropic (Claude) API.

Usa lazy import do SDK Anthropic para permitir instalação opcional.
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
from neural_hive_llm.models import LLMProvider, LLMRequest, LLMResponse, LLMStreamChunk
from neural_hive_llm.providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    """
    Provider para Anthropic (Claude) API.

    Suporta:
    - Claude 3 Opus, Sonnet, Haiku
    - Streaming assíncrono
    - Token counting via SDK
    - System parameter separado
    """

    # Tabela de preços por 1M tokens (atualizada 2024)
    PRICING = {
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-sonnet-20240229",
        base_url: Optional[str] = None,
        timeout_seconds: float = 60.0,
        api_version: str = "2023-06-01",
        **kwargs,
    ) -> None:
        """
        Inicializa provider Anthropic.

        Args:
            api_key: Chave de API Anthropic (obrigatória)
            model: Modelo a utilizar (default: claude-3-sonnet)
            base_url: URL base customizada
            timeout_seconds: Timeout para requisições
            api_version: Versão da API
            **kwargs: Parâmetros adicionais
        """
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        self.api_version = api_version
        self._client: Optional[Any] = None

    async def _initialize(self) -> None:
        """Inicializa cliente Anthropic (lazy import)."""
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic SDK não instalado. Instale com: pip install 'neural-hive-llm[anthropic]'"
            ) from exc

        self._client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,  # Retry é feito pelo decorator externo
        )

    async def _shutdown(self) -> None:
        """Fecha o cliente Anthropic."""
        if self._client:
            self._client = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Gera resposta usando Anthropic API.

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

        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self.model,
                    max_tokens=request.max_tokens or 4096,
                    system=request.system_prompt,
                    messages=[{"role": "user", "content": request.prompt}],
                    temperature=request.temperature,
                    top_p=request.top_p,
                    stop_sequences=request.stop_sequences,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="anthropic",
                original_error=exc,
            ) from exc
        except Exception as exc:
            raise self._map_exception(exc) from exc

        latency_ms = (time.time() - start_time) * 1000

        # Extrai resposta
        text = self._extract_text_from_response(response)
        usage = response.usage

        return LLMResponse(
            text=text,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            model=self.model,
            provider=LLMProvider.ANTHROPIC,
            finish_reason=response.stop_reason,
            estimated_cost_usd=self._calculate_cost(
                usage.input_tokens, usage.output_tokens
            ),
            latency_ms=latency_ms,
            raw_response={"id": response.id},
            metadata=request.metadata,
        )

    async def generate_stream(
        self, request: LLMRequest
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Gera resposta com streaming usando Anthropic API.

        Args:
            request: Requisição de geração

        Yields:
            LLMStreamChunk: Chunks da resposta

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._client:
            await self.initialize()

        try:
            stream = await asyncio.wait_for(
                self._client.messages.create(
                    model=self.model,
                    max_tokens=request.max_tokens or 4096,
                    system=request.system_prompt,
                    messages=[{"role": "user", "content": request.prompt}],
                    temperature=request.temperature,
                    top_p=request.top_p,
                    stop_sequences=request.stop_sequences,
                    stream=True,
                ),
                timeout=self.timeout_seconds,
            )

            async for event in stream:
                if event.type == "content_block_delta":
                    yield LLMStreamChunk(
                        delta=event.delta.text,
                        is_complete=False,
                    )
                elif event.type == "message_stop":
                    yield LLMStreamChunk(
                        delta="",
                        finish_reason=event.stop_reason,
                        is_complete=True,
                    )

        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="anthropic",
                original_error=exc,
            ) from exc
        except Exception as exc:
            raise self._map_exception(exc) from exc

    def _extract_text_from_response(self, response: Any) -> str:
        """
        Extrai texto da resposta da API Anthropic.

        A resposta pode ter diferentes formatos dependendo do tipo de conteúdo.

        Args:
            response: Resposta da API

        Returns:
            str: Texto extraído
        """
        text_parts = []

        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, str):
                text_parts.append(block)

        return "".join(text_parts)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calcula custo estimado da requisição.

        Args:
            input_tokens: Tokens do prompt
            output_tokens: Tokens da resposta

        Returns:
            float: Custo em USD
        """
        pricing = self.PRICING.get(self.model, {"input": 0.0, "output": 0.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def _map_exception(self, exc: Exception) -> LLMError:
        """
        Mapeia exceções do SDK Anthropic para exceções da biblioteca.

        Args:
            exc: Exceção original do SDK

        Returns:
            LLMError: Exceção mapeada
        """
        try:
            from anthropic import APIConnectionError, APITimeoutError, RateLimitError
        except ImportError:
            # SDK não instalado, fazer mapeamento genérico
            error_msg = str(exc).lower()
            if "rate limit" in error_msg:
                return LLMRateLimitError(
                    "Rate limit da Anthropic excedido",
                    provider="anthropic",
                    original_error=exc,
                )
            if "timeout" in error_msg:
                return LLMTimeoutError(
                    "Timeout da API Anthropic",
                    provider="anthropic",
                    original_error=exc,
                )
            return LLMProviderError(str(exc), provider="anthropic", original_error=exc)

        if isinstance(exc, RateLimitError):
            return LLMRateLimitError(
                "Rate limit da Anthropic excedido",
                provider="anthropic",
                original_error=exc,
            )
        if isinstance(exc, APITimeoutError):
            return LLMTimeoutError(
                "Timeout da API Anthropic",
                provider="anthropic",
                original_error=exc,
            )
        if isinstance(exc, APIConnectionError):
            return LLMProviderError(
                "Erro de conexão com API Anthropic",
                provider="anthropic",
                original_error=exc,
            )

        # Tentar extrair informações da exceção genérica
        error_msg = str(exc)
        if "rate" in error_msg.lower():
            return LLMRateLimitError(error_msg, provider="anthropic", original_error=exc)
        if "timeout" in error_msg.lower():
            return LLMTimeoutError(error_msg, provider="anthropic", original_error=exc)
        if "invalid" in error_msg.lower() or "validation" in error_msg.lower():
            return LLMInvalidRequestError(
                error_msg, provider="anthropic", original_error=exc
            )

        return LLMProviderError(str(exc), provider="anthropic", original_error=exc)
