"""Testes unitários para Rate Limit Middleware."""

import pytest

from src.middleware.rate_limit import (
    RateLimiter,
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitResult,
    TenantTier,
)


class TestRateLimitConfig:
    """Testes para RateLimitConfig."""

    def test_config_creation(self):
        """RateLimitConfig deve ser criado com valores fornecidos."""
        config = RateLimitConfig(requests_per_minute=100)
        assert config.requests_per_minute == 100
        assert config.requests_per_hour is None
        assert config.burst == 150  # Default 1.5x

    def test_config_with_custom_burst(self):
        """RateLimitConfig deve aceitar burst customizado."""
        config = RateLimitConfig(requests_per_minute=100, burst=200)
        assert config.burst == 200


class TestRateLimitResult:
    """Testes para RateLimitResult."""

    def test_allowed_result(self):
        """RateLimitResult deve representar request permitida."""
        result = RateLimitResult(
            allowed=True,
            remaining=50,
            reset_at=1234567890,
            limit=100,
        )
        assert result.allowed is True
        assert result.remaining == 50
        assert result.reset_at == 1234567890
        assert result.limit == 100
        assert result.retry_after is None

    def test_blocked_result(self):
        """RateLimitResult deve representar request bloqueada."""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=1234567890,
            limit=100,
            retry_after=30,
        )
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 30


class TestTenantTier:
    """Testes para TenantTier."""

    def test_trial_tier(self):
        """TenantTier TRIAL deve ter config correta."""
        from src.middleware.rate_limit import RATE_LIMIT_TIERS

        config = RATE_LIMIT_TIERS[TenantTier.TRIAL]
        assert config.requests_per_minute == 10  # 10 req/min

    def test_default_tier(self):
        """TenantTier DEFAULT deve ter config correta."""
        from src.middleware.rate_limit import RATE_LIMIT_TIERS

        config = RATE_LIMIT_TIERS[TenantTier.DEFAULT]
        assert config.requests_per_minute == 100  # 100 req/min (INV-8)

    def test_enterprise_tier(self):
        """TenantTier ENTERPRISE deve ter config correta."""
        from src.middleware.rate_limit import RATE_LIMIT_TIERS

        config = RATE_LIMIT_TIERS[TenantTier.ENTERPRISE]
        assert config.requests_per_minute == 1000  # 1000 req/min (INV-8)


class TestRateLimiter:
    """Testes para RateLimiter."""

    def test_redis_key_creation(self):
        """RateLimiter deve criar chaves Redis corretamente."""
        limiter = RateLimiter(redis_url="redis://localhost:7000/1")

        key = limiter._make_key("tenant-123", "user-456", "/api/test", "rate_limit", 12345)
        assert key == "unified_gateway:rate_limit:tenant-123:user-456:/api/test:rate_limit:12345"

    def test_redis_key_with_none_values(self):
        """RateLimiter deve lidar com valores None na chave."""
        limiter = RateLimiter()

        key = limiter._make_key("tenant-123", None, None, "rate_limit", 12345)
        assert key == "unified_gateway:rate_limit:tenant-123:rate_limit:12345"


class TestRateLimitMiddleware:
    """Testes para RateLimitMiddleware."""

    def test_should_skip_excluded_paths(self):
        """Middleware deve pular rate limiting para paths excluídos."""

        def dummy_app(scope, receive, send):
            pass

        middleware = RateLimitMiddleware(
            app=dummy_app,
            exclude_paths=["/health", "/metrics"],
        )

        assert middleware._should_skip("/health") is True
        assert middleware._should_skip("/metrics") is True
        assert middleware._should_skip("/api/test") is False

    def test_create_rate_limit_response(self):
        """Middleware deve criar resposta HTTP 429 com Retry-After (INV-8)."""

        def dummy_app(scope, receive, send):
            pass

        middleware = RateLimitMiddleware(app=dummy_app)

        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=1234567890,
            limit=100,
            retry_after=30,
        )

        response = middleware._create_rate_limit_response(result)

        assert response.status_code == 429  # INV-8
        assert b"rate_limit_exceeded" in response.body
        assert response.headers["Retry-After"] == "30"  # INV-8
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "0"
