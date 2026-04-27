"""Provider para OpenAI API.

Implementa cliente LLM usando o SDK oficial da OpenAI.
"""

from typing import AsyncIterator, Optional

from neural_hive_llm.models import LLMProvider, LLMResponse, LLMStreamChunk
from neural_hive_llm.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    """Provider para OpenAI API.

    Usa o SDK oficial openai>=1.40.0 para comunicação com
    modelos GPT-4, GPT-3.5-turbo, etc.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Inicializa provider OpenAI.

        Args:
            model: Nome do modelo (gpt-4o, gpt-4-turbo, gpt-3.5-turbo, etc)
            api_key: Chave da API OpenAI
            endpoint_url: URL customizada (para Azure OpenAI, etc)
            timeout: Timeout de requisição
        """
        super().__init__(model, api_key, endpoint_url, timeout)
        self._client = None

    async def start(self):
        """Inicializa cliente OpenAI."""
        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.endpoint_url,
                timeout=self.timeout,
            )
        except ImportError as e:
            raise ImportError(
                "SDK OpenAI não instalado. Instale com: pip install openai"
            ) from e

    async def stop(self):
        """Fecha cliente OpenAI."""
        if self._client:
            await self._client.close()
            self._client = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> LLMResponse:
        """Gera texto usando OpenAI.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens
            **kwargs: Parâmetros adicionais (top_p, frequency_penalty, etc)

        Returns:
            LLMResponse com resultado
        """
        if not self._client:
            await self.start()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        return LLMResponse.from_provider_response(
            text=choice.message.content or "",
            model=self.model,
            provider=LLMProvider.OPENAI,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            finish_reason=choice.finish_reason,
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

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens
            **kwargs: Parâmetros adicionais

        Yields:
            LLMStreamChunk com texto parcial
        """
        if not self._client:
            await self.start()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        accumulated = ""

        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                accumulated += delta
                yield LLMStreamChunk(
                    text=accumulated,
                    delta=delta,
                    is_final=False,
                )

        yield LLMStreamChunk(
            text=accumulated,
            delta="",
            is_final=True,
            finish_reason="stop",
        )

    async def healthcheck(self) -> bool:
        """Verifica saúde da conexão OpenAI.

        Returns:
            True se conexão está saudável
        """
        try:
            if not self._client:
                await self.start()
            # Chamada simples de teste
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return True
        except Exception:
            return False


__all__ = ["OpenAIProvider"]
