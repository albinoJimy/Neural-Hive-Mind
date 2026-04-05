"""
Testes de integração para RateLimitMiddleware com FastAPI app.

Task 6.1: Testar integração completa do middleware com a aplicação FastAPI.
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
def mock_settings():
    """Mock das configurações com rate limiting habilitado."""
    return MagicMock(
        spec=OrchestratorSettings,
        enable_rate_limiting=True,
        rate_limit_default_capacity=10,
        rate_limit_default_refill_rate=1.0,
        rate_limit_burst_multiplier=2.0,
        rate_limit_tier_limits={},
        rate_limit_redis_key_prefix="rate_limit",
        service_name="orchestrator-dynamic",
    )


@pytest.fixture
def mock_settings_disabled():
    """Mock das configurações com rate limiting desabilitado."""
    return MagicMock(
        spec=OrchestratorSettings,
        enable_rate_limiting=False,
        rate_limit_default_capacity=10,
        rate_limit_default_refill_rate=1.0,
        rate_limit_burst_multiplier=2.0,
        rate_limit_tier_limits={},
        rate_limit_redis_key_prefix="rate_limit",
        service_name="orchestrator-dynamic",
    )


@pytest.fixture
def mock_redis_client():
    """Mock do cliente Redis."""
    return AsyncMock()


@pytest.fixture
def app_with_rate_limit(mock_settings, mock_redis_client):
    """
    Cria app FastAPI com RateLimitMiddleware habilitado.

    Simula a integração que será feita em main.py.
    """
    app = FastAPI(title="Test App with Rate Limit")

    # Adicionar middleware
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis_client,
        settings=mock_settings,
    )

    @app.get("/api/v1/test")
    async def test_endpoint():
        return Response(content="OK", status_code=200)

    @app.post("/api/v1/workflows")
    async def create_workflow():
        return Response(content='{"workflow_id": "123"}', status_code=201)

    @app.get("/health")
    async def health():
        return Response(content="healthy", status_code=200)

    return app


@pytest.fixture
def app_without_rate_limit(mock_settings_disabled, mock_redis_client):
    """
    Cria app FastAPI com RateLimitMiddleware desabilitado.
    """
    app = FastAPI(title="Test App without Rate Limit")

    # Adicionar middleware (mas desabilitado via settings)
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=mock_redis_client,
        settings=mock_settings_disabled,
    )

    @app.get("/api/v1/test")
    async def test_endpoint():
        return Response(content="OK", status_code=200)

    return app


# =============================================================================
# Testes de Integração
# =============================================================================


@pytest.mark.asyncio
async def test_middleware_integration_allows_request(app_with_rate_limit):
    """Testa que request permitida passa pelo middleware."""
    # Patch _check_rate_limit para retornar permitido
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=True,
            tokens_remaining=9,
            retry_after=0.0,
            reset_time=1743849600.0,
        )

        # Criar TestClient
        with TestClient(app_with_rate_limit) as client:
            response = client.get(
                "/api/v1/test",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )

            # Assert - requisição permitida
            assert response.status_code == 200
            assert response.content == b"OK"


@pytest.mark.asyncio
async def test_middleware_integration_denies_request(app_with_rate_limit):
    """Testa que request negada retorna HTTP 429."""
    # Patch _check_rate_limit para retornar negado
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=45.0,
            reset_time=1743849600.0,
        )

        # Criar TestClient
        with TestClient(app_with_rate_limit) as client:
            response = client.post(
                "/api/v1/workflows",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )

            # Assert - requisição negada
            assert response.status_code == 429
            assert "rate_limit_exceeded" in response.json()["error"]


@pytest.mark.asyncio
async def test_middleware_integration_bypassed_when_disabled(app_without_rate_limit):
    """Testa que middleware é bypassado quando enable_rate_limiting=False (6.5)."""
    # Criar TestClient
    with TestClient(app_without_rate_limit) as client:
        # Fazer muitas requests - nenhuma deve ser limitada
        for _ in range(20):
            response = client.get(
                "/api/v1/test",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )
            # Assert - todas as requests devem passar
            assert response.status_code == 200
            # Sem headers de rate limit
            assert "RateLimit-Limit" not in response.headers


@pytest.mark.asyncio
async def test_middleware_integration_rate_limit_headers(app_with_rate_limit):
    """Testa que headers RateLimit-* são adicionados nas respostas."""
    # Patch _check_rate_limit para retornar permitido
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=True,
            tokens_remaining=7,
            retry_after=0.0,
            reset_time=1743849600.0,
        )

        # Criar TestClient
        with TestClient(app_with_rate_limit) as client:
            response = client.get(
                "/health",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )

            # Assert - headers presentes
            assert "RateLimit-Limit" in response.headers
            assert "RateLimit-Remaining" in response.headers
            assert "RateLimit-Reset" in response.headers
            assert response.headers["RateLimit-Remaining"] == "7"


@pytest.mark.asyncio
async def test_middleware_integration_anonymous_user(app_with_rate_limit):
    """Testa que requisições sem headers usam valores padrão."""
    # Patch _check_rate_limit para retornar permitido
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=True,
            tokens_remaining=9,
            retry_after=0.0,
            reset_time=1743849600.0,
        )

        # Criar TestClient
        with TestClient(app_with_rate_limit) as client:
            # Request sem headers
            response = client.get("/health")

            # Assert - requisição permitida (anonymous)
            assert response.status_code == 200
            # Verificar que _check_rate_limit foi chamado com anonymous
            mock_check.assert_called_once()
            call_args = mock_check.call_args
            # A chave deve conter "anonymous"
            key = call_args[1]["key"]  # keyword argument "key"
            assert "anonymous" in key


@pytest.mark.asyncio
async def test_middleware_integration_different_endpoints_separate_keys(
    app_with_rate_limit,
):
    """Testa que endpoints diferentes têm chaves separadas."""
    # Patch _check_rate_limit
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=True,
            tokens_remaining=9,
            retry_after=0.0,
            reset_time=1743849600.0,
        )

        # Criar TestClient
        with TestClient(app_with_rate_limit) as client:
            # Request para endpoint 1
            response1 = client.get(
                "/health",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )
            assert response1.status_code == 200

            # Request para endpoint 2 (retorna 201 Created)
            response2 = client.post(
                "/api/v1/workflows",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )
            assert response2.status_code == 201

            # Assert - _check_rate_limit chamado 2 vezes com chaves diferentes
            assert mock_check.call_count == 2

            # Extrair chaves das chamadas
            call1_key = mock_check.call_args_list[0][1]["key"]
            call2_key = mock_check.call_args_list[1][1]["key"]

            # Chaves devem ser diferentes
            assert call1_key != call2_key
            assert "GET:/health" in call1_key
            assert "POST:/api/v1/workflows" in call2_key


@pytest.mark.asyncio
async def test_middleware_integration_retry_after_header(app_with_rate_limit):
    """Testa que header Retry-After está presente em HTTP 429."""
    # Patch _check_rate_limit para retornar negado
    with patch(
        "src.middleware.rate_limit_middleware.RateLimitMiddleware._check_rate_limit"
    ) as mock_check:
        mock_check.return_value = RateLimitResult(
            allowed=False,
            tokens_remaining=0,
            retry_after=60.5,
            reset_time=1743849600.0,
        )

        # Criar TestClient
        with TestClient(app_with_rate_limit) as client:
            response = client.get(
                "/api/v1/test",
                headers={"X-Tenant-ID": "tenant_123", "X-User-ID": "user_456"},
            )

            # Assert
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            # 60.5 é arredondado para 61 (int() não floor, mas round para cima)
            assert response.headers["Retry-After"] == "61"

            # Verificar body da resposta
            body = response.json()
            assert body["error"] == "rate_limit_exceeded"
            assert "61" in body["message"]
            assert body["retry_after"] == 61
