"""Provider para Anthropic API.

Implementa cliente LLM usando o SDK oficial da Anthropic.
"""

from typing import AsyncIterator, Optional

from neural_hive_llm.models import LLMProvider, LLMResponse, LLMStreamChunk
from neural_hive_llm.providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Provider para Anthropic API (Claude).

    Usa o SDK oficial anthropic>=0.40.0 para comunicação com
    modelos Claude 3 Opus, Sonnet, Haiku.
    """

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Inicializa provider Anthropic.

        Args:
            model: Nome do modelo (claude-3-5-sonnet, claude-3-opus, etc)
            api_key: Chave da API Anthropic
            endpoint_url: URL customizada (geralmente não usado)
            timeout: Timeout de requisição
        """
        super().__init__(model, api_key, endpoint_url, timeout)
        self._client = None

    async def start(self):
        """Inicializa cliente Anthropic."""
        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.endpoint_url,
                timeout=self.timeout,
            )
        except ImportError as e:
            raise ImportError(
                "SDK Anthropic não instalado. Instale com: pip install anthropic"
            ) from e

    async def stop(self):
        """Fecha cliente Anthropic."""
        if self._client:
            # Cliente Anthropic não tem método close explícito
            self._client = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> LLMResponse:
        """Gera texto usando Anthropic Claude.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema (parâmetro separado no Claude)
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens
            **kwargs: Parâmetros adicionais (top_p, etc)

        Returns:
            LLMResponse com resultado
        """
        if not self._client:
            await self.start()

        message = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            **kwargs,
        )

        return LLMResponse.from_provider_response(
            text=message.content[0].text,
            model=self.model,
            provider=LLMProvider.ANTHROPIC,
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            finish_reason=message.stop_reason,
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

        accumulated = ""

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                accumulated += text
                yield LLMStreamChunk(
                    text=accumulated,
                    delta=text,
                    is_final=False,
                )

        yield LLMStreamChunk(
            text=accumulated,
            delta="",
            is_final=True,
            finish_reason="end_turn",
        )

    async def healthcheck(self) -> bool:
        """Verifica saúde da conexão Anthropic.

        Returns:
            True se conexão está saudável
        """
        try:
            if not self._client:
                await self.start()
            await self._client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True
        except Exception:
            return False


__all__ = ["AnthropicProvider"]
