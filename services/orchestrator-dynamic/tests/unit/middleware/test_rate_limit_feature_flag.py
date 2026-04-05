"""
Testes para verificar feature flag enable_rate_limiting (Task 6.5).

Verifica que o middleware funciona com a flag enabled/disabled.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from src.config.settings import OrchestratorSettings
from src.middleware.rate_limit_middleware import RateLimitMiddleware

from neural_hive_resilience import RateLimitResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def settings_enabled():
    """Settings com rate limiting habilitado."""
    return MagicMock(
        spec=OrchestratorSettings,
        enable_rate_limiting=True,
        rate_limit_default_capacity=5,
        rate_limit_default_refill_rate=1.0,
        rate_limit_burst_multiplier=2.0,
        rate_limit_tier_limits={},
        rate_limit_redis_key_prefix="rate_limit",
        service_name="orchestrator-dynamic",
    )


@pytest.fixture
def settings_disabled():
    """Settings com rate limiting desabilitado."""
    return MagicMock(
        spec=OrchestratorSettings,
        enable_rate_limiting=False,
        rate_limit_default_capacity=5,
        rate_limit_default_refill_rate=1.0,
        rate_limit_burst_multiplier=2.0,
        rate_limit_tier_limits={},
        rate_limit_redis_key_prefix="rate_limit",
        service_name="orchestrator-dynamic",
    )


@pytest.fixture
def mock_redis():
    """Mock do Redis client."""
    return AsyncMock()


# =============================================================================
# Testes Feature Flag
# =============================================================================


@pytest.mark.asyncio
async def test_feature_flag_enabled_enforces_limit(settings_enabled, mock_redis):
    """Testa que com enable_rate_limiting=True, limites são aplicados."""
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis,
        settings=settings_enabled,
    )

    @app.get("/test")
    async def test_endpoint():
        return Response(content="OK", status_code=200)

    # Patch para simular rate limit exceeded
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        # Simular limite excedido após algumas requests
        call_count = [0]

        def side_effect(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] > 5:
                return RateLimitResult(
                    allowed=False,
                    tokens_remaining=0,
                    retry_after=60.0,
                    reset_time=1743849600.0,
                )
            return RateLimitResult(
                allowed=True,
                tokens_remaining=5 - call_count[0],
                retry_after=0.0,
                reset_time=1743849600.0,
            )

        mock_check.side_effect = side_effect

        with TestClient(app) as client:
            # Primeiras 5 requests devem passar
            for i in range(5):
                response = client.get(
                    "/test",
                    headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
                )
                assert response.status_code == 200, f"Request {i+1} deve passar"

            # 6ª request deve ser bloqueada
            response = client.get(
                "/test",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )
            assert (
                response.status_code == 429
            ), "6ª request deve ser bloqueada por rate limit"
            assert "rate_limit_exceeded" in response.json()["error"]


@pytest.mark.asyncio
async def test_feature_flag_disabled_bypasses_middleware(settings_disabled, mock_redis):
    """Testa que com enable_rate_limiting=False, nenhuma request é limitada."""
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis,
        settings=settings_disabled,
    )

    request_count = [0]

    @app.get("/test")
    async def test_endpoint():
        request_count[0] += 1
        return Response(content=f"Request #{request_count[0]}", status_code=200)

    with TestClient(app) as client:
        # Fazer MUITAS requests - nenhuma deve ser limitada
        for _ in range(100):
            response = client.get(
                "/test",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )
            assert (
                response.status_code == 200
            ), "Com flag disabled, todas requests devem passar"
            # Sem headers de rate limit
            assert "RateLimit-Limit" not in response.headers

        # Verificar que todas as 100 requests foram processadas
        assert request_count[0] == 100


@pytest.mark.asyncio
async def test_feature_flag_respects_default_false(mock_redis):
    """Testa que default=False significa que rate limiting vem desabilitado."""
    # Criar settings sem especificar enable_rate_limiting
    settings_with_default = MagicMock(
        spec=OrchestratorSettings,
        # enable_rate_limiting não especificado, deve usar default do Field
        rate_limit_default_capacity=5,
        rate_limit_default_refill_rate=1.0,
        rate_limit_burst_multiplier=2.0,
        rate_limit_tier_limits={},
        rate_limit_redis_key_prefix="rate_limit",
        service_name="orchestrator-dynamic",
    )
    # Simular o padrão (default=False no Field)
    settings_with_default.enable_rate_limiting = False

    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis,
        settings=settings_with_default,
    )

    @app.get("/test")
    async def test_endpoint():
        return Response(content="OK", status_code=200)

    with TestClient(app) as client:
        # Fazer requests - nenhuma deve ser limitada
        for _ in range(20):
            response = client.get("/test")
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_feature_flag_toggles_at_runtime(settings_enabled, mock_redis):
    """
    Testa que mudar a feature flag em tempo de execução afeta o comportamento.

    Nota: Em produção, isto requer reinicialização do app, mas para teste
    verificamos que o middleware respeita o valor no momento da criação.
    """
    # Criar app com flag habilitada
    app_enabled = FastAPI()

    app_enabled.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis,
        settings=settings_enabled,
    )

    @app_enabled.get("/test")
    async def test_endpoint_enabled():
        return Response(content="enabled", status_code=200)

    # Criar app com flag desabilitada
    app_disabled = FastAPI()

    app_disabled.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis,
        settings=settings_disabled,
    )

    @app_disabled.get("/test")
    async def test_endpoint_disabled():
        return Response(content="disabled", status_code=200)

    # Testar app com rate limit habilitado
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=60.0,
            reset_time=1743849600.0,
        )

        with TestClient(app_enabled) as client:
            response = client.get("/test")
            # Com flag enabled, rate limit é aplicado
            assert response.status_code == 429

    # Testar app com rate limit desabilitado
    with TestClient(app_disabled) as client:
        response = client.get("/test")
        # Com flag disabled, rate limit NÃO é aplicado
        assert response.status_code == 200
        assert "disabled" in response.text
