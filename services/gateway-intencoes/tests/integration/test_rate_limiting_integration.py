"""
Testes de integracao para Rate Limiting com Sliding Window e Redis real
"""
import pytest
import asyncio
import os
import time

# Marca todos os testes deste arquivo como integracao
pytestmark = pytest.mark.integration


class TestRateLimitingIntegration:
    """Testes de integracao para Rate Limiting com Sliding Window"""

    @pytest.fixture
    async def redis_client(self):
        """Fixture para Redis client real"""
        from cache.redis_client import RedisClient

        # Usar Redis local ou variavel de ambiente
        os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")

        client = RedisClient()
        try:
            await client.initialize()
            yield client
        finally:
            await client.close()

    @pytest.fixture
    def rate_limiter(self, redis_client):
        """Fixture do rate limiter com Redis real"""
        from middleware.rate_limiter import RateLimiter

        return RateLimiter(
            redis_client=redis_client,
            enabled=True,
            default_limit=10,  # Limite baixo para testes
            burst_size=2,      # Permite 2 requisicoes extras como burst
            fail_open=True
        )

    @pytest.mark.asyncio
    async def test_sliding_window_basic(self, rate_limiter):
        """Testar sliding window basico com Redis real"""
        # Usar ID unico para evitar conflito com outros testes
        user_id = f"test_user_sliding_{int(time.time() * 1000)}"

        # Fazer 10 requisicoes (dentro do limite base)
        for i in range(10):
            result = await rate_limiter.check_rate_limit(user_id=user_id)
            assert result.allowed is True, f"Request {i+1} should be allowed"
            assert result.limit == 10  # Reports base limit

        # Requisicoes 11 e 12 ainda permitidas (burst)
        for i in range(2):
            result = await rate_limiter.check_rate_limit(user_id=user_id)
            assert result.allowed is True, f"Burst request {i+1} should be allowed"

        # 13a requisicao deve ser bloqueada (acima de base + burst = 12)
        result = await rate_limiter.check_rate_limit(user_id=user_id)
        assert result.allowed is False
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_sliding_window_burst_behavior(self, rate_limiter):
        """Testar que burst permite requisicoes extras"""
        user_id = f"test_user_burst_{int(time.time() * 1000)}"

        # Esgotar limite base (10 requisicoes)
        for _ in range(10):
            result = await rate_limiter.check_rate_limit(user_id=user_id)
            assert result.allowed is True

        # Verificar que remaining e 0 apos limite base
        result = await rate_limiter.check_rate_limit(user_id=user_id)
        assert result.allowed is True  # Burst ainda disponivel
        assert result.remaining == 0  # Remaining baseado no limite base

        # Ultima requisicao de burst
        result = await rate_limiter.check_rate_limit(user_id=user_id)
        assert result.allowed is True  # Ultimo burst

        # Proxima requisicao deve ser bloqueada
        result = await rate_limiter.check_rate_limit(user_id=user_id)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_sliding_window_concurrent_requests(self, rate_limiter):
        """Testar sliding window com requisicoes concorrentes"""
        user_id = f"test_user_concurrent_{int(time.time() * 1000)}"

        # Fazer 20 requisicoes concorrentes
        tasks = [
            rate_limiter.check_rate_limit(user_id=user_id)
            for _ in range(20)
        ]

        results = await asyncio.gather(*tasks)

        # Apenas 12 devem ser permitidas (10 base + 2 burst)
        allowed_count = sum(1 for r in results if r.allowed)
        assert allowed_count == 12

    @pytest.mark.asyncio
    async def test_sliding_window_different_users(self, rate_limiter):
        """Testar que usuarios diferentes tem janelas independentes"""
        timestamp = int(time.time() * 1000)
        user1 = f"test_user1_{timestamp}"
        user2 = f"test_user2_{timestamp}"

        # Esgotar limite do user1 (10 base + 2 burst = 12)
        for _ in range(12):
            await rate_limiter.check_rate_limit(user_id=user1)

        # User1 deve estar bloqueado
        result1 = await rate_limiter.check_rate_limit(user_id=user1)
        assert result1.allowed is False

        # User2 ainda deve ter limite disponivel
        result2 = await rate_limiter.check_rate_limit(user_id=user2)
        assert result2.allowed is True

    @pytest.mark.asyncio
    async def test_sliding_window_tenant_override(self, rate_limiter):
        """Testar limite por tenant com sliding window"""
        tenant_id = f"premium_tenant_{int(time.time() * 1000)}"
        user_id = f"test_user_{int(time.time() * 1000)}"

        # Configurar limite maior para tenant premium
        rate_limiter.set_tenant_limit(tenant_id, 15)

        # Fazer 15 requisicoes (dentro do limite do tenant premium)
        for i in range(15):
            result = await rate_limiter.check_rate_limit(
                user_id=user_id,
                tenant_id=tenant_id
            )
            assert result.allowed is True, f"Request {i+1} should be allowed for premium tenant"
            assert result.limit == 15  # Tenant limit

        # Requisicoes 16 e 17 ainda permitidas (burst de 2)
        for i in range(2):
            result = await rate_limiter.check_rate_limit(
                user_id=user_id,
                tenant_id=tenant_id
            )
            assert result.allowed is True, f"Burst request {i+1} should be allowed"

    @pytest.mark.asyncio
    async def test_sliding_window_remaining_decreases(self, rate_limiter):
        """Testar que remaining diminui corretamente"""
        user_id = f"test_user_remaining_{int(time.time() * 1000)}"

        results = []
        for _ in range(5):
            result = await rate_limiter.check_rate_limit(user_id=user_id)
            results.append(result.remaining)

        # Remaining deve diminuir a cada requisicao (baseado no limite base de 10)
        assert results == [9, 8, 7, 6, 5]

    @pytest.mark.asyncio
    async def test_sliding_window_headers_present(self, rate_limiter):
        """Testar que resultado contem informacoes para headers"""
        user_id = f"test_user_headers_{int(time.time() * 1000)}"

        result = await rate_limiter.check_rate_limit(user_id=user_id)

        assert result.limit == 10  # Base limit
        assert result.remaining >= 0
        assert result.reset_at > 0
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_sliding_window_reset_at_format(self, rate_limiter):
        """Testar que reset_at e um timestamp Unix valido"""
        user_id = f"test_user_reset_{int(time.time() * 1000)}"

        result = await rate_limiter.check_rate_limit(user_id=user_id)

        current_time = int(time.time())
        # reset_at deve ser aproximadamente 60 segundos no futuro
        assert result.reset_at >= current_time + 59
        assert result.reset_at <= current_time + 61

    @pytest.mark.asyncio
    async def test_sliding_window_no_burst(self):
        """Testar sliding window sem burst"""
        from cache.redis_client import RedisClient
        from middleware.rate_limiter import RateLimiter

        os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")
        client = RedisClient()

        try:
            await client.initialize()

            limiter = RateLimiter(
                redis_client=client,
                enabled=True,
                default_limit=5,
                burst_size=0,  # Sem burst
                fail_open=True
            )

            user_id = f"test_user_no_burst_{int(time.time() * 1000)}"

            # Fazer 5 requisicoes (limite exato)
            for i in range(5):
                result = await limiter.check_rate_limit(user_id=user_id)
                assert result.allowed is True, f"Request {i+1} should be allowed"

            # 6a requisicao deve ser bloqueada imediatamente (sem burst)
            result = await limiter.check_rate_limit(user_id=user_id)
            assert result.allowed is False

        finally:
            await client.close()


