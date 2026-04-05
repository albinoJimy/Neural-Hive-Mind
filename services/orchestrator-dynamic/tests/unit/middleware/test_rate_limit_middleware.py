"""
Testes unitários para RateLimitMiddleware.

Seguindo TDD: testes escritos antes da implementação.
"""
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from src.config.settings import OrchestratorSettings
from src.middleware.rate_limit_middleware import RateLimitMiddleware

from neural_hive_resilience import (
    RateLimiterFactory,
    RateLimitResult,
)

# Type alias para call_next
RequestResponseCycle = Callable[[Request], Response]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis_client():
    """Mock do cliente Redis."""
    return AsyncMock()


@pytest.fixture
def mock_settings():
    """Mock das configurações do Orchestrator."""
    return MagicMock(
        spec=OrchestratorSettings,
        enable_rate_limiting=True,
        rate_limit_default_capacity=100,
        rate_limit_default_refill_rate=10.0,
        rate_limit_burst_multiplier=2.0,
        rate_limit_tier_limits={},
        rate_limit_redis_key_prefix="rate_limit",
        service_name="orchestrator-dynamic",
    )


@pytest.fixture
def limiter_factory():
    """Factory para criar rate limiters."""
    return RateLimiterFactory(service_name="orchestrator-dynamic")


@pytest.fixture
def app_instance():
    """Instância do FastAPI app."""
    return FastAPI()


@pytest.fixture
def mock_call_next():
    """Mock para call_next do middleware."""

    async def _call_next(_request: Request) -> Response:
        return Response(content="OK", status_code=200)

    return _call_next


# =============================================================================
# Testes de Extração de Contexto (1.1)
# =============================================================================


@pytest.mark.asyncio
async def test_extract_tenant_id_from_header():
    """Testa extração de tenant_id do header X-Tenant-ID."""
    # Setup
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app=app,
        redis_client=AsyncMock(),
        settings=MagicMock(
            enable_rate_limiting=True,
            service_name="orchestrator-dynamic",
            rate_limit_default_capacity=100,
            rate_limit_default_refill_rate=10.0,
        ),
    )

    # Criar request mock com header X-Tenant-ID
    request = MagicMock(spec=Request)
    request.headers = {"X-Tenant-ID": "tenant_123"}

    # Act
    tenant_id = middleware._extract_tenant_id(request)

    # Assert
    assert tenant_id == "tenant_123"


@pytest.mark.asyncio
async def test_extract_tenant_id_missing_header():
    """Testa comportamento quando header X-Tenant-ID está ausente."""
    # Setup
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app=app,
        redis_client=AsyncMock(),
        settings=MagicMock(
            enable_rate_limiting=True,
            service_name="orchestrator-dynamic",
            rate_limit_default_capacity=100,
            rate_limit_default_refill_rate=10.0,
        ),
    )

    # Criar request mock sem header X-Tenant-ID
    request = MagicMock(spec=Request)
    request.headers = {}

    # Act
    tenant_id = middleware._extract_tenant_id(request)

    # Assert - deve retornar valor padrão
    assert tenant_id == "anonymous"


@pytest.mark.asyncio
async def test_extract_user_id_from_header():
    """Testa extração de user_id do header X-User-ID."""
    # Setup
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app=app,
        redis_client=AsyncMock(),
        settings=MagicMock(
            enable_rate_limiting=True,
            service_name="orchestrator-dynamic",
            rate_limit_default_capacity=100,
            rate_limit_default_refill_rate=10.0,
        ),
    )

    # Criar request mock com header X-User-ID
    request = MagicMock(spec=Request)
    request.headers = {"X-User-ID": "user_456"}

    # Act
    user_id = middleware._extract_user_id(request)

    # Assert
    assert user_id == "user_456"


@pytest.mark.asyncio
async def test_extract_user_id_missing_header():
    """Testa comportamento quando header X-User-ID está ausente."""
    # Setup
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app=app,
        redis_client=AsyncMock(),
        settings=MagicMock(
            enable_rate_limiting=True,
            service_name="orchestrator-dynamic",
            rate_limit_default_capacity=100,
            rate_limit_default_refill_rate=10.0,
        ),
    )

    # Criar request mock sem header X-User-ID
    request = MagicMock(spec=Request)
    request.headers = {}

    # Act
    user_id = middleware._extract_user_id(request)

    # Assert - deve retornar valor padrão
    assert user_id == "anonymous"


@pytest.mark.asyncio
async def test_extract_endpoint_from_request():
    """Testa extração de endpoint (method:path) da request."""
    # Setup
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app=app,
        redis_client=AsyncMock(),
        settings=MagicMock(
            enable_rate_limiting=True,
            service_name="orchestrator-dynamic",
            rate_limit_default_capacity=100,
            rate_limit_default_refill_rate=10.0,
        ),
    )

    # Criar request mock
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.url = MagicMock()
    request.url.path = "/api/v1/workflows"

    # Act
    endpoint = middleware._extract_endpoint(request)

    # Assert
    assert endpoint == "POST:/api/v1/workflows"


