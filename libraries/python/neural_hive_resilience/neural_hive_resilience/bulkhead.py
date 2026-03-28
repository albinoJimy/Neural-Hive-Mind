"""Bulkhead pattern implementation for Neural Hive-Mind.

O padrão Bulkhead isola recursos para evitar que falhas em um componente
afetem outros componentes. Similar aos compartimentos à prova d'água
de navios (bulkheads).

Este módulo implementa:
- Semaphore-based bulkhead: Limita concorrência
- Thread pool isolation: Isola em threads separadas
- Queue-based bulkhead: Fila com tamanho limitado
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, TypeVar
from prometheus_client import Counter, Gauge, Histogram
import structlog

from .exceptions import BulkheadRejectedError


# Type variables
T = TypeVar("T")


# Métricas Prometheus
bulkhead_requests_total = Counter(
    "bulkhead_requests_total",
    "Total number of bulkhead requests",
    ["service", "bulkhead", "status"],
)
bulkhead_queue_size = Gauge(
    "bulkhead_queue_size",
    "Current size of bulkhead queue",
    ["service", "bulkhead"],
)
bulkhead_active_tasks = Gauge(
    "bulkhead_active_tasks",
    "Current number of active tasks in bulkhead",
    ["service", "bulkhead"],
)
bulkhead_execution_duration_seconds = Histogram(
    "bulkhead_execution_duration_seconds",
    "Duration of bulkhead task execution",
    ["service", "bulkhead"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
)


class BulkheadStrategy(Enum):
    """Estratégias de isolamento bulkhead."""

    SEMAPHORE = "semaphore"
    THREAD_POOL = "thread_pool"
    QUEUE = "queue"


@dataclass
class BulkheadConfig:
    """Configuração do bulkhead.

    Attributes:
        max_concurrent: Número máximo de operações concorrentes
        max_queue_size: Tamanho máximo da fila (0 = sem fila)
        timeout: Timeout para esperar na fila (None = infinito)
    """

    max_concurrent: int = 10
    max_queue_size: int = 5
    timeout: Optional[float] = None


class SemaphoreBulkhead:
    """Bulkhead baseado em semáforo.

    Limita o número de operações simultâneas usando asyncio.Semaphore.
    Operações adicionais são bloqueadas ou rejeitadas baseado na configuração.

    Example:
        ```python
        bulkhead = SemaphoreBulkhead(
            service_name="consensus-engine",
            bulkhead_name="specialist_calls",
            max_concurrent=5,
            max_queue_size=10,
        )

        async with bulkhead:
            result = await specialist.analyze(data)
        ```
    """

    def __init__(
        self,
        service_name: str,
        bulkhead_name: str,
        config: BulkheadConfig,
    ):
        if config.max_concurrent <= 0:
            raise ValueError("max_concurrent deve ser > 0")

        self.service_name = service_name
        self.bulkhead_name = bulkhead_name
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent)
        self.queue = asyncio.Queue(maxsize=config.max_queue_size) if config.max_queue_size > 0 else None
        self.logger = structlog.get_logger()
        self._active_count = 0

    @property
    def active_count(self) -> int:
        """Número de tarefas atualmente ativas."""
        return self._active_count

    async def acquire(self) -> bool:
        """Tenta adquirir permissão para executar.

        Returns:
            True se permitido, False se rejeitado

        Raises:
            BulkheadRejectedError: Se fila cheia e timeout excedido
        """
        if self.queue is None:
            # Sem fila: tentar adquirir diretamente
            acquired = await self.semaphore.acquire()
            if acquired:
                self._active_count += 1
                bulkhead_active_tasks.labels(
                    service=self.service_name,
                    bulkhead=self.bulkhead_name,
                ).set(self._active_count)
            return acquired

        # Com fila: tentar colocar na fila
        try:
            if self.config.timeout:
                await asyncio.wait_for(
                    self.queue.put(None),
                    timeout=self.config.timeout,
                )
            else:
                await self.queue.put(None)

            bulkhead_queue_size.labels(
                service=self.service_name,
                bulkhead=self.bulkhead_name,
            ).set(self.queue.qsize())

            await self.semaphore.acquire()
            await self.queue.get()
            self.queue.task_done()

            self._active_count += 1
            bulkhead_active_tasks.labels(
                service=self.service_name,
                bulkhead=self.bulkhead_name,
            ).set(self._active_count)

            return True

        except asyncio.TimeoutError:
            raise BulkheadRejectedError(
                f"Bulkhead '{self.bulkhead_name}' rejeitou: fila cheia e timeout excedido",
                service=self.service_name,
                max_concurrent=self.config.max_concurrent,
                current_active=self._active_count,
                queue_size=self.config.max_queue_size,
            )

    def release(self) -> None:
        """Libera permissão após execução."""
        self._active_count -= 1
        self.semaphore.release()

        bulkhead_active_tasks.labels(
            service=self.service_name,
            bulkhead=self.bulkhead_name,
        ).set(self._active_count)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

    async def execute(
        self,
        coro: Awaitable[T],
    ) -> T:
        """Executa coroutine com isolamento bulkhead.

        Args:
            coro: Coroutine a executar

        Returns:
            Resultado da coroutine

        Raises:
            BulkheadRejectedError: Se rejeitado pelo bulkhead
        """
        async with self:
            start_time = asyncio.get_event_loop().time()

            try:
                result = await coro

                elapsed = asyncio.get_event_loop().time() - start_time
                bulkhead_execution_duration_seconds.labels(
                    service=self.service_name,
                    bulkhead=self.bulkhead_name,
                ).observe(elapsed)

                bulkhead_requests_total.labels(
                    service=self.service_name,
                    bulkhead=self.bulkhead_name,
                    status="success",
                ).inc()

                return result

            except Exception as e:
                elapsed = asyncio.get_event_loop().time() - start_time
                bulkhead_execution_duration_seconds.labels(
                    service=self.service_name,
                    bulkhead=self.bulkhead_name,
                ).observe(elapsed)

                bulkhead_requests_total.labels(
                    service=self.service_name,
                    bulkhead=self.bulkhead_name,
                    status="error",
                ).inc()

                raise


class ThreadPoolBulkhead:
    """Bulkhead baseado em thread pool.

    Isola operações bloqueantes em threads separadas para não
    bloquear o event loop.

    Example:
        ```python
        bulkhead = ThreadPoolBulkhead(
            service_name="orchestrator",
            bulkhead_name="db_operations",
            max_workers=5,
        )

        # Executar operação bloqueante em thread separada
        result = await bulkhead.run_in_thread(blocking_db_call, arg1, arg2)
        ```
    """

    def __init__(
        self,
        service_name: str,
        bulkhead_name: str,
        max_workers: int = 5,
    ):
        if max_workers <= 0:
            raise ValueError("max_workers deve ser > 0")

        self.service_name = service_name
        self.bulkhead_name = bulkhead_name
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.logger = structlog.get_logger()
        self._active_count = 0

    @property
    def active_count(self) -> int:
        """Número de tarefas atualmente ativas."""
        return self._active_count

    async def run_in_thread(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Executa função síncrona em thread separada.

        Args:
            func: Função a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função
        """
        loop = asyncio.get_event_loop()
        self._active_count += 1

        bulkhead_active_tasks.labels(
            service=self.service_name,
            bulkhead=self.bulkhead_name,
        ).set(self._active_count)

        start_time = asyncio.get_event_loop().time()

        try:
            result = await loop.run_in_executor(
                self.executor,
                lambda: func(*args, **kwargs),
            )

            elapsed = asyncio.get_event_loop().time() - start_time
            bulkhead_execution_duration_seconds.labels(
                service=self.service_name,
                bulkhead=self.bulkhead_name,
            ).observe(elapsed)

            bulkhead_requests_total.labels(
                service=self.service_name,
                bulkhead=self.bulkhead_name,
                status="success",
            ).inc()

            return result

        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start_time
            bulkhead_execution_duration_seconds.labels(
                service=self.service_name,
                bulkhead=self.bulkhead_name,
            ).observe(elapsed)

            bulkhead_requests_total.labels(
                service=self.service_name,
                bulkhead=self.bulkhead_name,
                status="error",
            ).inc()

            raise

        finally:
            self._active_count -= 1

    def shutdown(self, wait: bool = True) -> None:
        """Desliga o thread pool.

        Args:
            wait: Aguardar tarefas pendentes completarem
        """
        self.executor.shutdown(wait=wait)