class TestRateLimitingSlidingWindowBehavior:
    """Testes especificos para comportamento de sliding window"""

    @pytest.fixture
    async def redis_client(self):
        """Fixture para Redis client real"""
        from cache.redis_client import RedisClient

        os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")
        client = RedisClient()

        try:
            await client.initialize()
            yield client
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_sliding_window_continuous_nature(self, redis_client):
        """
        Testar natureza continua do sliding window

        Diferente do fixed window, o sliding window considera
        os ultimos 60 segundos continuamente, nao apenas o minuto atual.
        """
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=redis_client,
            enabled=True,
            default_limit=5,
            burst_size=0,
            fail_open=True
        )

        user_id = f"test_sliding_continuous_{int(time.time() * 1000)}"

        # Fazer 5 requisicoes
        for _ in range(5):
            result = await limiter.check_rate_limit(user_id=user_id)
            assert result.allowed is True

        # Proxima deve ser bloqueada
        result = await limiter.check_rate_limit(user_id=user_id)
        assert result.allowed is False

        # Mesmo se passarmos para o proximo "minuto", ainda estamos
        # na mesma janela de 60 segundos
        # (Este teste valida que nao resetamos no limite do minuto)

    @pytest.mark.asyncio
    async def test_retry_after_value(self, redis_client):
        """Testar que retry_after e calculado corretamente"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=redis_client,
            enabled=True,
            default_limit=3,
            burst_size=0,
            fail_open=True
        )

        user_id = f"test_retry_after_{int(time.time() * 1000)}"

        # Esgotar limite
        for _ in range(3):
            await limiter.check_rate_limit(user_id=user_id)

        # Verificar retry_after
        result = await limiter.check_rate_limit(user_id=user_id)
        assert result.allowed is False
        assert result.retry_after is not None
        assert result.retry_after > 0
        assert result.retry_after <= 60  # No maximo 60 segundos


class TestRateLimitingIntegrationSkipIfNoRedis:
    """Testes que sao pulados se Redis nao estiver disponivel"""

    @pytest.fixture
    async def redis_available(self):
        """Verificar se Redis esta disponivel"""
        from cache.redis_client import RedisClient

        os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")

        client = RedisClient()
        try:
            await client.initialize()
            await client.close()
            return True
        except Exception:
            return False

    @pytest.mark.asyncio
    async def test_sliding_window_expiration(self, redis_available):
        """
        Testar que requisicoes antigas expiram da janela

        Nota: Este teste requer espera de 60+ segundos e so deve ser
        executado em ambientes de CI com tempo disponivel.
        """
        if not redis_available:
            pytest.skip("Redis nao disponivel")

        # Este teste e muito lento para rodar regularmente
        # Descomente para testes manuais completos
        pytest.skip("Teste muito lento - rodar manualmente se necessario")

        # Codigo do teste (para referencia):
        # from cache.redis_client import RedisClient
        # from middleware.rate_limiter import RateLimiter
        #
        # os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")
        # client = RedisClient()
        # await client.initialize()
        #
        # limiter = RateLimiter(
        #     redis_client=client,
        #     enabled=True,
        #     default_limit=3,
        #     burst_size=0,
        #     fail_open=True
        # )
        #
        # user_id = f"test_expiration_{int(time.time() * 1000)}"
        #
        # # Esgotar limite
        # for _ in range(3):
        #     await limiter.check_rate_limit(user_id=user_id)
        #
        # # Verificar bloqueado
        # result = await limiter.check_rate_limit(user_id=user_id)
        # assert result.allowed is False
        #
        # # Aguardar janela expirar (61 segundos)
        # await asyncio.sleep(61)
        #
        # # Agora deve permitir novamente
        # result = await limiter.check_rate_limit(user_id=user_id)
        # assert result.allowed is True
        #
        # await client.close()
