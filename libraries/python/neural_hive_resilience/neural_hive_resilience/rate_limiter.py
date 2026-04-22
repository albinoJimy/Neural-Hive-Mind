"""Rate limiting implementations for Neural Hive-Mind.

Este módulo implementa algoritmos de rate limiting:
- Token Bucket: Permite bursts controlados
- Sliding Window Log: Preciso mas consome mais memória
- Sliding Window Counter: Balance entre precisão e memória
- Fixed Window: Simples mas pode permitir bursts nas bordas
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

from .exceptions import ConcurrencyLimitExceededError, RateLimitExceededError

# Métricas Prometheus
rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total number of rate limit checks",
    ["service", "limiter", "status"],
)
rate_limit_wait_duration_seconds = Histogram(
    "rate_limit_wait_duration_seconds",
    "Duration waiting for rate limit token",
    ["service", "limiter"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)
concurrent_requests = Gauge(
    "resilience_concurrent_requests",
    "Current number of concurrent requests",
    ["service", "limiter"],
)


class RateLimitAlgorithm(Enum):
    """Algoritmos de rate limiting disponíveis."""

    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitResult:
    """Resultado de uma verificação de rate limit.

    Attributes:
        allowed: Se a requisição é permitida
        tokens_remaining: Tokens restantes no bucket/janela
        retry_after: Segundos até a próxima requisição ser permitida
        reset_time: Timestamp quando o limite será resetado
    """

    allowed: bool
    tokens_remaining: int
    retry_after: float
    reset_time: float


class TokenBucketRateLimiter:
    """Rate limiter usando algoritmo Token Bucket.

    Permite bursts controlados enquanto mantém uma taxa média.
    Adequado para APIs que precisam lidar com picos temporários.

    Attributes:
        capacity: Número máximo de tokens no bucket
        refill_rate: Taxa de reabastecimento (tokens/segundo)
        tokens: Tokens atualmente disponíveis
        last_refill: Último timestamp de reabastecimento
    """

    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        service_name: str = "unknown",
        limiter_name: str = "token_bucket",
    ):
        if capacity <= 0:
            raise ValueError("capacity deve ser > 0")
        if refill_rate <= 0:
            raise ValueError("refill_rate deve ser > 0")

        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self.service_name = service_name
        self.limiter_name = limiter_name
        self.logger = structlog.get_logger()

        # Lock para thread-safety em operações assíncronas
        self._lock = asyncio.Lock()

    async def _refill(self) -> None:
        """Reabastece tokens baseado no tempo decorrido."""
        now = time.monotonic()
        elapsed = now - self.last_refill

        if elapsed > 0:
            new_tokens = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now

    async def acquire(
        self, tokens: int = 1, block: bool = True, timeout: Optional[float] = None
    ) -> RateLimitResult:
        """Adquire tokens do bucket.

        Args:
            tokens: Número de tokens a adquirir
            block: Se deve aguardar tokens ficarem disponíveis
            timeout: Tempo máximo de espera (None = infinito)

        Returns:
            RateLimitResult com status da requisição

        Raises:
            RateLimitExceededError: Se não há tokens disponíveis e block=False
        """
        async with self._lock:
            await self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                rate_limit_requests_total.labels(
                    service=self.service_name,
                    limiter=self.limiter_name,
                    status="allowed",
                ).inc()
                return RateLimitResult(
                    allowed=True,
                    tokens_remaining=int(self.tokens),
                    retry_after=0.0,
                    reset_time=self.last_refill + (self.capacity - self.tokens) / self.refill_rate,
                )

            # Não há tokens suficientes
            wait_time = (tokens - self.tokens) / self.refill_rate

            if not block:
                rate_limit_requests_total.labels(
                    service=self.service_name,
                    limiter=self.limiter_name,
                    status="denied",
                ).inc()
                raise RateLimitExceededError(
                    f"Rate limit excedido: {tokens} tokens solicitados, {int(self.tokens)} disponíveis",
                    service=self.service_name,
                    limit=self.capacity,
                    window_seconds=self.capacity / self.refill_rate,
                    retry_after=wait_time,
                )

        # Aguarda se block=True
        start_wait = time.monotonic()
        deadline = start_wait + timeout if timeout else None

        while True:
            await asyncio.sleep(0.01)  # Pequeno sleep para não sobrecarregar CPU

            async with self._lock:
                await self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    wait_duration = time.monotonic() - start_wait
                    rate_limit_wait_duration_seconds.labels(
                        service=self.service_name,
                        limiter=self.limiter_name,
                    ).observe(wait_duration)
                    return RateLimitResult(
                        allowed=True,
                        tokens_remaining=int(self.tokens),
                        retry_after=0.0,
                        reset_time=self.last_refill,
                    )

                if deadline and time.monotonic() >= deadline:
                    raise RateLimitExceededError(
                        f"Timeout aguardando tokens: {tokens} tokens solicitados",
                        service=self.service_name,
                        limit=self.capacity,
                        window_seconds=self.capacity / self.refill_rate,
                        retry_after=(tokens - self.tokens) / self.refill_rate,
                    )

    async def reserve(self, tokens: int = 1) -> float:
        """Reserva tokens e retorna o tempo de espera.

        Similar ao acquire mas retorna apenas o tempo de espera.
        Útil para implementar graceful degradation.

        Args:
            tokens: Número de tokens a reservar

        Returns:
            Tempo de espera em segundos
        """
        async with self._lock:
            await self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            wait_time = (tokens - self.tokens) / self.refill_rate
            self.tokens = 0
            return wait_time


class SlidingWindowLogRateLimiter:
    """Rate limiter usando Sliding Window Log.

    Implementação precisa que mantém log de timestamps.
    Consome mais memória mas não permite bursts nas bordas da janela.

    Attributes:
        limit: Número máximo de requisições permitidas
        window_seconds: Tamanho da janela em segundos
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        service_name: str = "unknown",
        limiter_name: str = "sliding_window_log",
    ):
        if limit <= 0:
            raise ValueError("limit deve ser > 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds deve ser > 0")

        self.limit = limit
        self.window_seconds = window_seconds
        self.request_times: deque = deque()
        self.service_name = service_name
        self.limiter_name = limiter_name
        self.logger = structlog.get_logger()
        self._lock = asyncio.Lock()

    async def _clean_old_requests(self, now: float) -> None:
        """Remove timestamps fora da janela."""
        cutoff = now - self.window_seconds
        while self.request_times and self.request_times[0] <= cutoff:
            self.request_times.popleft()

    async def check(self) -> RateLimitResult:
        """Verifica se uma requisição é permitida.

        Returns:
            RateLimitResult com status da verificação
        """
        async with self._lock:
            now = time.monotonic()
            await self._clean_old_requests(now)

            allowed = len(self.request_times) < self.limit

            if allowed:
                self.request_times.append(now)
                status = "allowed"
            else:
                status = "denied"

            rate_limit_requests_total.labels(
                service=self.service_name,
                limiter=self.limiter_name,
                status=status,
            ).inc()

            # Calcular retry_after
            if self.request_times:
                oldest_in_window = self.request_times[0]
                retry_after = oldest_in_window + self.window_seconds - now
            else:
                retry_after = 0.0

            return RateLimitResult(
                allowed=allowed,
                tokens_remaining=max(0, self.limit - len(self.request_times)),
                retry_after=max(0.0, retry_after),
                reset_time=now + max(0.0, retry_after),
            )

    async def acquire(self, block: bool = True, timeout: Optional[float] = None) -> RateLimitResult:
        """Tenta adquirir permissão para requisição.

        Args:
            block: Se deve aguardar até ter permissão
            timeout: Tempo máximo de espera

        Returns:
            RateLimitResult com status
        """
        result = await self.check()

        if result.allowed or not block:
            return result

        # Aguarda se block=True
        start_wait = time.monotonic()
        deadline = start_wait + timeout if timeout else None

        while True:
            await asyncio.sleep(min(0.1, result.retry_after))

            result = await self.check()
            if result.allowed:
                return result

            if deadline and time.monotonic() >= deadline:
                raise RateLimitExceededError(
                    f"Timeout aguardando rate limit: {self.limit} req/{self.window_seconds}s",
                    service=self.service_name,
                    limit=self.limit,
                    window_seconds=self.window_seconds,
                    retry_after=result.retry_after,
                )


