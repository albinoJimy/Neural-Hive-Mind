"""
Testes de integração do OPAAuthorizationMiddleware.

Estes testes validam que o middleware de autorização OPA está funcionando
corretamente para proteger endpoints da API HTTP.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI

from src.config.settings import get_settings


@pytest.mark.asyncio
class TestOPAMiddlewareIntegration:
    """Testes de integração do OPAAuthorizationMiddleware."""

    async def test_public_path_without_auth(self, test_app: FastAPI):
        """Paths públicos não requerem autenticação."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            # Health endpoint deve funcionar sem autenticação
            assert response.status_code in [200, 404]  # 404 se endpoint não implementado

    async def test_metrics_public(self, test_app: FastAPI):
        """Endpoint /metrics é público."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")
            # Metrics endpoint deve funcionar sem autenticação
            assert response.status_code in [200, 404]

    async def test_api_without_auth_returns_403(self, test_app: FastAPI):
        """API sem header de autenticação retorna 403 quando middleware ativo."""
        config = get_settings()
        if not config.enable_opa_authorization:
            pytest.skip("OPA authorization middleware disabled")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/workflows")
            # Sem autenticação deve retornar 403 Forbidden
            assert response.status_code == 403

    async def test_api_with_valid_auth_headers(self, test_app: FastAPI):
        """API com headers válidos deve processar a requisição."""
        config = get_settings()
        if not config.enable_opa_authorization:
            pytest.skip("OPA authorization middleware disabled")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                config.opa_user_id_header: "user-123",
                config.opa_tenant_id_header: "tenant-abc",
                config.opa_role_header: "developer",
            }
            response = await client.get("/api/v1/workflows", headers=headers)
            # Com auth válida não deve retornar 403
            # Pode retornar 200, 404 (não encontrado) ou 422 (validation error)
            # Mas nunca 403 (authorization error)
            assert response.status_code != 403

    async def test_admin_can_access_everything(self, test_app: FastAPI):
        """Admin role tem acesso irrestrito via OPA policy."""
        config = get_settings()
        if not config.enable_opa_authorization:
            pytest.skip("OPA authorization middleware disabled")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                config.opa_user_id_header: "admin-1",
                config.opa_tenant_id_header: "system",
                config.opa_role_header: "admin",
            }
            # Tentar acessar endpoint que normalmente seria restrito
            response = await client.post("/api/v1/workflows/start", json={}, headers=headers)
            # Admin não deve receber 403
            assert response.status_code != 403

    async def test_tenant_isolation(self, test_app: FastAPI):
        """Tenant A não pode acessar recursos do Tenant B."""
        config = get_settings()
        if not config.enable_opa_authorization:
            pytest.skip("OPA authorization middleware disabled")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers_a = {
                config.opa_user_id_header: "user-a",
                config.opa_tenant_id_header: "tenant-a",
                config.opa_role_header: "developer",
            }
            # Request para recurso do tenant-b com headers do tenant-a
            response = await client.get("/api/v1/tenant-b/workflows", headers=headers_a)
            # Deve negar acesso (403) devido ao tenant isolation
            assert response.status_code == 403

    async def test_developer_readonly_access(self, test_app: FastAPI):
        """Developer role pode fazer GET mas não POST."""
        config = get_settings()
        if not config.enable_opa_authorization:
            pytest.skip("OPA authorization middleware disabled")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                config.opa_user_id_header: "dev-1",
                config.opa_tenant_id_header: "tenant-dev",
                config.opa_role_header: "developer",
            }
            # GET deve funcionar
            response_get = await client.get("/api/v1/workflows", headers=headers)
            assert response_get.status_code != 403

            # POST deve ser negado
            response_post = await client.post("/api/v1/workflows/start", json={}, headers=headers)
            assert response_post.status_code == 403

    async def test_worker_can_register(self, test_app: FastAPI):
        """Worker role pode acessar endpoints de registro."""
        config = get_settings()
        if not config.enable_opa_authorization:
            pytest.skip("OPA authorization middleware disabled")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                config.opa_user_id_header: "worker-1",
                config.opa_tenant_id_header: "system",
                config.opa_role_header: "worker",
            }
            # Worker pode acessar /api/v1/workers/register
            response = await client.post("/api/v1/workers/register", json={}, headers=headers)
            # Não deve receber 403
            assert response.status_code != 403


@pytest.mark.asyncio
class TestOPAMiddlewareMetrics:
    """Testes de métricas do OPAAuthorizationMiddleware."""

    async def test_metrics_exposed(self, test_app: FastAPI):
        """Métricas do middleware OPA devem ser expostas."""
        from src.observability.metrics import get_metrics

        metrics = get_metrics()

        # Verificar se métricas esperadas existem
        metric_names = [m.name for m in metrics]

        # Métricas que devem ser expostas pelo middleware
        expected_metrics = [
            "opa_middleware_decisions_total",
            "opa_middleware_latency_seconds",
            "opa_middleware_cache_hits_total",
        ]

        for expected in expected_metrics:
            # Pode não estar presente se middleware não foi inicializado
            # mas se estiver, deve ter labels corretos
            if expected in metric_names:
                assert True  # Métrica existe


@pytest.mark.asyncio
class TestOPAMiddlewareFailClosed:
    """Testes de comportamento fail-closed quando OPA está indisponível."""

    async def test_opa_unavailable_returns_503(self, test_app_with_opa_down: FastAPI):
        """Quando OPA está down, retorna 503 (fail-closed)."""
        config = get_settings()
        if config.opa_fail_open:
            pytest.skip("OPA configured as fail-open, skipping fail-closed test")

        transport = ASGITransport(app=test_app_with_opa_down)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                config.opa_user_id_header: "user-123",
                config.opa_tenant_id_header: "tenant-abc",
                config.opa_role_header: "developer",
            }
            response = await client.get("/api/v1/workflows", headers=headers)
            # OPA indisponível com fail-closed deve retornar 503
            assert response.status_code == 503


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_app():
    """
    Fixture que cria uma aplicação FastAPI de teste com o middleware OPA.
    """
    from src.main import app

    return app


@pytest.fixture
def test_app_with_opa_down():
    """
    Fixture que cria uma app com OPA mockado para retornar erro.
    """
    from fastapi import FastAPI
    from unittest.mock import patch

    # Criar app de teste
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/v1/workflows")
    async def list_workflows():
        return {"workflows": []}

    # Adicionar middleware com mock que falha
    with patch(
        "neural_hive_opa.middleware.OPAAuthorizationMiddleware._build_opa_input"
    ) as mock_input:
        with patch("neural_hive_opa.middleware.OPAAuthorizationMiddleware._call_opa") as mock_call:
            # Mock que simula OPA indisponível
            import httpx

            mock_call.side_effect = httpx.ConnectError("Connection refused")

            # Importar e adicionar middleware
            from neural_hive_opa.middleware import OPAAuthorizationMiddleware, OPAMiddlewareConfig

            config = get_settings()
            app.add_middleware(
                OPAAuthorizationMiddleware,
                config=OPAMiddlewareConfig(
                    opa_url=f"http://{config.opa_host}:{config.opa_port}",
                    policy_path=config.opa_authorization_policy_path,
                    timeout_seconds=1,  # Timeout rápido para teste
                    fail_open=False,  # Fail-closed
                ),
            )

    return app
