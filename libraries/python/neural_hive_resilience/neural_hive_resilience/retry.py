"""Retry policy with exponential backoff and jitter for Neural Hive-Mind.

Este módulo implementa políticas de retry com:
- Exponential backoff com jitter para evitar thundering herd
- Max attempts configurável
- Exception filtering
- Metrics Prometheus integradas
"""

import asyncio
import random
import time
from collections.abc import Callable, Coroutine
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Optional,
    TypeVar,
    Union,
)

import structlog
from prometheus_client import Counter, Histogram

from .exceptions import (
    MaxRetriesExceededError,
    NonRetryableError,
    RetryableError,
)

# Type variables
T = TypeVar("T")
F = TypeVar("F")


# Métricas Prometheus
retry_attempts_total = Counter(
    "retry_attempts_total",
    "Total number of retry attempts",
    ["service", "operation", "status"],
)
retry_duration_seconds = Histogram(
    "retry_duration_seconds",
    "Duration of retry operations",
    ["service", "operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


class BackoffStrategy(Enum):
    """Estratégias de backoff para retry."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"
    FIBONACCI = "fibonacci"


class RetryPolicy:
    """Configuração de política de retry.

    Attributes:
        max_attempts: Número máximo de tentativas (incluindo a primeira)
        base_delay: Delay base em segundos
        max_delay: Delay máximo em segundos
        backoff_strategy: Estratégia de backoff
        jitter_enabled: Habilita jitter para evitar thundering herd
        jitter_factor: Fator de jitter (0.0 a 1.0)
        retryable_exceptions: Exceções que devem ser retriadas
        non_retryable_exceptions: Exceções que NÃO devem ser retriadas
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 30.0,
        backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
        jitter_enabled: bool = True,
        jitter_factor: float = 0.1,
        retryable_exceptions: Optional[tuple[type[Exception], ...]] = None,
        non_retryable_exceptions: Optional[tuple[type[Exception], ...]] = None,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts deve ser >= 1")
        if base_delay < 0:
            raise ValueError("base_delay deve ser >= 0")
        if max_delay < base_delay:
            raise ValueError("max_delay deve ser >= base_delay")
        if not 0.0 <= jitter_factor <= 1.0:
            raise ValueError("jitter_factor deve estar entre 0.0 e 1.0")

        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_strategy = backoff_strategy
        self.jitter_enabled = jitter_enabled
        self.jitter_factor = jitter_factor
        self.retryable_exceptions = retryable_exceptions
        self.non_retryable_exceptions = non_retryable_exceptions
        self.logger = structlog.get_logger()

    def calculate_delay(self, attempt: int) -> float:
        """Calcula o delay para uma tentativa.

        Args:
            attempt: Número da tentativa (0-indexed)

        Returns:
            Delay em segundos
        """
        if attempt == 0:
            return 0

        delay: float

        if self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.backoff_strategy == BackoffStrategy.FIXED:
            delay = self.base_delay
        elif self.backoff_strategy == BackoffStrategy.FIBONACCI:
            delay = self.base_delay * self._fibonacci(attempt)
        else:
            delay = self.base_delay

        # Aplicar max_delay
        delay = min(delay, self.max_delay)

        # Aplicar jitter
        if self.jitter_enabled and delay > 0:
            jitter_range = delay * self.jitter_factor
            delay = delay - jitter_range + (2 * jitter_range * random.random())

        return max(0, delay)

    def _fibonacci(self, n: int) -> int:
        """Calcula o n-ésimo número de Fibonacci."""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b

    def should_retry(self, exception: Exception) -> bool:
        """Determina se uma exceção deve ser retriada.

        Args:
            exception: A exceção ocorrida

        Returns:
            True se deve retriar, False caso contrário
        """
        # Verificar non_retryable primeiro (prioridade alta)
        if self.non_retryable_exceptions:
            if isinstance(exception, self.non_retryable_exceptions):
                return False

        # Se a exceção é explicitamente NonRetryableError, não retriada
        if isinstance(exception, NonRetryableError):
            return False

        # Se a exceção é RetryableError, sempre retriada
        if isinstance(exception, RetryableError):
            return True

        # Verificar retryable_exceptions
        if self.retryable_exceptions:
            return isinstance(exception, self.retryable_exceptions)

        # Padrão: não retriada se nada configurado
        return False

    def get_retry_count(self, exception: Exception) -> int:
        """Retorna o número de tentativas baseado na exceção.

        Alguns erros podem justificar mais tentativas que outros.

        Args:
            exception: A exceção ocorrida

        Returns:
            Número de tentativas recomendado
        """
        if isinstance(exception, RetryableError):
            if hasattr(exception, "max_retry_count"):
                return min(exception.max_retry_count, self.max_attempts)

        return self.max_attempts


def retry(
    policy: Optional[RetryPolicy] = None,
    service_name: str = "unknown",
    operation_name: str = "unknown",
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> Callable[[F], F]:
    """Decorator para adicionar retry a funções síncronas e assíncronas.

    Args:
        policy: Política de retry (usa padrão se None)
        service_name: Nome do serviço para métricas
        operation_name: Nome da operação para métricas
        on_retry: Callback executado em cada retry

    Returns:
        Decorator configurado

    Example:
        ```python
        @retry(service_name="consensus-engine", operation_name="call_specialist")
        async def call_specialist(specialist_id: str):
            return await specialist.analyze(...)
        ```
    """

    if policy is None:
        policy = RetryPolicy()

    def decorator(func: F) -> F:
        operation = f"{service_name}:{operation_name}"

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exception: Optional[Exception] = None
                start_time = time.time()

                for attempt in range(policy.max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        # Verificar se deve retriada
                        if attempt == policy.max_attempts - 1:
                            retry_attempts_total.labels(
                                service=service_name,
                                operation=operation,
                                status="exhausted",
                            ).inc()
                            raise MaxRetriesExceededError(
                                f"Máximo de {policy.max_attempts} tentativas excedido",
                                operation=operation,
                                attempts=policy.max_attempts,
                                last_exception=last_exception,
                            ) from e

                        if not policy.should_retry(e):
                            retry_attempts_total.labels(
                                service=service_name,
                                operation=operation,
                                status="non_retryable",
                            ).inc()
                            raise

                        # Callback se fornecido
                        if on_retry:
                            on_retry(attempt + 1, e)

                        # Calcular delay e aguardar
                        delay = policy.calculate_delay(attempt + 1)
                        if delay > 0:
                            await asyncio.sleep(delay)

                        retry_attempts_total.labels(
                            service=service_name,
                            operation=operation,
                            status="retrying",
                        ).inc()
                        policy.logger.warning(
                            "retry_attempt",
                            service=service_name,
                            operation=operation,
                            attempt=attempt + 1,
                            max_attempts=policy.max_attempts,
                            delay=delay,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

                # Nunca deve chegar aqui, mas por segurança
                raise MaxRetriesExceededError(
                    "Máximo de tentativas excedido",
                    operation=operation,
                )

            return async_wrapper  # type: ignore

        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exception: Optional[Exception] = None
                start_time = time.time()

                for attempt in range(policy.max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e

                        # Verificar se deve retriada
                        if attempt == policy.max_attempts - 1:
                            retry_attempts_total.labels(
                                service=service_name,
                                operation=operation,
                                status="exhausted",
                            ).inc()
                            duration = time.time() - start_time
                            retry_duration_seconds.labels(
                                service=service_name,
                                operation=operation,
                            ).observe(duration)
                            raise MaxRetriesExceededError(
                                f"Máximo de {policy.max_attempts} tentativas excedido",
                                operation=operation,
                                attempts=policy.max_attempts,
                                last_exception=last_exception,
                            ) from e

                        if not policy.should_retry(e):
                            retry_attempts_total.labels(
                                service=service_name,
                                operation=operation,
                                status="non_retryable",
                            ).inc()
                            raise

                        # Callback se fornecido
                        if on_retry:
                            on_retry(attempt + 1, e)

                        # Calcular delay e aguardar
                        delay = policy.calculate_delay(attempt + 1)
                        if delay > 0:
                            time.sleep(delay)

                        retry_attempts_total.labels(
                            service=service_name,
                            operation=operation,
                            status="retrying",
                        ).inc()
                        policy.logger.warning(
                            "retry_attempt",
                            service=service_name,
                            operation=operation,
                            attempt=attempt + 1,
                            max_attempts=policy.max_attempts,
                            delay=delay,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

                # Nunca deve chegar aqui, mas por segurança
                raise MaxRetriesExceededError(
                    "Máximo de tentativas excedido",
                    operation=operation,
                )

            return sync_wrapper  # type: ignore

    return decorator


class RetryContext:
    """Context manager para retry com controle manual.

    Útil quando o decorator não é apropriado.

    Example:
        ```python
        async with RetryContext(policy) as ctx:
            result = await risky_operation()
        # Se falhar todas as tentativas, levanta MaxRetriesExceededError
        ```
    """

    def __init__(
        self,
        policy: Optional[RetryPolicy] = None,
        service_name: str = "unknown",
        operation_name: str = "manual",
    ):
        self.policy = policy or RetryPolicy()
        self.service_name = service_name
        self.operation_name = operation_name
        self.attempt_count = 0
        self.logger = structlog.get_logger()

    async def __aenter__(self) -> "RetryContext":
        self.attempt_count = 0
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False  # Não suprime exceções

    async def execute(
        self, coro_or_func: Union[Coroutine[Any, Any, T], Callable[..., Coroutine[Any, Any, T]]]
    ) -> T:
        """Executa uma coroutine com retry.

        Args:
            coro_or_func: Coroutine ou função que retorna coroutine

        Returns:
            Resultado da coroutine

        Raises:
            MaxRetriesExceededError: Se todas as tentativas falharem
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.policy.max_attempts):
            self.attempt_count = attempt + 1
            try:
                # Se for callable, chamar para obter coroutine
                if callable(coro_or_func):
                    coro = coro_or_func()
                else:
                    coro = coro_or_func
                return await coro
            except Exception as e:
                last_exception = e

                if attempt == self.policy.max_attempts - 1:
                    raise MaxRetriesExceededError(
                        f"Máximo de {self.policy.max_attempts} tentativas excedido",
                        operation=self.operation_name,
                        attempts=self.policy.max_attempts,
                        last_exception=last_exception,
                    ) from e

                if not self.policy.should_retry(e):
                    raise

                delay = self.policy.calculate_delay(attempt + 1)
                if delay > 0:
                    await asyncio.sleep(delay)

                self.logger.warning(
                    "retry_context_attempt",
                    service=self.service_name,
                    operation=self.operation_name,
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )

        raise MaxRetriesExceededError(
            "Máximo de tentativas excedido",
            operation=self.operation_name,
        )


# Exceções customizadas para retry
class RetryConfigError(ValueError):
    """Erro de configuração de política de retry."""

