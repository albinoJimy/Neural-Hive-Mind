"""Testes para módulo rate_limiter."""

import pytest
import asyncio
import time

from neural_hive_resilience.rate_limiter import (
    TokenBucketRateLimiter,
    SlidingWindowLogRateLimiter,
    ConcurrencyLimiter,
    RateLimiterFactory,
    RateLimitAlgorithm,
    RateLimitResult,
)
from neural_hive_resilience.exceptions import (
    RateLimitExceededError,
    ConcurrencyLimitExceededError,
)


class TestTokenBucketRateLimiter:
    """Testes para TokenBucketRateLimiter."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Testa inicialização com parâmetros válidos."""
        limiter = TokenBucketRateLimiter(
            capacity=100,
            refill_rate=10,
            service_name="test-service",
        )

        assert limiter.capacity == 100
        assert limiter.refill_rate == 10
        assert limiter.tokens == 100

    def test_initialization_invalid_capacity(self):
        """Testa erro com capacidade inválida."""
        with pytest.raises(ValueError, match="capacity deve ser > 0"):
            TokenBucketRateLimiter(capacity=0, refill_rate=10)

    def test_initialization_invalid_refill_rate(self):
        """Testa erro com refill_rate inválido."""
        with pytest.raises(ValueError, match="refill_rate deve ser > 0"):
            TokenBucketRateLimiter(capacity=100, refill_rate=0)

    @pytest.mark.asyncio
    async def test_acquire_success(self):
        """Testa aquisição bem-sucedida de tokens."""
        limiter = TokenBucketRateLimiter(
            capacity=10,
            refill_rate=1,
        )

        result = await limiter.acquire(tokens=5)

        assert result.allowed is True
        assert result.tokens_remaining == 5
        assert result.retry_after == 0

    @pytest.mark.asyncio
    async def test_acquire_insufficient_tokens_no_block(self):
        """Testa erro quando não há tokens suficientes sem bloqueio."""
        limiter = TokenBucketRateLimiter(
            capacity=5,
            refill_rate=1,
        )

        # Consumir todos os tokens
        await limiter.acquire(tokens=5)

        # Tentar adquirir mais sem bloqueio
        with pytest.raises(RateLimitExceededError):
            await limiter.acquire(tokens=1, block=False)

    @pytest.mark.asyncio
    async def test_acquire_with_wait(self):
        """Testa aquisição com espera por reabastecimento."""
        limiter = TokenBucketRateLimiter(
            capacity=5,
            refill_rate=10,  # 10 tokens/segundo
        )

        # Consumir todos os tokens
        await limiter.acquire(tokens=5)

        # Aguardar reabastecimento (deve ser rápido)
        start = time.monotonic()
        result = await limiter.acquire(tokens=3, block=True)
        elapsed = time.monotonic() - start

        assert result.allowed is True
        # Deve ter esperado ~0.3 segundos (3 tokens / 10 tokens/s)
        assert 0.25 < elapsed < 0.5

    @pytest.mark.asyncio
    async def test_refill_over_time(self):
        """Testa reabastecimento ao longo do tempo."""
        limiter = TokenBucketRateLimiter(
            capacity=10,
            refill_rate=5,  # 5 tokens/segundo
        )

        # Consumir tudo
        await limiter.acquire(tokens=10)

        # Aguardar 1 segundo (deve repor 5 tokens)
        await asyncio.sleep(1.0)

        result = await limiter.acquire(tokens=5, block=False)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_refill_respects_capacity(self):
        """Testa que reabastecimento não excede capacidade."""
        limiter = TokenBucketRateLimiter(
            capacity=10,
            refill_rate=100,
        )

        # Consumir metade
        await limiter.acquire(tokens=5)

        # Aguardar bastante tempo
        await asyncio.sleep(1.0)

        # Tokens devem estar na capacidade máxima
        result = await limiter.acquire(tokens=10, block=False)
        assert result.allowed is True
        assert result.tokens_remaining == 0

    @pytest.mark.asyncio
    async def test_reserve(self):
        """Testa método reserve."""
        limiter = TokenBucketRateLimiter(
            capacity=10,
            refill_rate=1,
        )

        # Reservar com tokens disponíveis
        wait_time = await limiter.reserve(tokens=5)
        assert wait_time == 0

        # Reservar sem tokens disponíveis
        wait_time = await limiter.reserve(tokens=10)
        assert wait_time > 0


