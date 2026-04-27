"""Provider para modelos locais (Ollama).

Implementa cliente LLM usando HTTP client para comunicação
com modelos locais hospedados via Ollama.
"""

from typing import AsyncIterator, Optional

import httpx
from neural_hive_llm.models import LLMProvider, LLMResponse, LLMStreamChunk
from neural_hive_llm.providers.base import BaseProvider


class LocalProvider(BaseProvider):
    """Provider para modelos locais (Ollama).

    Usa HTTP client para comunicação com Ollama API em
    localhost:11434 ou URL customizada.
    """

    DEFAULT_ENDPOINT = "http://localhost:11434/api"

    def __init__(
        self,
        model: str = "llama3",
        api_key: Optional[str] = None,  # Não usado mas mantido para compatibilidade
        endpoint_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Inicializa provider local.

        Args:
            model: Nome do modelo Ollama (llama3, mistral, etc)
            api_key: Não usado (mantido para compatibilidade de interface)
            endpoint_url: URL do endpoint Ollama
            timeout: Timeout de requisição
        """
        super().__init__(model, api_key, endpoint_url or self.DEFAULT_ENDPOINT, timeout)
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Inicializa HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.endpoint_url,
            timeout=self.timeout,
        )

    async def stop(self):
        """Fecha HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> LLMResponse:
        """Gera texto usando modelo local.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema (concatenado ao prompt)
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens (num_predict no Ollama)
            **kwargs: Parâmetros adicionais

        Returns:
            LLMResponse com resultado
        """
        if not self._client:
            await self.start()

        # Ollama usa prompt único (system + user concatenados)
        full_prompt = f"{system_prompt or ''}\n\n{prompt}".strip()

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        response = await self._client.post("/generate", json=payload)
        response.raise_for_status()

        data = response.json()
        text = data.get("response", "")
        # Ollama não retorna contagem de tokens
        # Estimar usando heurística simples
        estimated_tokens = len(text) // 4

        return LLMResponse.from_provider_response(
            text=text,
            model=self.model,
            provider=LLMProvider.LOCAL,
            prompt_tokens=estimated_tokens // 2,
            completion_tokens=estimated_tokens // 2,
            finish_reason=data.get("done_reason"),
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Gera texto com streaming.

        NOTA: Streaming com Ollama requer implementação adicional
        de parsing de NDJSON. Esta é uma implementação básica.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens
            **kwargs: Parâmetros adicionais

        Yields:
            LLMStreamChunk com texto parcial

        Raises:
            NotImplementedError: Streaming não suportado nesta versão
        """
        raise NotImplementedError(
            "Streaming para provider local ainda não implementado. "
            "Use generate() para resposta completa."
        )

    async def healthcheck(self) -> bool:
        """Verifica saúde da conexão Ollama.

        Returns:
            True se conexão está saudável
        """
        try:
            if not self._client:
                await self.start()

            response = await self._client.get("/tags")
            return response.status_code == 200
        except Exception:
            return False


__all__ = ["LocalProvider"]
