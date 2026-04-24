"""
Local Provider - implementação para Ollama e outros endpoints locais.

Usa httpx diretamente sem depender de SDKs específicos.
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Optional

import httpx

from neural_hive_llm.exceptions import (
    LLMError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from neural_hive_llm.models import LLMProvider, LLMRequest, LLMResponse, LLMStreamChunk
from neural_hive_llm.providers.base import BaseProvider


class LocalProvider(BaseProvider):
    """
    Provider para LLMs locais via HTTP (Ollama, vLLM, etc).

    Suporta:
    - Ollama /api/generate e /api/chat endpoints
    - Estimativa de tokens (heurística)
    - Streaming (opcional)
    """

    # Estimativa de preços (local é "grátis", mas para consistência)
    PRICING = {"default": {"input": 0.0, "output": 0.0}}

    # Estimativa de caracteres por token (varia por modelo)
    CHARS_PER_TOKEN = 4.0

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama2",
        timeout_seconds: float = 120.0,
        **kwargs,
    ) -> None:
        """
        Inicializa provider local.

        Args:
            base_url: URL base do serviço local
            model: Nome do modelo
            timeout_seconds: Timeout para requisições
            **kwargs: Parâmetros adicionais
        """
        super().__init__(
            api_key=None,  # Local não precisa de API key
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def _initialize(self) -> None:
        """Inicializa cliente HTTP."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )

    async def _shutdown(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Gera resposta usando endpoint local.

        Args:
            request: Requisição de geração

        Returns:
            LLMResponse: Resposta gerada

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._client:
            await self.initialize()

        start_time = time.time()

        # Constrói payload para Ollama /api/generate
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
        }

        # Adiciona parâmetros opcionais
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.temperature != 0.7:
            payload["temperature"] = request.temperature
        if request.top_p != 1.0:
            payload["top_p"] = request.top_p
        if request.max_tokens:
            payload["num_predict"] = request.max_tokens

        try:
            response = await asyncio.wait_for(
                self._client.post("/api/generate", json=payload),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="local",
                original_error=exc,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise self._map_exception(exc) from exc
        except Exception as exc:
            raise LLMProviderError(
                f"Erro na requisição: {exc}",
                provider="local",
                original_error=exc,
            ) from exc

        latency_ms = (time.time() - start_time) * 1000

        # Parse resposta do Ollama
        data = response.json()
        text = data.get("response", "")

        # Estima tokens (Ollama retorna prompt_eval_count e eval_count)
        prompt_tokens = data.get("prompt_eval_count", self._estimate_tokens(request.prompt))
        completion_tokens = data.get("eval_count", self._estimate_tokens(text))

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=self.model,
            provider=LLMProvider.LOCAL,
            finish_reason=data.get("done_reason"),
            estimated_cost_usd=0.0,  # Local é gratuito
            latency_ms=latency_ms,
            raw_response=data,
            metadata=request.metadata,
        )

    async def generate_stream(
        self, request: LLMRequest
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """
        Gera resposta com streaming (suporte limitado para Ollama).

        Nota: Ollama usa newlines para separar eventos de streaming.

        Args:
            request: Requisição de geração

        Yields:
            LLMStreamChunk: Chunks da resposta

        Raises:
            LLMError: Em caso de erro na geração
        """
        if not self._client:
            await self.initialize()

        # Constrói payload para Ollama streaming
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": True,
        }

        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.temperature != 0.7:
            payload["temperature"] = request.temperature
        if request.max_tokens:
            payload["num_predict"] = request.max_tokens

        try:
            async with self._client.stream(
                "POST", "/api/generate", json=payload, timeout=self.timeout_seconds
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        data = line if isinstance(line, dict) else eval(line)
                    except Exception:
                        # Se não for JSON válido, usar como texto cru
                        yield LLMStreamChunk(delta=line)
                        continue

                    delta = data.get("response", "")
                    done = data.get("done", False)

                    yield LLMStreamChunk(
                        delta=delta,
                        is_complete=done,
                        prompt_tokens=data.get("prompt_eval_count"),
                    )

        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(
                f"Timeout após {self.timeout_seconds}s",
                provider="local",
                original_error=exc,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise self._map_exception(exc) from exc
        except Exception as exc:
            raise LLMProviderError(
                f"Erro no streaming: {exc}",
                provider="local",
                original_error=exc,
            ) from exc

    def _estimate_tokens(self, text: str) -> int:
        """
        Estima número de tokens com base em caracteres.

        Args:
            text: Texto para estimar

        Returns:
            int: Estimativa de tokens
        """
        return max(1, int(len(text) / self.CHARS_PER_TOKEN))

    def _map_exception(self, exc: httpx.HTTPStatusError) -> LLMError:
        """
        Mapeia exceções HTTP para exceções da biblioteca.

        Args:
            exc: Exceção HTTP

        Returns:
            LLMError: Exceção mapeada
        """
        status_code = exc.response.status_code
        error_msg = exc.response.text

        if status_code == 429:
            return LLMRateLimitError(
                "Rate limit excedido",
                provider="local",
                original_error=exc,
            )
        if status_code == 400:
            return LLMInvalidRequestError(
                f"Requisição inválida: {error_msg}",
                provider="local",
                original_error=exc,
            )
        if status_code >= 500:
            return LLMProviderError(
                f"Erro no servidor: {error_msg}",
                provider="local",
                original_error=exc,
            )

        return LLMProviderError(
            f"Erro HTTP {status_code}: {error_msg}",
            provider="local",
            original_error=exc,
        )

    async def healthcheck(self) -> bool:
        """
        Verifica saúde do serviço local via /api/tags.

        Returns:
            bool: True se o serviço está respondendo
        """
        try:
            if not self._client:
                await self.initialize()
            response = await self._client.get("/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
