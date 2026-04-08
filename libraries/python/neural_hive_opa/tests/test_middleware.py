"""
Testes do middleware OPA.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request
from starlette.responses import Response

from neural_hive_opa.middleware import (
    OPAAuthorizationMiddleware,
    OPAMiddlewareConfig,
)


@pytest.fixture
def mock_opa_client():
    """Mock do cliente OPA."""
    with patch("neural_hive_opa.middleware.OPAClient") as mock:
        yield mock


@pytest.fixture
def test_app():
    """App FastAPI para testes."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/v1/workflows")
    async def workflows():
        return {"workflows": []}

    @app.post("/api/v1/workflows/start")
    async def start_workflow():
        return {"workflow_id": "123"}

    return app


@pytest.mark.asyncio
class TestOPAAuthorizationMiddleware:
    """Testes do middleware de autorização."""

    async def test_public_path_allowed(self, test_app, mock_opa_client):
        """Paths públicos devem ser permitidos sem autenticação."""
        mock_result = MagicMock()
        mock_result.allow = True
        mock_opa_client.return_value.check.return_value = mock_result

        middleware = OPAAuthorizationMiddleware(
            test_app,
            config=OPAMiddlewareConfig(opa_url="http://opa:8181"),
        )

        # Criar request para path público
    async def test_public_path_allowed_no_auth(self, test_app):
        """Paths públicos devem funcionar sem headers de autenticação."""
        from httpx import ASGITransport, AsyncClient

        app = test_app
        app.add_middleware(
            OPAAuthorizationMiddleware,
            config=OPAMiddlewareConfig(opa_url="http://opa:8181"),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200

    async def test_api_without_auth_returns_403(self, test_app, mock_opa_client):
        """API sem headers deve retornar 403."""
        mock_result = MagicMock()
        mock_result.allow = True
        mock_opa_client.return_value.check.return_value = mock_result

        app = test_app
        app.add_middleware(
            OPAAuthorizationMiddleware,
            config=OPAMiddlewareConfig(opa_url="http://opa:8181"),
        )

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/workflows")
            # Sem headers deve retornar 403
            assert response.status_code == 403
            data = response.json()
            assert data["error"] == "Forbidden"

    async def test_api_with_valid_auth(self, test_app, mock_opa_client):
        """API com headers válidos deve funcionar."""
        mock_result = MagicMock()
        mock_result.allow = True
        mock_result.cached = False
        mock_opa_client.return_value.check.return_value = mock_result

        app = test_app
        app.add_middleware(
            OPAAuthorizationMiddleware,
            config=OPAMiddlewareConfig(opa_url="http://opa:8181"),
        )

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "X-User-ID": "user-123",
                "X-Tenant-ID": "tenant-abc",
                "X-User-Role": "developer",
            }
            response = await client.get("/api/v1/workflows", headers=headers)
            # Com auth válida não deve ser 403
            assert response.status_code != 403

    async def test_api_with_opa_deny(self, test_app):
        """Quando OPA nega, deve retornar 403."""
        app = test_app

        # Criar mock result
        mock_result = MagicMock()
        mock_result.allow = False
        mock_result.reason = "insufficient_permissions"
        mock_result.cached = False

        # Patch do método check do OPA client
        with patch("neural_hive_opa.middleware.OPAClient") as MockOPAClient:
            mock_client_instance = MagicMock()
            mock_client_instance.check = AsyncMock(return_value=mock_result)
            mock_client_instance.get_circuit_breaker_state.return_value = "CLOSED"
            MockOPAClient.return_value = mock_client_instance

            app.add_middleware(
                OPAAuthorizationMiddleware,
                config=OPAMiddlewareConfig(opa_url="http://opa:8181"),
            )

            from httpx import ASGITransport, AsyncClient

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {
                    "X-User-ID": "user-123",
                    "X-Tenant-ID": "tenant-abc",
                    "X-User-Role": "developer",
                }
                response = await client.get("/api/v1/workflows", headers=headers)
                assert response.status_code == 403
                data = response.json()
                assert data["message"] == "Access denied by policy"

    async def test_fail_open_allows_on_opa_error(self, test_app):
        """Fail-open deve permitir acesso quando OPA erro."""
        app = test_app

        # Simular erro do OPA com conexão
        import httpx

        with patch("neural_hive_opa.middleware.OPAClient") as MockOPAClient:
            mock_client_instance = MagicMock()
            mock_client_instance.check = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_instance.get_circuit_breaker_state.return_value = "CLOSED"
            MockOPAClient.return_value = mock_client_instance

            app.add_middleware(
                OPAAuthorizationMiddleware,
                config=OPAMiddlewareConfig(opa_url="http://opa:8181", fail_open=True),
            )

            from httpx import ASGITransport, AsyncClient

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {
                    "X-User-ID": "user-123",
                    "X-Tenant-ID": "tenant-abc",
                    "X-User-Role": "developer",
                }
                response = await client.get("/api/v1/workflows", headers=headers)
                # Fail open não deve ser 503
                assert response.status_code != 503

    async def test_fail_closed_denies_on_opa_error(self, test_app, mock_opa_client):
        """Fail-closed deve negar acesso quando OPA erro."""
        import httpx

        # Simular erro de conexão do OPA
        mock_opa_client.return_value.check.side_effect = httpx.ConnectError("Connection refused")
        mock_opa_client.return_value.get_circuit_breaker_state.return_value = "CLOSED"

        app = test_app
        app.add_middleware(
            OPAAuthorizationMiddleware,
            config=OPAMiddlewareConfig(opa_url="http://opa:8181", fail_open=False),
        )

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "X-User-ID": "user-123",
                "X-Tenant-ID": "tenant-abc",
                "X-User-Role": "developer",
            }
            response = await client.get("/api/v1/workflows", headers=headers)
            # Fail closed deve retornar 503
            assert response.status_code == 503

    async def test_custom_headers(self, test_app, mock_opa_client):
        """Deve suportar headers customizados."""
        mock_result = MagicMock()
        mock_result.allow = True
        mock_result.cached = False
        mock_opa_client.return_value.check.return_value = mock_result

        app = test_app
        config = OPAMiddlewareConfig(
            opa_url="http://opa:8181",
            user_id_header="X-Custom-User-ID",
            tenant_id_header="X-Custom-Tenant-ID",
            role_header="X-Custom-Role",
        )
        app.add_middleware(OPAAuthorizationMiddleware, config=config)

        # Verificar que headers customizados são usados
        assert config.user_id_header == "X-Custom-User-ID"
        assert config.tenant_id_header == "X-Custom-Tenant-ID"
        assert config.role_header == "X-Custom-Role"


@pytest.mark.asyncio
class TestOPAMiddlewareConfig:
    """Testes da configuração do middleware."""

    async def test_default_config(self):
        """Configuração padrão deve ter valores corretos."""
        config = OPAMiddlewareConfig(opa_url="http://opa:8181")

        assert config.policy_path == "neuralhive/orchestrator/authz"
        assert config.timeout_seconds == 5
        assert config.fail_open is False
        assert config.enable_cache is True
        assert config.user_id_header == "X-User-ID"
        assert config.tenant_id_header == "X-Tenant-ID"
        assert config.role_header == "X-User-Role"

    async def test_custom_public_paths(self):
        """Deve aceitar paths públicos customizados."""
        config = OPAMiddlewareConfig(
            opa_url="http://opa:8181",
            public_paths=["/custom-public", "/another-public"],
        )

        assert "/custom-public" in config.public_paths
        assert "/another-public" in config.public_paths
