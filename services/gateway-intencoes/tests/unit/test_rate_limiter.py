"""
Testes unitarios para Rate Limiter com Sliding Window e Burst Support
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import time


class TestRateLimiter:
    """Testes para o Rate Limiter"""

    @pytest.fixture
    def mock_redis(self):
        """Mock do cliente Redis"""
        redis = AsyncMock()
        # Sliding window: [zremrangebyscore result, zadd result, zcard result, expire result]
        redis.pipeline_operations = AsyncMock(return_value=[0, 1, 1, True])
        return redis

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Fixture do rate limiter"""
        from middleware.rate_limiter import RateLimiter
        return RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=20,
            fail_open=True
        )

    @pytest.mark.asyncio
    async def test_rate_limit_allowed(self, rate_limiter, mock_redis):
        """Testar requisicao dentro do limite"""
        # zcard returns 50 (within limit of 100 + 20 burst = 120)
        mock_redis.pipeline_operations.return_value = [0, 1, 50, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.limit == 100  # Reports base limit
        assert result.remaining == 50  # 100 - 50

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, rate_limiter, mock_redis):
        """Testar requisicao acima do limite (base + burst)"""
        # zcard returns 121 (above limit of 100 + 20 burst = 120)
        mock_redis.pipeline_operations.return_value = [0, 1, 121, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None

    @pytest.mark.asyncio
    async def test_rate_limit_burst_allows_extra_requests(self, rate_limiter, mock_redis):
        """Testar que burst_size permite requisicoes extras alem do limite base"""
        # zcard returns 110 (above base limit 100 but within burst allowance 100+20=120)
        mock_redis.pipeline_operations.return_value = [0, 1, 110, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.limit == 100  # Reports base limit to user

    @pytest.mark.asyncio
    async def test_rate_limit_at_burst_limit(self, rate_limiter, mock_redis):
        """Testar requisicao exatamente no limite efetivo (base + burst)"""
        # zcard returns 120 (exactly at limit of 100 + 20 burst)
        mock_redis.pipeline_operations.return_value = [0, 1, 120, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_rate_limit_tenant_override(self, rate_limiter, mock_redis):
        """Testar limite especifico por tenant"""
        rate_limiter.set_tenant_limit("premium-tenant", 500)
        # zcard returns 250 (within tenant limit 500 + 20 burst = 520)
        mock_redis.pipeline_operations.return_value = [0, 1, 250, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="premium-tenant"
        )

        assert result.allowed is True
        assert result.limit == 500

    @pytest.mark.asyncio
    async def test_rate_limit_user_override(self, rate_limiter, mock_redis):
        """Testar limite especifico por usuario"""
        rate_limiter.set_user_limit("admin-user", 1000)
        # zcard returns 500 (within user limit 1000 + 20 burst = 1020)
        mock_redis.pipeline_operations.return_value = [0, 1, 500, True]

        result = await rate_limiter.check_rate_limit(
            user_id="admin-user",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.limit == 1000

    @pytest.mark.asyncio
    async def test_rate_limit_user_takes_priority_over_tenant(self, rate_limiter, mock_redis):
        """Testar que limite de usuario tem prioridade sobre tenant"""
        rate_limiter.set_tenant_limit("tenant1", 500)
        rate_limiter.set_user_limit("special-user", 2000)
        # zcard returns 1500 (within user limit 2000 + 20 burst = 2020)
        mock_redis.pipeline_operations.return_value = [0, 1, 1500, True]

        result = await rate_limiter.check_rate_limit(
            user_id="special-user",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.limit == 2000

    @pytest.mark.asyncio
    async def test_rate_limit_fail_open(self, rate_limiter, mock_redis):
        """Testar fail-open quando Redis falha"""
        mock_redis.pipeline_operations.side_effect = Exception("Redis connection failed")

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        # Deve permitir requisicao mesmo com erro (fail-open)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_fail_closed(self, mock_redis):
        """Testar fail-closed quando Redis falha"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=20,
            fail_open=False  # fail-closed
        )

        mock_redis.pipeline_operations.side_effect = Exception("Redis connection failed")

        result = await limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        # Deve bloquear requisicao com erro (fail-closed)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_rate_limit_disabled(self, mock_redis):
        """Testar comportamento quando rate limiting esta desabilitado"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=False,
            default_limit=100,
            burst_size=20
        )

        result = await limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        # Redis nao deve ser chamado
        mock_redis.pipeline_operations.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limit_at_exact_base_limit(self, rate_limiter, mock_redis):
        """Testar requisicao exatamente no limite base"""
        # zcard returns 100 (at base limit, but allowed due to burst)
        mock_redis.pipeline_operations.return_value = [0, 1, 100, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.remaining == 0  # Remaining based on base limit

    @pytest.mark.asyncio
    async def test_rate_limit_result_has_reset_time(self, rate_limiter, mock_redis):
        """Testar que resultado inclui tempo de reset"""
        mock_redis.pipeline_operations.return_value = [0, 1, 50, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        # Reset time should be approximately 60 seconds from now
        current_time = int(time.time())
        assert result.reset_at >= current_time + 59
        assert result.reset_at <= current_time + 61

    @pytest.mark.asyncio
    async def test_sliding_window_redis_operations(self, rate_limiter, mock_redis):
        """Testar que operacoes Redis corretas sao chamadas para sliding window"""
        mock_redis.pipeline_operations.return_value = [0, 1, 50, True]

        await rate_limiter.check_rate_limit(
            user_id="test_user",
            tenant_id="tenant1"
        )

        # Verificar que pipeline_operations foi chamado
        mock_redis.pipeline_operations.assert_called_once()

        # Verificar estrutura das operacoes
        call_args = mock_redis.pipeline_operations.call_args[0][0]
        assert len(call_args) == 4

        # 1. zremrangebyscore - remover timestamps antigos
        assert call_args[0]["method"] == "zremrangebyscore"
        assert "gateway:rate_limit:sw:test_user" in call_args[0]["args"][0]

        # 2. zadd - adicionar timestamp atual
        assert call_args[1]["method"] == "zadd"

        # 3. zcard - contar total
        assert call_args[2]["method"] == "zcard"

        # 4. expire - definir TTL
        assert call_args[3]["method"] == "expire"
        assert call_args[3]["args"][1] == 61  # WINDOW_SIZE + 1

    @pytest.mark.asyncio
    async def test_burst_size_zero(self, mock_redis):
        """Testar com burst_size = 0 (sem burst permitido)"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=0,  # No burst
            fail_open=True
        )

        # zcard returns 101 (above limit with no burst)
        mock_redis.pipeline_operations.return_value = [0, 1, 101, True]

        result = await limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_large_burst_size(self, mock_redis):
        """Testar com burst_size grande"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=500,  # Large burst
            fail_open=True
        )

        # zcard returns 550 (within 100 + 500 = 600)
        mock_redis.pipeline_operations.return_value = [0, 1, 550, True]

        result = await limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is True
        assert result.limit == 100  # Reports base limit

    def test_set_and_remove_user_limit(self, rate_limiter):
        """Testar adicionar e remover limite de usuario"""
        rate_limiter.set_user_limit("test-user", 500)
        assert "test-user" in rate_limiter.user_limits
        assert rate_limiter.user_limits["test-user"] == 500

        rate_limiter.remove_user_limit("test-user")
        assert "test-user" not in rate_limiter.user_limits

    def test_set_and_remove_tenant_limit(self, rate_limiter):
        """Testar adicionar e remover limite de tenant"""
        rate_limiter.set_tenant_limit("test-tenant", 1000)
        assert "test-tenant" in rate_limiter.tenant_limits
        assert rate_limiter.tenant_limits["test-tenant"] == 1000

        rate_limiter.remove_tenant_limit("test-tenant")
        assert "test-tenant" not in rate_limiter.tenant_limits

    def test_get_current_limits(self, rate_limiter):
        """Testar obter configuracao atual de limites"""
        rate_limiter.set_user_limit("user1", 500)
        rate_limiter.set_tenant_limit("tenant1", 1000)

        limits = rate_limiter.get_current_limits()

        assert limits["default_limit"] == 100
        assert limits["burst_size"] == 20
        assert limits["enabled"] is True
        assert limits["fail_open"] is True
        assert "user1" in limits["user_limits"]
        assert "tenant1" in limits["tenant_limits"]

    @pytest.mark.asyncio
    async def test_rate_limit_without_tenant(self, rate_limiter, mock_redis):
        """Testar rate limit sem tenant_id"""
        mock_redis.pipeline_operations.return_value = [0, 1, 50, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id=None
        )

        assert result.allowed is True
        assert result.limit == 100  # Usa limite default

    @pytest.mark.asyncio
    async def test_retry_after_calculated_correctly(self, rate_limiter, mock_redis):
        """Testar que retry_after e calculado corretamente quando bloqueado"""
        # zcard returns 121 (above effective limit)
        mock_redis.pipeline_operations.return_value = [0, 1, 121, True]

        result = await rate_limiter.check_rate_limit(
            user_id="user123",
            tenant_id="tenant1"
        )

        assert result.allowed is False
        # retry_after deve ser aproximadamente 60 segundos (tamanho da janela)
        assert result.retry_after >= 1
        assert result.retry_after <= 60


class TestRateLimiterSingleton:
    """Testes para singleton do Rate Limiter"""

    def test_get_set_rate_limiter(self):
        """Testar get/set do singleton"""
        from middleware.rate_limiter import (
            get_rate_limiter,
            set_rate_limiter,
            close_rate_limiter,
            RateLimiter
        )

        # Limpar estado anterior
        close_rate_limiter()

        # Inicialmente None
        assert get_rate_limiter() is None

        # Criar e setar
        mock_redis = AsyncMock()
        limiter = RateLimiter(mock_redis, enabled=True, default_limit=100)
        set_rate_limiter(limiter)

        assert get_rate_limiter() is limiter

        # Limpar
        close_rate_limiter()
        assert get_rate_limiter() is None


class TestRateLimiterMetrics:
    """Testes para metricas Prometheus do Rate Limiter"""

    @pytest.fixture
    def mock_redis(self):
        """Mock do cliente Redis"""
        redis = AsyncMock()
        redis.pipeline_operations = AsyncMock(return_value=[0, 1, 50, True])
        return redis

    @pytest.mark.asyncio
    async def test_metrics_include_user_id_label(self, mock_redis):
        """Testar que metricas incluem user_id como label"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=20,
            fail_open=True
        )

        # Verificar que metricas tem label user_id
        assert 'user_id' in limiter.rate_limit_exceeded_counter._labelnames
        assert 'user_id' in limiter.rate_limit_current_usage._labelnames
        assert 'user_id' in limiter.rate_limit_requests_total._labelnames

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_allowed_request(self, mock_redis):
        """Testar que metricas sao registradas em requisicao permitida"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=20,
            fail_open=True
        )

        mock_redis.pipeline_operations.return_value = [0, 1, 50, True]

        result = await limiter.check_rate_limit(
            user_id="test_user",
            tenant_id="test_tenant"
        )

        assert result.allowed is True
        # Metricas devem ser registradas (verificamos que nao lancou excecao)

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_exceeded_request(self, mock_redis):
        """Testar que metricas sao registradas quando limite e excedido"""
        from middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(
            redis_client=mock_redis,
            enabled=True,
            default_limit=100,
            burst_size=20,
            fail_open=True
        )

        # Exceed the limit
        mock_redis.pipeline_operations.return_value = [0, 1, 121, True]

        result = await limiter.check_rate_limit(
            user_id="test_user",
            tenant_id="test_tenant"
        )

        assert result.allowed is False
        # Metricas de exceeded devem ser incrementadas