@pytest.mark.asyncio
async def test_build_rate_limit_key():
    """Testa construção da chave Redis para rate limiting."""
    # Setup
    app = FastAPI()
    middleware = RateLimitMiddleware(
        app=app,
        redis_client=AsyncMock(),
        settings=MagicMock(
            enable_rate_limiting=True,
            service_name="orchestrator-dynamic",
            rate_limit_default_capacity=100,
            rate_limit_default_refill_rate=10.0,
            rate_limit_redis_key_prefix="rate_limit",
        ),
    )

    # Act
    key = middleware._build_rate_limit_key(
        tenant_id="tenant_123",
        user_id="user_456",
        endpoint="POST:/api/v1/workflows",
    )

    # Assert - formato esperado: rate_limit:tenant_123:user_456:POST:/api/v1/workflows
    assert key == "rate_limit:tenant_123:user_456:POST:/api/v1/workflows"


# =============================================================================
# Testes do Middleware (1.2 - 1.7)
# =============================================================================


@pytest.mark.asyncio
async def test_middleware_allows_within_limit(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que requisição dentro do limite é permitida (1.4)."""
    # Setup
    mock_settings.enable_rate_limiting = True

    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    # Mock do limiter para retornar permitido
    with patch.object(middleware, "_check_rate_limit") as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=True,
            tokens_remaining=95,
            retry_after=0.0,
            reset_time=1743849600.0,
        )

        # Criar request
        request = MagicMock(spec=Request)
        request.headers = {
            "X-Tenant-ID": "tenant_123",
            "X-User-ID": "user_456",
        }
        request.method = "GET"
        request.url.path = "/api/v1/health"

        async def call_next(_req):
            return Response(content="OK", status_code=200)

        # Act
        response = await middleware.dispatch(request, call_next)

        # Assert - requisição permitida
        assert response.status_code == 200
        mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_middleware_denies_exceeds_limit(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que requisição excedendo limite retorna HTTP 429 (1.6)."""
    # Setup
    mock_settings.enable_rate_limiting = True

    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    # Mock do limiter para retornar negado
    with patch.object(middleware, "_check_rate_limit") as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=45.0,
            reset_time=1743849600.0,
        )

        # Criar request
        request = MagicMock(spec=Request)
        request.headers = {
            "X-Tenant-ID": "tenant_123",
            "X-User-ID": "user_456",
        }
        request.method = "POST"
        request.url.path = "/api/v1/workflows"

        # Mock call_next para verificar se foi chamado
        call_next_mock = AsyncMock(return_value=Response(content="OK", status_code=200))

        # Act
        response = await middleware.dispatch(request, call_next_mock)

        # Assert - requisição negada com 429
        assert response.status_code == 429
        # call_next NÃO deve ser chamado quando rate limit excedido
        call_next_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_different_users_separate_limits(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que usuários diferentes têm buckets independentes."""
    # Setup
    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    # Criar requests para usuários diferentes
    request1 = MagicMock(spec=Request)
    request1.headers = {"X-Tenant-ID": "tenant_123", "X-User-ID": "user_1"}
    request1.method = "GET"
    request1.url.path = "/api/v1/health"

    request2 = MagicMock(spec=Request)
    request2.headers = {"X-Tenant-ID": "tenant_123", "X-User-ID": "user_2"}
    request2.method = "GET"
    request2.url.path = "/api/v1/health"

    # Act - extrair chaves
    key1 = middleware._build_rate_limit_key(
        tenant_id="tenant_123",
        user_id="user_1",
        endpoint="GET:/api/v1/health",
    )
    key2 = middleware._build_rate_limit_key(
        tenant_id="tenant_123",
        user_id="user_2",
        endpoint="GET:/api/v1/health",
    )

    # Assert - chaves devem ser diferentes
    assert key1 != key2
    assert "user_1" in key1
    assert "user_2" in key2


@pytest.mark.asyncio
async def test_middleware_headers_added(app_instance, mock_redis_client, mock_settings):
    """Testa que headers RateLimit-* são adicionados nas respostas (1.5)."""
    # Setup
    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    with patch.object(middleware, "_check_rate_limit") as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=True,
            tokens_remaining=95,
            retry_after=0.0,
            reset_time=1743849600.0,
        )

        request = MagicMock(spec=Request)
        request.headers = {
            "X-Tenant-ID": "tenant_123",
            "X-User-ID": "user_456",
        }
        request.method = "GET"
        request.url.path = "/api/v1/health"

        async def call_next(_req):
            return Response(content="OK", status_code=200)

        # Act
        response = await middleware.dispatch(request, call_next)

        # Assert - headers presentes
        assert "RateLimit-Limit" in response.headers
        assert "RateLimit-Remaining" in response.headers
        assert "RateLimit-Reset" in response.headers
        assert response.headers["RateLimit-Remaining"] == "95"


@pytest.mark.asyncio
async def test_middleware_retry_after_calculated(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que Retry-After é calculado corretamente (1.6)."""
    # Setup
    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    with patch.object(middleware, "_check_rate_limit") as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=45.5,
            reset_time=1743849600.0,
        )

        request = MagicMock(spec=Request)
        request.headers = {
            "X-Tenant-ID": "tenant_123",
            "X-User-ID": "user_456",
        }
        request.method = "POST"
        request.url.path = "/api/v1/workflows"

        async def call_next(_req):
            return Response(content="OK", status_code=200)

        # Act
        response = await middleware.dispatch(request, call_next)

        # Assert - status 429 e Retry-After header
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert (
            response.headers["Retry-After"] == "46"
        )  # arredondado para cima (ceiling)