class ConcurrencyLimiter:
    """Limitador de concorrência (bulkhead pattern).

    Limita o número de operações simultâneas para evitar sobrecarga.

    Attributes:
        max_concurrent: Número máximo de operações simultâneas
        queue_size: Tamanho da fila de espera (0 = sem fila)
    """

    def __init__(
        self,
        max_concurrent: int,
        queue_size: int = 0,
        service_name: str = "unknown",
        limiter_name: str = "concurrency",
    ):
        if max_concurrent <= 0:
            raise ValueError("max_concurrent deve ser > 0")
        if queue_size < 0:
            raise ValueError("queue_size deve ser >= 0")

        self.max_concurrent = max_concurrent
        self.queue_size = queue_size
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.service_name = service_name
        self.limiter_name = limiter_name
        self.logger = structlog.get_logger()
        self._current_concurrent = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Tenta adquirir permissão para executar.

        Raises:
            ConcurrencyLimitExceededError: Se limite excedido e fila cheia
        """
        if self.queue_size > 0:
            # Tentar adquirir com timeout baseado no tamanho da fila
            queue = asyncio.Queue(maxsize=self.queue_size)

            try:
                await asyncio.wait_for(
                    queue.put(None),
                    timeout=0.001 * self.queue_size,
                )
            except asyncio.TimeoutError:
                raise ConcurrencyLimitExceededError(
                    f"Limite de concorrência excedido e fila cheia: {self.max_concurrent} concurrent, {self.queue_size} queued",
                    service=self.service_name,
                    current_concurrent=self._current_concurrent,
                    max_concurrent=self.max_concurrent,
                )
            finally:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

        await self.semaphore.acquire()

        async with self._lock:
            self._current_concurrent += 1
            concurrent_requests.labels(
                service=self.service_name,
                limiter=self.limiter_name,
            ).set(self._current_concurrent)

    def release(self) -> None:
        """Libera permissão após execução."""
        self.semaphore.release()
        self._current_concurrent -= 1
        concurrent_requests.labels(
            service=self.service_name,
            limiter=self.limiter_name,
        ).set(max(0, self._current_concurrent))

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


class RateLimiterFactory:
    """Factory para criar rate limiters configurados.

    Example:
        ```python
        factory = RateLimiterFactory(service_name="my-service")

        # Token bucket para API externa
        api_limiter = factory.token_bucket(
            capacity=100,
            refill_rate=10,  # 10 tokens/segundo
        )

        # Sliding window para operações críticas
        critical_limiter = factory.sliding_window_log(
            limit=10,
            window_seconds=60,
        )

        # Concurrency limiter para DB operations
        db_limiter = factory.concurrency(
            max_concurrent=5,
            queue_size=10,
        )
        ```
    """

    def __init__(self, service_name: str):
        self.service_name = service_name

    def token_bucket(
        self,
        capacity: int,
        refill_rate: float,
        name: str = "token_bucket",
    ) -> TokenBucketRateLimiter:
        """Cria um Token Bucket Rate Limiter."""
        return TokenBucketRateLimiter(
            capacity=capacity,
            refill_rate=refill_rate,
            service_name=self.service_name,
            limiter_name=name,
        )

    def sliding_window_log(
        self,
        limit: int,
        window_seconds: float,
        name: str = "sliding_window_log",
    ) -> SlidingWindowLogRateLimiter:
        """Cria um Sliding Window Log Rate Limiter."""
        return SlidingWindowLogRateLimiter(
            limit=limit,
            window_seconds=window_seconds,
            service_name=self.service_name,
            limiter_name=name,
        )

    def concurrency(
        self,
        max_concurrent: int,
        queue_size: int = 0,
        name: str = "concurrency",
    ) -> ConcurrencyLimiter:
        """Cria um Concurrency Limiter (Bulkhead)."""
        return ConcurrencyLimiter(
            max_concurrent=max_concurrent,
            queue_size=queue_size,
            service_name=self.service_name,
            limiter_name=name,
        )
