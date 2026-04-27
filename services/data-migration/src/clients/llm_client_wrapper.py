"""
Wrapper LLM Client para data-migration usando neural_hive_llm.

Mantém compatibilidade com a API existente enquanto usa
a biblioteca centralizada neural_hive_llm internamente.
Suporta tanto operações assíncronas quanto síncronas.
"""

from typing import Optional

import structlog
from neural_hive_llm import LLMClient as NeuralHiveLLMClient
from neural_hive_llm import LLMProvider, LLMResponse

logger = structlog.get_logger()


class LLMClient:
    """
    Cliente unificado para OpenAI e Anthropic usando neural_hive_llm.

    Wrapper que mantém a API existente do data-migration
    enquanto delega para a biblioteca neural_hive_llm.

    Suporta tanto modo async quanto sync para compatibilidade.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4"):
        """Inicializa o cliente LLM.

        Args:
            api_key: Chave de API do OpenAI (opcional, usa settings se None)
            model: Nome do modelo LLM
        """
        from src.config.settings import get_settings

        settings = get_settings()
        self.api_key = api_key or getattr(settings, "openai_api_key", None)
        self.model = model or getattr(settings, "llm_model", "gpt-4")

        # Criar cliente neural_hive_llm interno
        self._client: Optional[NeuralHiveLLMClient] = None
        self._started = False

    async def _ensure_client(self):
        """Garante que o cliente está inicializado."""
        if not self._client and self.api_key:
            try:
                self._client = NeuralHiveLLMClient(
                    provider=LLMProvider.OPENAI,
                    api_key=self.api_key,
                    model=self.model,
                )
                await self._client.start()
                self._started = True
                logger.info("llm_client_initialized", provider="openai")
            except Exception as e:
                logger.error("llm_client_init_failed", error=str(e))
                self._client = None

    async def generate(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> "ChatCompletion":
        """
        Gera resposta do LLM (compatível com OpenAI).

        Args:
            messages: Lista de mensagens no formato OpenAI
            model: Nome do modelo (override)
            temperature: Temperatura de geração
            max_tokens: Máximo de tokens

        Returns:
            ChatCompletion com resposta compatível OpenAI
        """
        await self._ensure_client()

        if not self._client:
            return ChatCompletion.from_text(self._get_fallback_text(messages), model or self.model)

        try:
            # Extrair prompt e system prompt das mensagens
            system_prompt = None
            user_prompt = messages[-1].get("content", "")

            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content")
                    break

            response: LLMResponse = await self._client.generate(
                prompt=user_prompt, system_prompt=system_prompt
            )

            return ChatCompletion.from_response(response, model or self.model)

        except Exception as e:
            logger.warning("llm_generate_failed", error=str(e))
            return ChatCompletion.from_text(self._get_fallback_text(messages), model or self.model)

    def generate_sync(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> "ChatCompletion":
        """
        Gera resposta do LLM em modo síncrono.

        Args:
            messages: Lista de mensagens no formato OpenAI
            model: Nome do modelo (override)
            temperature: Temperatura de geração
            max_tokens: Máximo de tokens

        Returns:
            ChatCompletion com resposta compatível OpenAI
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Se já estamos em um loop async, criar uma nova task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.generate(messages, model, temperature, max_tokens),
                    )
                    return future.result()
            else:
                # Se não há loop rodando, executar diretamente
                return asyncio.run(self.generate(messages, model, temperature, max_tokens))
        except Exception as e:
            logger.warning("llm_generate_sync_failed", error=str(e))
            return ChatCompletion.from_text(self._get_fallback_text(messages), model or self.model)

    def _get_fallback_text(self, messages: list[dict[str, str]]) -> str:
        """Retorna resposta padrão quando LLM não disponível."""
        return '{"tables": []}'

    async def close(self):
        """Fecha o cliente LLM."""
        if self._client:
            self._client = None
            self._started = False


class ChatCompletion:
    """Wrapper para resposta compatível com OpenAI."""

    def __init__(
        self,
        choices: list["Choice"],
        model: str,
        usage: "Usage | None" = None,
    ):
        self.choices = choices
        self.model = model
        self.usage = usage

    @classmethod
    def from_response(cls, response: LLMResponse, model: str) -> "ChatCompletion":
        """Cria ChatCompletion a partir de LLMResponse."""
        choice = Choice(message={"role": "assistant", "content": response.text})
        usage = Usage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
        )
        return cls(choices=[choice], model=model, usage=usage)

    @classmethod
    def from_text(cls, text: str, model: str) -> "ChatCompletion":
        """Cria ChatCompletion a partir de texto."""
        choice = Choice(message={"role": "assistant", "content": text})
        return cls(choices=[choice], model=model, usage=None)


class Choice:
    """Wrapper para Choice do OpenAI."""

    def __init__(self, message: dict[str, str], finish_reason: str = "stop"):
        self.message = message
        self.finish_reason = finish_reason


class Usage:
    """Wrapper para Usage do OpenAI."""

    def __init__(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