@pytest.mark.asyncio
async def test_middleware_disabled_when_flag_false(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que middleware é bypassado quando enable_rate_limiting=False."""
    # Setup
    mock_settings.enable_rate_limiting = False

    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    request = MagicMock(spec=Request)
    request.headers = {
        "X-Tenant-ID": "tenant_123",
        "X-User-ID": "user_456",
    }
    request.method = "GET"
    request.url.path = "/api/v1/health"

    call_next_called = False

    async def call_next(_req):
        nonlocal call_next_called
        call_next_called = True
        return Response(content="OK", status_code=200)

    # Act
    response = await middleware.dispatch(request, call_next)

    # Assert - request passa direto
    assert response.status_code == 200
    assert call_next_called
    assert "RateLimit-Limit" not in response.headers


# =============================================================================
# Testes de Integração com RateLimiterFactory
# =============================================================================


@pytest.mark.asyncio
async def test_middleware_uses_limiter_factory(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que middleware usa RateLimiterFactory para criar limiters."""
    # Setup
    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    # Assert - factory foi inicializada
    assert middleware.limiter_factory is not None
    assert middleware.limiter_factory.service_name == "orchestrator-dynamic"


@pytest.mark.asyncio
async def test_middleware_creates_per_key_limiters(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que limiters são criados por chave (cache)."""
    # Setup
    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    # Act - obter limiter para chave1
    key1 = "rate_limit:tenant_1:user_1:GET:/api/v1/health"
    limiter1 = middleware._get_or_create_limiter(
        key=key1, method="GET", path="/api/v1/health", tenant_id="tenant_1"
    )

    # Act - obter limiter para chave2 (diferente)
    key2 = "rate_limit:tenant_2:user_2:GET:/api/v1/health"
    limiter2 = middleware._get_or_create_limiter(
        key=key2, method="GET", path="/api/v1/health", tenant_id="tenant_2"
    )

    # Act - obter limiter para chave1 novamente (cache hit)
    limiter1_cached = middleware._get_or_create_limiter(
        key=key1, method="GET", path="/api/v1/health", tenant_id="tenant_1"
    )

    # Assert
    assert limiter1 is not None
    assert limiter2 is not None
    # Cache deve retornar mesma instância para mesma chave
    assert limiter1 is limiter1_cached
    # Mas instâncias diferentes para chaves diferentes
    assert limiter1 is not limiter2


# =============================================================================
# Testes de Logging
# =============================================================================


@pytest.mark.asyncio
async def test_middleware_logs_rate_limit_denied(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que middleware loga eventos de negação."""
    # Setup

    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    with patch.object(middleware, "_check_rate_limit") as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=45.0,
            reset_time=1743849600.0,
        )

        request = MagicMock(spec=Request)
        request.headers = {
            "X-Tenant-ID": "tenant_123",
            "X-User-ID": "user_456",
        }
        request.method = "POST"
        request.url.path = "/api/v1/workflows"

        async def call_next(_req):
            return Response(content="OK", status_code=200)

        # Act
        response = await middleware.dispatch(request, call_next)

        # Assert - status 429 indica log foi registrado
        assert response.status_code == 429


# =============================================================================
# Testes de JSON Response para 429
# =============================================================================


@pytest.mark.asyncio
async def test_middleware_returns_json_on_429(
    app_instance, mock_redis_client, mock_settings
):
    """Testa que resposta 429 contém JSON com detalhes."""
    # Setup
    middleware = RateLimitMiddleware(
        app=app_instance,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    with patch.object(middleware, "_check_rate_limit") as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=45.0,
            reset_time=1743849600.0,
        )

        request = MagicMock(spec=Request)
        request.headers = {
            "X-Tenant-ID": "tenant_123",
            "X-User-ID": "user_456",
        }
        request.method = "POST"
        request.url.path = "/api/v1/workflows"

        async def call_next(_req):
            return Response(content="OK", status_code=200)

        # Act
        response = await middleware.dispatch(request, call_next)

        # Assert
        assert response.status_code == 429
        assert "application/json" in response.headers.get("content-type", "")
