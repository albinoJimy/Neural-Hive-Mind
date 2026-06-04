"""Cliente principal LLM com suporte a múltiplos provedores.

Implementa LLMClient com strategy pattern para seleção de provedores,
integração com resiliência, contagem de tokens e observabilidade.
"""

import asyncio
import time
from typing import Any, AsyncIterator

import structlog

from .circuit_breaker import create_llm_circuit_breaker
from .exceptions import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from .models import (
    LLMProvider,
    LLMResponse,
    LLMStreamChunk,
)
from .observability import OperationType, get_llm_tracer
from .resilience import LLMRetryPolicy, llm_retry
from .settings import get_llm_settings
from .token_counter import get_token_counter

logger = structlog.get_logger()


class LLMClient:
    """Cliente principal LLM com suporte a múltiplos provedores.

    Implementa interface unificada para OpenAI, Anthropic e provedores
    locais (Ollama), com retry automático, circuit breaker e observabilidade.

    Attributes:
        config: Configuração do cliente
        provider: Provedor LLM selecionado
        model: Nome do modelo em uso
    """

    # Mapeamento de modelos padrão por provedor
    DEFAULT_MODELS = {
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
        LLMProvider.LOCAL: "llama3",
    }

    def __init__(
        self,
        provider: LLMProvider | None = None,
        api_key: str | None = None,
        model: str | None = None,
        endpoint_url: str | None = None,
        settings: Any | None = None,
        service_name: str = "neural_hive_llm",
    ):
        """Inicializa cliente LLM.

        Args:
            provider: Provedor LLM (usa settings se None)
            api_key: Chave de API (usa settings se None)
            model: Nome do modelo (usa padrão se None)
            endpoint_url: URL customizada para local
            settings: Instância de LLMSettings
            service_name: Nome do serviço para observabilidade

        Raises:
            LLMConfigurationError: Se configuração inválida
        """
        # Carregar configurações
        if settings is None:
            settings = get_llm_settings()
            self._owns_settings = True
        else:
            self._owns_settings = False

        self.settings = settings
        self.service_name = service_name

        # Aplicar overrides se fornecidos
        self.provider = provider or self.settings.provider
        self.api_key = api_key or self.settings.api_key
        self.model = model or self.settings.model or self.DEFAULT_MODELS[self.provider]
        self.endpoint_url = endpoint_url or self.settings.endpoint_url

        # Validar configuração
        if self.provider != LLMProvider.LOCAL and not self.api_key:
            raise LLMConfigurationError(
                f"api_key é obrigatório para provider '{self.provider.value}'",
                parameter="api_key",
            )

        # Inicializar componentes
        self.logger = structlog.get_logger().bind(
            service=service_name,
            provider=self.provider.value,
            model=self.model,
        )

        # Retry policy
        self.retry_policy = LLMRetryPolicy(
            max_retries=self.settings.max_retries,
            base_delay=self.settings.base_delay,
            max_delay=self.settings.max_delay,
        )

        # Circuit breaker
        if self.settings.enable_circuit_breaker:
            self.circuit_breaker = create_llm_circuit_breaker(
                provider=self.provider.value,
                failure_threshold=self.settings.circuit_breaker_threshold,
                recovery_timeout=self.settings.circuit_breaker_timeout,
                service_name=service_name,
            )
        else:
            self.circuit_breaker = None

        # Token counter
        self.token_counter = get_token_counter(service_name=service_name)

        # Tracer
        if self.settings.enable_tracing:
            self.tracer = get_llm_tracer(service_name=service_name)
        else:
            self.tracer = None

        # Cliente HTTP (lazy init)
        self._http_client: Any = None
        self._provider_client: Any = None

        # Estado
        self._started = False

        self.logger.info(
            "llm_client_initialized",
            provider=self.provider.value,
            model=self.model,
            max_retries=self.settings.max_retries,
            circuit_breaker_enabled=self.circuit_breaker is not None,
        )

    async def start(self):
        """Inicializa cliente LLM.

        Cria conexões HTTP e inicializa clientes específicos
        do provedor.

        Raises:
            LLMConnectionError: Se falhar ao conectar
        """
        if self._started:
            return

        try:
            # Inicializar cliente HTTP
            if self.provider == LLMProvider.LOCAL:
                import httpx

                self._http_client = httpx.AsyncClient(
                    base_url=self.endpoint_url,
                    timeout=self.settings.timeout,
                )

            # Inicializar cliente específico do provedor
            await self._init_provider_client()

            self._started = True
            self.logger.info("llm_client_started")

        except Exception as e:
            raise LLMConnectionError(
                f"Failed to initialize LLM client: {e}",
                provider=self.provider.value,
                endpoint=self.endpoint_url,
            ) from e

    async def stop(self):
        """Fecha conexões e limpa recursos."""
        if not self._started:
            return

        # Fechar HTTP client
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        # Fechar cliente do provedor
        if self._provider_client:
            if hasattr(self._provider_client, "close"):
                close_fn = self._provider_client.close
                if asyncio.iscoroutinefunction(close_fn):
                    await close_fn()
                else:
                    close_fn()
            self._provider_client = None

        self._started = False
        self.logger.info("llm_client_stopped")

    async def _init_provider_client(self):
        """Inicializa cliente específico do provedor (lazy import)."""
        if self.provider == LLMProvider.OPENAI:
            try:
                from openai import AsyncOpenAI

                self._provider_client = AsyncOpenAI(api_key=self.api_key)
            except ImportError as e:
                raise LLMConfigurationError(
                    "OpenAI SDK não instalado. Instale com: pip install openai",
                    details={"error": str(e)},
                )

        elif self.provider == LLMProvider.ANTHROPIC:
            try:
                from anthropic import AsyncAnthropic

                self._provider_client = AsyncAnthropic(api_key=self.api_key)
            except ImportError as e:
                raise LLMConfigurationError(
                    "Anthropic SDK não instalado. Instale com: pip install anthropic",
                    details={"error": str(e)},
                )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs,
    ) -> LLMResponse:
        """Gera texto usando LLM.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema (opcional)
            temperature: Temperatura de amostragem (0.0-1.0)
            max_tokens: Máximo de tokens na resposta
            **kwargs: Parâmetros adicionais

        Returns:
            LLMResponse com texto gerado e metadados

        Raises:
            LLMError: Se erro na geração
        """
        if not self._started:
            await self.start()

        start_time = time.time()

        # Contexto de tracing
        if self.tracer:
            async with self.tracer.trace_generation(
                provider=self.provider.value,
                model=self.model,
                operation_type=OperationType.GENERATE,
                prompt=prompt,
            ) as span_ctx:
                result = await self._generate_with_retry(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    span_ctx=span_ctx,
                    **kwargs,
                )
        else:
            result = await self._generate_with_retry(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                span_ctx=None,
                **kwargs,
            )

        latency_ms = (time.time() - start_time) * 1000
        result.latency_ms = latency_ms

        return result

    @llm_retry(
        policy=None,  # Usará policy do self.retry_policy
        service_name="neural_hive_llm",
        operation_name="generate",
    )
    async def _generate_with_retry(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        span_ctx: Any | None,
        **kwargs,
    ) -> LLMResponse:
        """Executa geração com proteção de circuit breaker."""
        execute_fn = self._execute_generate

        if self.circuit_breaker:
            try:
                return await self.circuit_breaker.call(
                    execute_fn,
                    prompt,
                    system_prompt,
                    temperature,
                    max_tokens,
                    span_ctx,
                    **kwargs,
                )
            except Exception as e:
                if "CircuitBreakerOpenError" in type(e).__name__:
                    from .exceptions import LLMCircuitBreakerOpenError

                    raise LLMCircuitBreakerOpenError(
                        provider=self.provider.value,
                        recovery_timeout=self.circuit_breaker.recovery_timeout,
                    ) from e
                raise
        else:
            return await execute_fn(
                prompt,
                system_prompt,
                temperature,
                max_tokens,
                span_ctx,
                **kwargs,
            )

    async def _execute_generate(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        span_ctx: Any | None,
        **kwargs,
    ) -> LLMResponse:
        """Executa chamada ao provedor LLM."""
        try:
            if self.provider == LLMProvider.OPENAI:
                return await self._call_openai(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    span_ctx=span_ctx,
                )
            elif self.provider == LLMProvider.ANTHROPIC:
                return await self._call_anthropic(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    span_ctx=span_ctx,
                )
            else:  # LOCAL
                return await self._call_local(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    **kwargs,
                )

        except Exception as e:
            # Traduzir exceções do SDK para nossas exceções
            error_type = type(e).__name__

            if error_type == "RateLimitError" or "rate limit" in str(e).lower():
                if span_ctx:
                    span_ctx.set_error("rate_limit", str(e))
                raise LLMRateLimitError(
                    provider=self.provider.value,
                    model=self.model,
                    message=str(e),
                ) from e

            if "timeout" in str(e).lower():
                if span_ctx:
                    span_ctx.set_error("timeout", str(e))
                raise LLMTimeoutError(
                    provider=self.provider.value,
                    model=self.model,
                    timeout_seconds=self.settings.timeout,
                ) from e

            # Erro genérico
            if span_ctx:
                span_ctx.set_error("unknown", str(e))
            raise LLMProviderError(
                provider=self.provider.value,
                model=self.model,
                message=str(e),
            ) from e

    async def _call_openai(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        span_ctx: Any | None,
    ) -> LLMResponse:
        """Chama API OpenAI."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._provider_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        text = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        finish_reason = response.choices[0].finish_reason

        # Calcular custo
        cost_data = self.token_counter.calculate_cost(
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

        # Registrar uso
        self.token_counter.record_usage(
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

        if span_ctx:
            span_ctx.set_result(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            )

        return LLMResponse.from_provider_response(
            text=text or "",
            model=self.model,
            provider=LLMProvider.OPENAI,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_data[0],
            finish_reason=finish_reason,
        )

    async def _call_anthropic(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        span_ctx: Any | None,
    ) -> LLMResponse:
        """Chama API Anthropic."""
        message = await self._provider_client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )

        text = message.content[0].text
        prompt_tokens = message.usage.input_tokens
        completion_tokens = message.usage.output_tokens
        finish_reason = message.stop_reason

        # Calcular custo
        cost_data = self.token_counter.calculate_cost(
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

        # Registrar uso
        self.token_counter.record_usage(
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

        if span_ctx:
            span_ctx.set_result(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            )

        return LLMResponse.from_provider_response(
            text=text,
            model=self.model,
            provider=LLMProvider.ANTHROPIC,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_data[0],
            finish_reason=finish_reason,
        )

    async def _call_local(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        **kwargs,
    ) -> LLMResponse:
        """Chama API local (Ollama)."""
        full_prompt = f"{system_prompt or ''}\n\n{prompt}".strip()

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }

        response = await self._http_client.post("/generate", json=payload)
        response.raise_for_status()

        data = response.json()
        text = data.get("response", "")
        # Ollama não retorna contagem de tokens

        # Estimar tokens
        estimated_tokens = self.token_counter.estimate_tokens(text, self.model)

        return LLMResponse.from_provider_response(
            text=text,
            model=self.model,
            provider=LLMProvider.LOCAL,
            prompt_tokens=estimated_tokens // 2,  # Estimativa grosseira
            completion_tokens=estimated_tokens // 2,
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Gera texto com streaming.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema (opcional)
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens

        Yields:
            LLMStreamChunk com texto parcial

        Raises:
            LLMError: Se erro na geração
        """
        if not self._started:
            await self.start()

        if self.provider == LLMProvider.LOCAL:
            raise LLMError("Streaming não suportado para provedor local")

        try:
            if self.provider == LLMProvider.OPENAI:
                async for chunk in self._stream_openai(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk

            elif self.provider == LLMProvider.ANTHROPIC:
                async for chunk in self._stream_anthropic(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk

        except Exception as e:
            raise LLMProviderError(
                provider=self.provider.value,
                model=self.model,
                message=f"Streaming error: {e}",
            ) from e

    async def _stream_openai(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming para OpenAI."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        accumulated_text = ""

        stream = await self._provider_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                accumulated_text += delta
                yield LLMStreamChunk(
                    text=accumulated_text,
                    delta=delta,
                    is_final=False,
                )

        # Chunk final
        yield LLMStreamChunk(
            text=accumulated_text,
            delta="",
            is_final=True,
            finish_reason="stop",
        )

    async def _stream_anthropic(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Streaming para Anthropic."""
        accumulated_text = ""

        async with self._provider_client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                accumulated_text += text
                yield LLMStreamChunk(
                    text=accumulated_text,
                    delta=text,
                    is_final=False,
                )

        yield LLMStreamChunk(
            text=accumulated_text,
            delta="",
            is_final=True,
            finish_reason="stop",
        )

    async def generate_batch(
        self,
        prompts: list[str],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> list[LLMResponse]:
        """Gera texto para múltiplos prompts em paralelo.

        Args:
            prompts: Lista de prompts
            system_prompt: Prompt de sistema compartilhado
            temperature: Temperatura de amostragem
            max_tokens: Máximo de tokens

        Returns:
            Lista de LLMResponse na mesma ordem dos prompts

        Raises:
            LLMError: Se erro em qualquer geração
        """
        if not self._started:
            await self.start()

        tasks = [
            self.generate(
                prompt=p,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for p in prompts
        ]

        return await asyncio.gather(*tasks)

    def __repr__(self) -> str:
        return (
            f"LLMClient(provider={self.provider.value}, "
            f"model={self.model}, started={self._started})"
        )


__all__ = [
    "LLMClient",
]
