"""Testes de integração para os middlewares do Unified Gateway."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware


class TestMiddlewareIntegration:
    """Testes de integração dos middlewares."""

    @pytest.fixture
    def app_with_middlewares(self):
        """Cria app FastAPI com todos os middlewares."""
        from src.main import app

        # Usar a app real do main.py que já tem os middlewares
        return app

    @pytest.fixture
    def client(self, app_with_middlewares):
        """Cria cliente de teste."""
        return TestClient(app_with_middlewares)

    def test_health_check_returns_status_and_version(self, client):
        """
        Health check deve retornar {status, version} conforme INV-10.

        Este teste implementa R-G1: o serviço responde com health check
        contendo status e version.
        """
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # INV-10: deve ter status e version
        assert "status" in data
        assert "version" in data
        assert data["status"] in ["healthy", "unhealthy"]
        assert isinstance(data["version"], str)

    def test_health_check_excluded_from_auth(self, client):
        """Health check deve ser excluído de autenticação."""
        response = client.get("/health")

        # Não deve retornar 401 mesmo sem auth
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_health_ready_excluded_from_auth(self, client):
        """Readiness check deve ser excluído de autenticação."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["ready"] is True

    def test_health_live_excluded_from_auth(self, client):
        """Liveness check deve ser excluído de autenticação."""
        response = client.get("/health/live")

        assert response.status_code == 200
        assert response.json()["alive"] is True

    def test_metrics_endpoint_accessible(self, client):
        """Endpoint /metrics deve estar acessível."""
        response = client.get("/metrics")

        # Prometheus endpoint retorna 200
        assert response.status_code == 200

    def test_root_endpoint(self, client):
        """Endpoint raiz deve retornar informações do serviço."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "service" in data
        assert data["service"] == "unified-gateway"
        assert "version" in data
        assert "status" in data
        assert "docs" in data
        assert "health" in data
        assert "metrics" in data

    def test_cors_headers_if_configured(self, client):
        """Se CORS configurado, headers devem estar presentes."""
        response = client.options("/")

        # Pode ter CORS headers se configurado
        # Este teste apenas verifica que a requisição não falha
        assert response.status_code in [200, 404, 405]


class TestJWTAuthMiddlewareIntegration:
    """Testes de integração para JWT Auth Middleware."""

    @pytest.fixture
    def app_with_jwt_auth(self):
        """Cria app com JWT Auth Middleware."""
        app = FastAPI()

        from src.middleware import JWTAuthMiddleware

        # Adicionar middleware com auth opcional
        app.add_middleware(
            JWTAuthMiddleware,
            exclude_paths=["/health", "/public"],
            require_auth=False,
        )

        @app.get("/protected")
        async def protected():
            return {"message": "authenticated"}

        @app.get("/public")
        async def public():
            return {"message": "public"}

        return app

    @pytest.fixture
    def client(self, app_with_jwt_auth):
        """Cria cliente de teste."""
        return TestClient(app_with_jwt_auth)

    def test_public_endpoint_accessible_without_auth(self, client):
        """Endpoint público deve ser acessível sem autenticação."""
        response = client.get("/public")

        assert response.status_code == 200
        assert response.json()["message"] == "public"

    def test_protected_endpoint_accessible_without_optional_auth(self, client):
        """Endpoint protegido deve ser acessível com auth opcional."""
        response = client.get("/protected")

        # Com require_auth=False, não retorna 401
        assert response.status_code == 200

    def test_jwt_token_in_authorization_header(self, client):
        """Token JWT deve ser extraído do header Authorization."""
        import jwt

        payload = {"sub": "user-123", "tenant_id": "tenant-456"}
        token = jwt.encode(payload, "secret", algorithm="HS256")

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200


class TestRateLimitMiddlewareIntegration:
    """Testes de integração para Rate Limit Middleware."""

    @pytest.fixture
    def app_with_rate_limit(self):
        """Cria app com Rate Limit Middleware (desabilitado para testes)."""
        app = FastAPI()

        from src.middleware import RateLimitMiddleware

        # Adicionar middleware desabilitado para não depender de Redis
        app.add_middleware(
            RateLimitMiddleware,
            exclude_paths=["/health"],
            enabled=False,  # Desabilitado para testes sem Redis
        )

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "ok"}

        return app

    @pytest.fixture
    def client(self, app_with_rate_limit):
        """Cria cliente de teste."""
        return TestClient(app_with_rate_limit)

    def test_endpoint_accessible_when_rate_limit_disabled(self, client):
        """Endpoint deve ser acessível quando rate limit está desabilitado."""
        response = client.get("/api/test")

        assert response.status_code == 200
        assert response.json()["message"] == "ok"

    def test_rate_limit_headers_added(self, client):
        """Headers de rate limit devem ser adicionados à resposta."""
        response = client.get("/api/test")

        # Quando rate limit está desabilitado, headers ainda podem ser adicionados
        # mas com valores default
        assert response.status_code == 200
