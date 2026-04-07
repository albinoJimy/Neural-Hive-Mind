"""Timeout decorators and utilities for Neural Hive-Mind.

Este módulo implementa mecanismos de timeout para operações assíncronas:
- Timeout decorator com cancelamento gracioso
- Timeout com fallback
- Timeout com retry
"""

import asyncio
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    TypeVar,
    Union,
)
from prometheus_client import Counter, Histogram
import structlog

from .exceptions import TimeoutError as ResilienceTimeoutError


# Type variables
T = TypeVar("T")
F = TypeVar("F", bound=Union[Callable[..., T], Callable[..., Awaitable[T]]])


# Métricas Prometheus
timeout_operations_total = Counter(
    "timeout_operations_total",
    "Total number of operations with timeout",
    ["service", "operation", "status"],
)
timeout_duration_seconds = Histogram(
    "timeout_duration_seconds",
    "Duration of operations before timeout",
    ["service", "operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)


async def _wait_with_timeout(
    coro: Awaitable[T],
    timeout: float,
    service_name: str,
    operation_name: str,
) -> T:
    """Executa uma coroutine com timeout.

    Args:
        coro: Coroutine a executar
        timeout: Timeout em segundos
        service_name: Nome do serviço para métricas
        operation_name: Nome da operação para métricas

    Returns:
        Resultado da coroutine

    Raises:
        ResilienceTimeoutError: Se o timeout for excedido
    """
    operation = f"{service_name}:{operation_name}"
    start_time = asyncio.get_event_loop().time()

    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        elapsed = asyncio.get_event_loop().time() - start_time

        timeout_duration_seconds.labels(
            service=service_name,
            operation=operation,
        ).observe(elapsed)

        timeout_operations_total.labels(
            service=service_name,
            operation=operation,
            status="completed",
        ).inc()

        return result

    except asyncio.TimeoutError:
        elapsed = asyncio.get_event_loop().time() - start_time

        timeout_duration_seconds.labels(
            service=service_name,
            operation=operation,
        ).observe(elapsed)

        timeout_operations_total.labels(
            service=service_name,
            operation=operation,
            status="timeout",
        ).inc()

        raise ResilienceTimeoutError(
            f"Operação '{operation}' excedeu timeout de {timeout}s",
            service=service_name,
            timeout_seconds=timeout,
        )


def timeout(
    timeout_seconds: float,
    service_name: str = "unknown",
    operation_name: str = "unknown",
) -> Callable[[F], F]:
    """Decorator para adicionar timeout a funções assíncronas.

    Args:
        timeout_seconds: Timeout em segundos
        service_name: Nome do serviço para métricas
        operation_name: Nome da operação para métricas

    Returns:
        Decorator configurado

    Example:
        ```python
        @timeout(timeout_seconds=5.0, service_name="consensus-engine", operation_name="merge_opinions")
        async def merge_opinions(opinions: list[Opinion]):
            return await consensus_service.merge(opinions)
        ```
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds deve ser > 0")

    def decorator(func: F) -> F:
        op_name = operation_name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _wait_with_timeout(
                    func(*args, **kwargs),
                    timeout=timeout_seconds,
                    service_name=service_name,
                    operation_name=op_name,
                )

            return async_wrapper  # type: ignore
        else:
            raise TypeError(
                f"@timeout decorator só suporta funções assíncronas, "
                f"{func.__name__} não é assíncrona"
            )

    return decorator


class TimeoutContext:
    """Context manager para timeout com controle manual.

    Útil quando o decorator não é apropriado ou para operações complexas.

    Example:
        ```python
        async with TimeoutContext(timeout_seconds=10.0, service_name="orchestrator") as ctx:
            result = await long_running_operation()
        ```
    """

    def __init__(
        self,
        timeout_seconds: float,
        service_name: str = "unknown",
        operation_name: str = "manual",
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser > 0")

        self.timeout_seconds = timeout_seconds
        self.service_name = service_name
        self.operation_name = operation_name
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "TimeoutContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return False

    async def execute(self, coro: Awaitable[T]) -> T:
        """Executa uma coroutine com timeout.

        Args:
            coro: Coroutine a executar

        Returns:
            Resultado da coroutine

        Raises:
            ResilienceTimeoutError: Se o timeout for excedido
        """
        self._task = asyncio.create_task(coro)
        return await _wait_with_timeout(
            self._task,
            timeout=self.timeout_seconds,
            service_name=self.service_name,
            operation_name=self.operation_name,
        )


class TimeoutWithFallback:
    """Timeout com fallback automático em caso de timeout.

    Executa uma função fallback se a operação principal exceder o timeout.

    Example:
        ```python
        async def fallback_opinions(opinions):
            return Opinion.merge_safe(opinions)

        timeout_fallback = TimeoutWithFallback(
            timeout_seconds=5.0,
            fallback_func=fallback_opinions,
            service_name="consensus-engine",
        )

        result = await timeout_fallback.execute(merge_opinions(opinions))
        ```
    """

    def __init__(
        self,
        timeout_seconds: float,
        fallback_func: Callable[..., Awaitable[Any]],
        service_name: str = "unknown",
        operation_name: str = "timeout_with_fallback",
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser > 0")

        self.timeout_seconds = timeout_seconds
        self.fallback_func = fallback_func
        self.service_name = service_name
        self.operation_name = operation_name
        self.logger = structlog.get_logger()

    async def execute(self, coro: Awaitable[T], *args: Any, **kwargs: Any) -> Any:
        """Executa coroutine com fallback em timeout.

        Args:
            coro: Coroutine principal a executar
            *args: Argumentos para o fallback
            **kwargs: Argumentos para o fallback

        Returns:
            Resultado da coroutine principal ou do fallback
        """
        try:
            return await _wait_with_timeout(
                coro,
                timeout=self.timeout_seconds,
                service_name=self.service_name,
                operation_name=self.operation_name,
            )
        except ResilienceTimeoutError as e:
            self.logger.warning(
                "timeout_fallback_triggered",
                service=self.service_name,
                operation=self.operation_name,
                timeout_seconds=self.timeout_seconds,
            )
            return await self.fallback_func(*args, **kwargs)


def timeout_with_fallback(
    timeout_seconds: float,
    fallback_func: Callable[..., Awaitable[Any]],
    service_name: str = "unknown",
    operation_name: str = "unknown",
) -> Callable[[F], F]:
    """Decorator para timeout com fallback.

    Args:
        timeout_seconds: Timeout em segundos
        fallback_func: Função fallback assíncrona
        service_name: Nome do serviço
        operation_name: Nome da operação

    Returns:
        Decorator configurado

    Example:
        ```python
        async def safe_merge(opinions):
            return Opinion.merge_safe(opinions)

        @timeout_with_fallback(
            timeout_seconds=5.0,
            fallback_func=safe_merge,
            service_name="consensus-engine",
        )
        async def merge_opinions(opinions):
            return await consensus_service.merge(opinions)
        ```
    """

    def decorator(func: F) -> F:
        op_name = operation_name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await _wait_with_timeout(
                        func(*args, **kwargs),
                        timeout=timeout_seconds,
                        service_name=service_name,
                        operation_name=op_name,
                    )
                except ResilienceTimeoutError:
                    logger = structlog.get_logger()
                    logger.warning(
                        "timeout_fallback_triggered",
                        service=service_name,
                        operation=op_name,
                        timeout_seconds=timeout_seconds,
                    )
                    return await fallback_func(*args, **kwargs)

            return async_wrapper  # type: ignore
        else:
            raise TypeError(f"@timeout_with_fallback decorator só suporta funções assíncronas")

    return decorator