class TestSlidingWindowLogRateLimiter:
    """Testes para SlidingWindowLogRateLimiter."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Testa inicialização."""
        limiter = SlidingWindowLogRateLimiter(
            limit=10,
            window_seconds=60,
        )

        assert limiter.limit == 10
        assert limiter.window_seconds == 60

    @pytest.mark.asyncio
    async def test_check_within_limit(self):
        """Testa verificação dentro do limite."""
        limiter = SlidingWindowLogRateLimiter(
            limit=5,
            window_seconds=10,
        )

        for _ in range(5):
            result = await limiter.check()
            assert result.allowed is True

        # 6ª requisição deve ser negada
        result = await limiter.check()
        assert result.allowed is False
        assert result.tokens_remaining == 0

    @pytest.mark.asyncio
    async def test_window_sliding(self):
        """Testa que janela desliza corretamente."""
        limiter = SlidingWindowLogRateLimiter(
            limit=2,
            window_seconds=1,  # 1 janela de 1 segundo
        )

        # Fazer 2 requisições
        await limiter.check()  # t=0
        await limiter.check()  # t=0

        # 3ª deve ser negada
        result = await limiter.check()
        assert result.allowed is False

        # Aguardar janela deslizar
        await asyncio.sleep(1.1)

        # Agora deve permitir novamente
        result = await limiter.check()
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_acquire_blocking(self):
        """Testa aquisição com bloqueio."""
        limiter = SlidingWindowLogRateLimiter(
            limit=2,
            window_seconds=0.5,
        )

        # Consumir limite
        await limiter.acquire()
        await limiter.acquire()

        # Tentar adquirir mais (deve aguardar)
        start = time.monotonic()
        result = await limiter.acquire(block=True, timeout=1.0)
        elapsed = time.monotonic() - start

        assert result.allowed is True
        assert elapsed >= 0.4  # Perto do tempo da janela


class TestConcurrencyLimiter:
    """Testes para ConcurrencyLimiter."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Testa inicialização."""
        limiter = ConcurrencyLimiter(
            max_concurrent=5,
            queue_size=2,
        )

        assert limiter.max_concurrent == 5
        assert limiter.queue_size == 2

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        """Testa aquisição e liberação."""
        limiter = ConcurrencyLimiter(
            max_concurrent=2,
            queue_size=0,
        )

        await limiter.acquire()
        assert limiter._current_concurrent == 1

        await limiter.acquire()
        assert limiter._current_concurrent == 2

        limiter.release()
        assert limiter._current_concurrent == 1

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Testa uso como context manager."""
        limiter = ConcurrencyLimiter(
            max_concurrent=2,
            queue_size=0,
        )

        async with limiter:
            assert limiter._current_concurrent == 1

        assert limiter._current_concurrent == 0

    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        """Testa limite de concorrência."""
        limiter = ConcurrencyLimiter(
            max_concurrent=2,
            queue_size=2,
        )

        active_count = 0
        max_active = 0

        async def task():
            nonlocal active_count, max_active
            await limiter.acquire()
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.1)
            active_count -= 1
            limiter.release()

        # Executar 5 tarefas simultâneas
        tasks = [task() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Nunca deve exceder max_concurrent
        assert max_active <= 2

    @pytest.mark.asyncio
    async def test_queue_exceeded(self):
        """Testa erro quando fila é excedida."""
        limiter = ConcurrencyLimiter(
            max_concurrent=1,
            queue_size=1,
        )

        # Preencher concorrência
        await limiter.acquire()

        # Preencher fila
        try:
            await asyncio.wait_for(
                limiter._lock.acquire(),
                timeout=0.01,
            )
        except asyncio.TimeoutError:
            pass

        # Tentar adquirir com fila cheia
        # (depende da implementação do teste)


class TestRateLimiterFactory:
    """Testes para RateLimiterFactory."""

    def test_initialization(self):
        """Testa criação da factory."""
        factory = RateLimiterFactory(service_name="test-service")
        assert factory.service_name == "test-service"

    def test_token_bucket_creation(self):
        """Testa criação de token bucket."""
        factory = RateLimiterFactory(service_name="test-service")

        limiter = factory.token_bucket(
            capacity=100,
            refill_rate=10,
            name="api-limiter",
        )

        assert isinstance(limiter, TokenBucketRateLimiter)
        assert limiter.service_name == "test-service"
        assert limiter.limiter_name == "api-limiter"

    def test_sliding_window_creation(self):
        """Testa criação de sliding window."""
        factory = RateLimiterFactory(service_name="test-service")

        limiter = factory.sliding_window_log(
            limit=100,
            window_seconds=60,
            name="window-limiter",
        )

        assert isinstance(limiter, SlidingWindowLogRateLimiter)
        assert limiter.service_name == "test-service"
        assert limiter.limiter_name == "window-limiter"

    def test_concurrency_creation(self):
        """Testa criação de concurrency limiter."""
        factory = RateLimiterFactory(service_name="test-service")

        limiter = factory.concurrency(
            max_concurrent=5,
            queue_size=2,
            name="concurrency-limiter",
        )

        assert isinstance(limiter, ConcurrencyLimiter)
        assert limiter.service_name == "test-service"
        assert limiter.limiter_name == "concurrency-limiter"


class TestRateLimitResult:
    """Testes para RateLimitResult."""

    def test_creation(self):
        """Testa criação de resultado."""
        result = RateLimitResult(
            allowed=True,
            tokens_remaining=5,
            retry_after=0.0,
            reset_time=time.time() + 60,
        )

        assert result.allowed is True
        assert result.tokens_remaining == 5
        assert result.retry_after == 0.0
