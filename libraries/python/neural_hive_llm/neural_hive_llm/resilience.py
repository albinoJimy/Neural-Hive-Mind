"""Módulo de resiliência para clientes LLM.

Implementa lógica de retry com exponential backoff usando tenacity,
configurado especificamente para operações LLM (rate limits, timeouts, 5xx).
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import structlog
from tenacity import (
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from neural_hive_resilience import (
    CircuitBreakerOpenError as ResilienceCircuitBreakerOpenError,
)

# Type variables
P = ParamSpec("P")
T = TypeVar("T")

logger = structlog.get_logger()


# Exceções específicas de LLM que devem ser retriadas
class LLMRateLimitError(Exception):
    """Erro de rate limit do provedor LLM."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after  # Segundos sugeridos para retry


class LLMTimeoutError(Exception):
    """Erro de timeout na requisição LLM."""


class LLMServerError(Exception):
    """Erro de servidor (5xx) do provedor LLM."""


def _is_retryable_llm_error(exc: Exception) -> bool:
    """Determina se uma exceção LLM deve ser retriada.

    Args:
        exc: Exceção ocorrida

    Returns:
        True se deve retriada, False caso contrário
    """
    # Rate limit errors - sempre retriável
    if isinstance(exc, LLMRateLimitError):
        return True

    # Timeout - retriável (pode ser transitório)
    if isinstance(exc, LLMTimeoutError):
        return True

    # Server errors (5xx) - retriável
    if isinstance(exc, LLMServerError):
        return True

    # Verificar exceções de SDKs externos
    exc_name = exc.__class__.__name__

    # OpenAI SDK
    if exc_name == "RateLimitError":
        return True
    if exc_name == "APITimeoutError":
        return True
    if exc_name == "APIConnectionError":
        return True
    if exc_name == "APIError" and hasattr(exc, "status_code"):
        # Retriar 5xx
        status = getattr(exc, "status_code", 0)
        return 500 <= status < 600

    # Anthropic SDK
    if exc_name == "RateLimitError":
        return True
    if exc_name == "APITimeoutError":
        return True
    if exc_name == "APIConnectionError":
        return True
    if exc_name == "APIError" and hasattr(exc, "status"):
        status = getattr(exc, "status", 0)
        return 500 <= status < 600

    # httpx (HTTP client)
    if exc_name in ("ReadTimeout", "WriteTimeout", "ConnectTimeout", "ConnectError"):
        return True

    # Circuit breaker aberto - não retriar aqui (deixar o handler tratar)
    if isinstance(exc, ResilienceCircuitBreakerOpenError):
        return False

    return False


class LLMRetryPolicy:
    """Política de retry para operações LLM.

    Configura o comportamento de retry com base no tipo de erro
    e características de provedores LLM.

    Attributes:
        max_retries: Número máximo de tentativas de retry
        base_delay: Delay base em segundos para exponential backoff
        max_delay: Delay máximo em segundos
        jitter_enabled: Habilita jitter para evitar thundering herd
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter_enabled: bool = True,
    ):
        """Inicializa política de retry.

        Args:
            max_retries: Número máximo de retries (padrão: 3)
            base_delay: Delay base em segundos (padrão: 1.0)
            max_delay: Delay máximo em segundos (padrão: 60.0)
            jitter_enabled: Habilitar jitter (padrão: True)
        """
        if max_retries < 0:
            raise ValueError("max_retries deve ser >= 0")
        if base_delay < 0:
            raise ValueError("base_delay deve ser >= 0")
        if max_delay < base_delay:
            raise ValueError("max_delay deve ser >= base_delay")

        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_enabled = jitter_enabled
        self.logger = structlog.get_logger()


# Decorator de retry simplificado para LLMs
def llm_retry(
    policy: LLMRetryPolicy | None = None,
    service_name: str = "neural_hive_llm",
    operation_name: str = "generate",
):
    """Decorator que adiciona retry com exponential backoff para operações LLM.

    Args:
        policy: Política de retry (usa padrão se None)
        service_name: Nome do serviço para logs
        operation_name: Nome da operação para logs

    Returns:
        Decorator configurado

    Example:
        ```python
        @llm_retry(service_name="code-forge", operation_name="generate_code")
        async def call_openai(prompt: str) -> str:
            return await openai_client.generate(prompt)
        ```
    """

    if policy is None:
        policy = LLMRetryPolicy()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Para funções assíncronas
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_exception: Exception | None = None

                for attempt in range(policy.max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        # Última tentativa falhou
                        if attempt >= policy.max_retries:
                            policy.logger.error(
                                "llm_retry_exhausted",
                                service=service_name,
                                operation=operation_name,
                                max_attempts=policy.max_retries + 1,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                            raise

                        # Verificar se deve retriada
                        if not _is_retryable_llm_error(e):
                            policy.logger.warning(
                                "llm_non_retryable_error",
                                service=service_name,
                                operation=operation_name,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                            raise

                        # Calcular delay com exponential backoff
                        import random

                        delay = min(
                            policy.base_delay * (2**attempt),
                            policy.max_delay,
                        )

                        # Adicionar jitter se habilitado
                        if policy.jitter_enabled:
                            jitter = delay * 0.1  # 10% jitter
                            delay = delay - jitter + (2 * jitter * random.random())

                        # Log da tentativa de retry
                        policy.logger.warning(
                            "llm_retry_attempt",
                            service=service_name,
                            operation=operation_name,
                            attempt=attempt + 1,
                            max_attempts=policy.max_retries + 1,
                            delay_seconds=delay,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

                        # Aguardar antes da próxima tentativa
                        await asyncio.sleep(delay)

                # Nunca deve chegar aqui
                raise RuntimeError("Estado inválido no loop de retry") from last_exception

            return async_wrapper  # type: ignore

        # Para funções síncronas
        else:

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                import time

                last_exception: Exception | None = None

                for attempt in range(policy.max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        # Última tentativa falhou
                        if attempt >= policy.max_retries:
                            policy.logger.error(
                                "llm_retry_exhausted",
                                service=service_name,
                                operation=operation_name,
                                max_attempts=policy.max_retries + 1,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                            raise

                        # Verificar se deve retriada
                        if not _is_retryable_llm_error(e):
                            policy.logger.warning(
                                "llm_non_retryable_error",
                                service=service_name,
                                operation=operation_name,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                            raise

                        # Calcular delay
                        import random

                        delay = min(
                            policy.base_delay * (2**attempt),
                            policy.max_delay,
                        )

                        if policy.jitter_enabled:
                            jitter = delay * 0.1
                            delay = delay - jitter + (2 * jitter * random.random())

                        policy.logger.warning(
                            "llm_retry_attempt",
                            service=service_name,
                            operation=operation_name,
                            attempt=attempt + 1,
                            max_attempts=policy.max_retries + 1,
                            delay_seconds=delay,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

                        time.sleep(delay)

                raise RuntimeError("Estado inválido no loop de retry") from last_exception

            return sync_wrapper  # type: ignore

    return decorator


__all__ = [
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMServerError",
    "LLMRetryPolicy",
    "llm_retry",
    "_is_retryable_llm_error",
]