class BulkheadFactory:
    """Factory para criar bulkheads configurados.

    Example:
        ```python
        factory = BulkheadFactory(service_name="consensus-engine")

        # Bulkhead para chamadas de especialistas
        specialist_bulkhead = factory.semaphore(
            name="specialist_calls",
            max_concurrent=10,
            max_queue_size=5,
        )

        # Bulkhead para operações de DB (bloqueantes)
        db_bulkhead = factory.thread_pool(
            name="db_operations",
            max_workers=5,
        )
        ```
    """

    def __init__(self, service_name: str):
        self.service_name = service_name

    def semaphore(
        self,
        name: str,
        max_concurrent: int = 10,
        max_queue_size: int = 5,
        timeout: Optional[float] = None,
    ) -> SemaphoreBulkhead:
        """Cria um Semaphore Bulkhead."""
        config = BulkheadConfig(
            max_concurrent=max_concurrent,
            max_queue_size=max_queue_size,
            timeout=timeout,
        )
        return SemaphoreBulkhead(
            service_name=self.service_name,
            bulkhead_name=name,
            config=config,
        )

    def thread_pool(
        self,
        name: str,
        max_workers: int = 5,
    ) -> ThreadPoolBulkhead:
        """Cria um Thread Pool Bulkhead."""
        return ThreadPoolBulkhead(
            service_name=self.service_name,
            bulkhead_name=name,
            max_workers=max_workers,
        )


def bulkhead(
    bulkhead_name: str = "default",
    max_concurrent: int = 10,
    max_queue_size: int = 5,
    service_name: str = "unknown",
):
    """Decorator para adicionar isolamento bulkhead a funções assíncronas.

    Args:
        bulkhead_name: Nome identificador do bulkhead
        max_concurrent: Máximo de operações concorrentes
        max_queue_size: Tamanho máximo da fila
        service_name: Nome do serviço para métricas

    Returns:
        Decorator configurado

    Example:
        ```python
        @bulkhead(
            bulkhead_name="specialist_calls",
            max_concurrent=5,
            service_name="consensus-engine",
        )
        async def call_specialist(specialist_id: str, data: dict):
            return await specialist.analyze(data)
        ```
    """
    _bulkhead: Optional[SemaphoreBulkhead] = None

    def decorator(func):
        nonlocal _bulkhead

        if _bulkhead is None:
            config = BulkheadConfig(
                max_concurrent=max_concurrent,
                max_queue_size=max_queue_size,
            )
            _bulkhead = SemaphoreBulkhead(
                service_name=service_name,
                bulkhead_name=bulkhead_name,
                config=config,
            )

        if asyncio.iscoroutinefunction(func):

            async def wrapper(*args, **kwargs):
                return await _bulkhead.execute(func(*args, **kwargs))

            return wrapper
        else:
            raise TypeError(
                f"@bulkhead decorator só suporta funções assíncronas"
            )

    return decorator
