"""
Testes TDD para OPA Middleware FastAPI.

Siga o ciclo RED-GREEN-REFACTOR:
1. Escreva teste (RED - falha esperada)
2. Implemente código mínimo (GREEN - teste passa)
3. Refatore (REFACTOR - melhorias)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from neural_hive_opa import (
    OPAConfig,
    OPAAuthorizationMiddleware,
    OPADependency,
    OPAMiddlewareConfig,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_opa_client():
    """Mock do cliente OPA."""
    client = AsyncMock()
    client.initialize = AsyncMock()
    client.evaluate = AsyncMock(return_value={"allow": True})
    return client


@pytest.fixture
def fastapi_app(mock_opa_client):
    """FastAPI app com middleware OPA."""
    app = FastAPI()

    @app.get("/api/test")
    async def test_endpoint():
        return {"message": "test"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    # Adicionar middleware
    middleware = OPAAuthorizationMiddleware(
        app,
        opa_url="http://opa:8181",
        policy_path="neuralhive/authz",
    )
    # Substituir cliente interno com mock
    middleware._client = mock_opa_client
    middleware._initialized = True

    app.add_middleware(
        lambda app_next: type("Middleware", (), {"app_next": app_next, "dispatch": middleware.dispatch})()
    )

    return app


@pytest.fixture
def test_client(fastapi_app):
    """Test client FastAPI."""
    return TestClient(fastapi_app)


# =============================================================================
# Testes: MiddlewareConfig
# =============================================================================

class TestMiddlewareConfig:
    """Testes para OPAMiddlewareConfig."""

    def test_default_values(self):
        """
        DADO: Nenhum argumento fornecido
        QUANDO: Crio OPAMiddlewareConfig
        ENTÃO: Valores padrão devem ser usados
        """
        config = OPAMiddlewareConfig()

        assert config.opa_url == "http://localhost:8181"
        assert config.policy_path == "neuralhive/authz"
        assert config.timeout_seconds == 5
        assert config.cache_ttl_seconds == 300
        assert config.fail_open is False
        assert config.user_id_header == "X-User-ID"
        assert config.tenant_id_header == "X-Tenant-ID"
        assert config.role_header == "X-User-Role"

    def test_custom_values(self):
        """
        DADO: Valores customizados
        QUANDO: Crio OPAMiddlewareConfig com valores
        ENTÃO: Valores customizados devem ser usados
        """
        config = OPAMiddlewareConfig(
            opa_url="http://custom-opa:8181",
            policy_path="custom/policy",
            fail_open=True,
        )

        assert config.opa_url == "http://custom-opa:8181"
        assert config.policy_path == "custom/policy"
        assert config.fail_open is True


# =============================================================================
# Testes: Middleware Initialization
# =============================================================================

class TestMiddlewareInit:
    """Testes para inicialização do middleware."""

    def test_init_with_defaults(self):
        """
        DADO: App FastAPI
        QUANDO: Adiciono middleware com valores padrão
        ENTÃO: Middleware deve ser criado com config padrão
        """
        app = FastAPI()

        middleware = OPAAuthorizationMiddleware(app)

        assert middleware.config.opa_url == "http://localhost:8181"
        assert middleware.config.policy_path == "neuralhive/authz"

    def test_init_with_custom_config(self):
        """
        DADO: App FastAPI e config customizada
        QUANDO: Adiciono middleware com config
        ENTÃO: Middleware deve usar config fornecida
        """
        app = FastAPI()
        config = OPAMiddlewareConfig(
            opa_url="http://custom:8181",
            policy_path="custom/path",
        )

        middleware = OPAAuthorizationMiddleware(app, config=config)

        assert middleware.config.opa_url == "http://custom:8181"
        assert middleware.config.policy_path == "custom/path"

    def test_init_with_params(self):
        """
        DADO: App FastAPI
        QUANDO: Adiciono middleware com parâmetros diretos
        ENTÃO: Parâmetros devem sobrescrever defaults
        """
        app = FastAPI()

        middleware = OPAAuthorizationMiddleware(
            app,
            opa_url="http://override:8181",
            policy_path="override/path",
        )

        assert middleware.config.opa_url == "http://override:8181"
        assert middleware.config.policy_path == "override/path"


# =============================================================================
# Testes: Skip Paths
# =============================================================================

class TestSkipPaths:
    """Testes para paths que devem ser ignorados."""

    def test_health_check_skipped(self):
        """
        DADO: Requisição para /health
        QUANDO: Middleware processa requisição
        ENTÃO: Deve pular avaliação OPA
        """
        app = FastAPI()
        middleware = OPAAuthorizationMiddleware(app)

        assert middleware._should_skip_path("/health") is True
        assert middleware._should_skip_path("/healthz") is True
        assert middleware._should_skip_path("/ready") is True

    def test_metrics_skipped(self):
        """
        DADO: Requisição para /metrics
        QUANDO: Middleware processa requisição
        ENTÃO: Deve pular avaliação OPA
        """
        app = FastAPI()
        middleware = OPAAuthorizationMiddleware(app)

        assert middleware._should_skip_path("/metrics") is True

    def test_docs_skipped(self):
        """
        DADO: Requisição para docs
        QUANDO: Middleware processa requisição
        ENTÃO: Deve pular avaliação OPA
        """
        app = FastAPI()
        middleware = OPAAuthorizationMiddleware(app)

        assert middleware._should_skip_path("/docs") is True
        assert middleware._should_skip_path("/redoc") is True
        assert middleware._should_skip_path("/openapi.json") is True

    def test_api_path_not_skipped(self):
        """
        DADO: Requisição para API endpoint
        QUANDO: Middleware processa requisição
        ENTÃO: NÃO deve pular avaliação OPA
        """
        app = FastAPI()
        middleware = OPAAuthorizationMiddleware(app)

        assert middleware._should_skip_path("/api/test") is False
        assert middleware._should_skip_path("/api/v1/resource") is False


# =============================================================================
# Testes: OPA Input Building
# =============================================================================

class TestBuildOPAInput:
    """Testes para construção de input OPA."""

    @pytest.mark.asyncio
    async def test_build_input_with_headers(self):
        """
        DADO: Requisição com headers de contexto
        QUANDO: Construo input OPA
        ENTÃO: Input deve conter user info dos headers
        """
        app = FastAPI()
        middleware = OPAAuthorizationMiddleware(app, config=OPAMiddlewareConfig())

        # Criar request mock
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [
                (b"x-user-id", b"user123"),
                (b"x-tenant-id", b"tenant456"),
                (b"x-user-role", b"admin"),
            ],
        }
        request = Request(scope)

        opa_input = await middleware._build_opa_input(request)

        assert opa_input["user"]["id"] == "user123"
        assert opa_input["user"]["tenant_id"] == "tenant456"
        assert opa_input["user"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_build_input_with_request_info(self):
        """
        DADO: Requisição GET
        QUANDO: Construo input OPA
        ENTÃO: Input deve conter request info
        """
        app = FastAPI()
        middleware = OPAAuthorizationMiddleware(app, config=OPAMiddlewareConfig())

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/resource",
            "query_string": b"param1=value1",
            "headers": [],
        }
        request = Request(scope)

        opa_input = await middleware._build_opa_input(request)

        assert opa_input["request"]["method"] == "GET"
        assert opa_input["request"]["path"] == "/api/resource"
        assert opa_input["request"]["query_params"] == {"param1": "value1"}


# =============================================================================
# Testes: Authorization Decisions
# =============================================================================

class TestAuthorization:
    """Testes para decisões de autorização."""

    @pytest.mark.asyncio
    async def test_allowed_request(self):
        """
        DADO: OPA retorna allow=True
        QUANDO: Middleware processa requisição
        ENTÃO: Requisição deve ser permitida
        """
        app = FastAPI()

        @app.get("/api/test")
        async def test():
            return {"data": "test"}

        # Criar middleware com mock
        mock_client = AsyncMock()
        mock_client.evaluate = AsyncMock(return_value={"allow": True})
        mock_client.initialize = AsyncMock()

        middleware = OPAAuthorizationMiddleware(app, opa_url="http://opa:8181")
        middleware._client = mock_client
        middleware._initialized = True

        # Criar request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [],
            "app": app,
        }
        request = Request(scope)
        call_next = AsyncMock(return_value=Response(content=b"test"))

        # Executar middleware
        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 200
        mock_client.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_denied_request(self):
        """
        DADO: OPA retorna allow=False
        QUANDO: Middleware processa requisição
        ENTÃO: Requisição deve ser negada (403)
        """
        app = FastAPI()
        mock_client = AsyncMock()
        mock_client.evaluate = AsyncMock(
            return_value={"allow": False, "reason": "Insufficient permissions"}
        )
        mock_client.initialize = AsyncMock()

        middleware = OPAAuthorizationMiddleware(app, opa_url="http://opa:8181")
        middleware._client = mock_client
        middleware._initialized = True

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [],
            "app": app,
        }
        request = Request(scope)
        call_next = AsyncMock(return_value=Response(content=b"test"))

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 403
        assert b"Insufficient permissions" in response.body


# =============================================================================
# Testes: Error Handling
# =============================================================================

class TestErrorHandling:
    """Testes para tratamento de erros."""

    @pytest.mark.asyncio
    async def test_opa_connection_error_fail_closed(self):
        """
        DADO: Erro de conexão OPA e fail_open=False
        QUANDO: Middleware avalia requisição
        ENTÃO: Deve retornar 503 Service Unavailable
        """
        from neural_hive_opa.exceptions import OPAConnectionError

        app = FastAPI()
        mock_client = AsyncMock()
        mock_client.evaluate = AsyncMock(
            side_effect=OPAConnectionError("Connection failed")
        )
        mock_client.initialize = AsyncMock()

        middleware = OPAAuthorizationMiddleware(
            app, opa_url="http://opa:8181", config=OPAMiddlewareConfig(fail_open=False)
        )
        middleware._client = mock_client
        middleware._initialized = True

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [],
            "app": app,
        }
        request = Request(scope)
        call_next = AsyncMock(return_value=Response(content=b"test"))

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 503
        assert b"Authorization service unavailable" in response.body

    @pytest.mark.asyncio
    async def test_opa_connection_error_fail_open(self):
        """
        DADO: Erro de conexão OPA e fail_open=True
        QUANDO: Middleware avalia requisição
        ENTÃO: Deve permitir requisição (continuar para next)
        """
        from neural_hive_opa.exceptions import OPAConnectionError

        app = FastAPI()
        mock_client = AsyncMock()
        mock_client.evaluate = AsyncMock(
            side_effect=OPAConnectionError("Connection failed")
        )
        mock_client.initialize = AsyncMock()

        middleware = OPAAuthorizationMiddleware(
            app, opa_url="http://opa:8181", config=OPAMiddlewareConfig(fail_open=True)
        )
        middleware._client = mock_client
        middleware._initialized = True

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [],
            "app": app,
        }
        request = Request(scope)
        call_next = AsyncMock(return_value=Response(content=b"test"))

        response = await middleware.dispatch(request, call_next)

        # Em fail_open, deve chamar call_next
        call_next.assert_called_once()


# =============================================================================
# Testes: OPADependency
# =============================================================================

class TestOPADependency:
    """Testes para OPADependency."""

    def test_init(self):
        """
        DADO: Nenhum argumento
        QUANDO: Crio OPADependency
        ENTÃO: Deve usar valores padrão
        """
        dep = OPADependency()

        assert dep.opa_url == "http://localhost:8181"
        assert dep.policy_path == "neuralhive/authz"
        assert dep.fail_open is False

    def test_init_with_params(self):
        """
        DADO: Parâmetros customizados
        QUANDO: Crio OPADependency
        ENTÃO: Deve usar parâmetros fornecidos
        """
        dep = OPADependency(
            opa_url="http://custom:8181",
            policy_path="custom/path",
            fail_open=True,
        )

        assert dep.opa_url == "http://custom:8181"
        assert dep.policy_path == "custom/path"
        assert dep.fail_open is True

    @pytest.mark.asyncio
    async def test_call_allowed(self):
        """
        DADO: OPA retorna allow=True
        QUANDO: Chamo dependency
        ENTÃO: Deve retornar resultado da avaliação
        """
        from fastapi import HTTPException

        dep = OPADependency(opa_url="http://opa:8181")

        # Mock client
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock()
        mock_client.evaluate = AsyncMock(return_value={"allow": True, "decision_id": "123"})
        dep._client = mock_client

        # Criar request mock
        app = FastAPI()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [],
            "app": app,
        }
        request = Request(scope)

        result = await dep(request)

        assert result["allow"] is True
        assert result["decision_id"] == "123"

    @pytest.mark.asyncio
    async def test_call_denied(self):
        """
        DADO: OPA retorna allow=False
        QUANDO: Chamo dependency
        ENTÃO: Deve levantar HTTPException 403
        """
        from fastapi import HTTPException

        dep = OPADependency(opa_url="http://opa:8181")

        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock()
        mock_client.evaluate = AsyncMock(return_value={"allow": False, "reason": "Denied"})
        dep._client = mock_client

        app = FastAPI()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": "",
            "headers": [],
            "app": app,
        }
        request = Request(scope)

        with pytest.raises(HTTPException) as exc:
            await dep(request)

        assert exc.value.status_code == 403
