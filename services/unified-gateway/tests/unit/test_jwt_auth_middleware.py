"""Testes unitários para JWT Auth Middleware."""

import pytest
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.middleware.jwt_auth import (
    AuthContext,
    AuthMethod,
    JWTAuthMiddleware,
    JWTAuthError,
    get_auth_context,
)


@pytest.fixture
def jwt_middleware():
    """Retorna instância do middleware JWT."""

    def dummy_app(scope, receive, send):
        pass

    return JWTAuthMiddleware(
        app=dummy_app,
        exclude_paths=["/health", "/metrics"],
        require_auth=False,  # Auth opcional para testes
    )


class TestAuthContext:
    """Testes para AuthContext."""

    def test_auth_context_creation(self):
        """AuthContext deve ser criado com valores padrão."""
        ctx = AuthContext(authenticated=False)
        assert ctx.authenticated is False
        assert ctx.user_id is None
        assert ctx.tenant_id is None
        assert ctx.auth_method == AuthMethod.NONE

    def test_auth_context_with_values(self):
        """AuthContext deve aceitar valores fornecidos."""
        ctx = AuthContext(
            authenticated=True,
            user_id="user-123",
            tenant_id="tenant-456",
            session_id="session-789",
            auth_method=AuthMethod.JWT,
            roles=["user", "admin"],
            permissions=["read", "write"],
        )
        assert ctx.authenticated is True
        assert ctx.user_id == "user-123"
        assert ctx.tenant_id == "tenant-456"
        assert ctx.session_id == "session-789"
        assert ctx.auth_method == AuthMethod.JWT
        assert ctx.roles == ["user", "admin"]
        assert ctx.permissions == ["read", "write"]

    def test_auth_context_get_headers(self):
        """AuthContext deve gerar headers corretamente (INV-7)."""
        ctx = AuthContext(
            authenticated=True,
            user_id="user-123",
            tenant_id="tenant-456",
            session_id="session-789",
            auth_method=AuthMethod.JWT,
            roles=["user", "admin"],
        )

        headers = ctx.get_headers()

        # Verificar headers obrigatórios
        assert headers["X-Auth-Method"] == "jwt"
        assert headers["X-Authenticated"] == "true"
        assert headers["X-User-ID"] == "user-123"
        assert headers["X-Tenant-ID"] == "tenant-456"
        assert headers["X-Session-ID"] == "session-789"
        assert headers["X-User-Roles"] == "user,admin"

    def test_auth_context_get_headers_minimal(self):
        """AuthContext deve gerar headers mesmo com valores mínimos."""
        ctx = AuthContext(authenticated=True, user_id="user-123")

        headers = ctx.get_headers()

        assert headers["X-Auth-Method"] == "none"
        assert headers["X-Authenticated"] == "true"
        assert headers["X-User-ID"] == "user-123"
        assert "X-Tenant-ID" not in headers  # Não presente, não adiciona
        assert "X-Session-ID" not in headers


class TestJWTAuthMiddleware:
    """Testes para JWTAuthMiddleware."""

    def test_should_skip_auth(self, jwt_middleware):
        """Middleware deve pular auth para paths excluídos."""
        assert jwt_middleware._should_skip_auth("/health") is True
        assert jwt_middleware._should_skip_auth("/metrics") is True
        assert jwt_middleware._should_skip_auth("/api/test") is False

    def test_should_not_skip_auth(self, jwt_middleware):
        """Middleware não deve pular auth para paths não excluídos."""
        assert jwt_middleware._should_skip_auth("/api/v1/request") is False
        assert jwt_middleware._should_skip_auth("/admin") is False

    @pytest.mark.asyncio
    async def test_extract_auth_context_no_header(self, jwt_middleware):
        """Deve retornar AuthContext não autenticado sem header."""
        # Criar request mock
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [],
        }
        request = Request(scope)

        ctx = await jwt_middleware._extract_auth_context(request)

        assert ctx.authenticated is False
        assert ctx.auth_method == AuthMethod.NONE

    @pytest.mark.asyncio
    async def test_extract_auth_context_invalid_format(self, jwt_middleware):
        """Deve retornar AuthContext não autenticado com formato inválido."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [[b"authorization", b"InvalidFormat token123"]],
        }
        request = Request(scope)

        ctx = await jwt_middleware._extract_auth_context(request)

        assert ctx.authenticated is False

    @pytest.mark.asyncio
    async def test_extract_auth_context_valid_jwt(self, jwt_middleware):
        """Deve extrair contexto de JWT válido."""
        import jwt

        # Criar token JWT de teste
        payload = {
            "sub": "user-123",
            "tenant_id": "tenant-456",
            "session_id": "session-789",
            "roles": ["user"],
        }
        token = jwt.encode(payload, "secret", algorithm="HS256")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [[b"authorization", f"Bearer {token}".encode()]],
        }
        request = Request(scope)

        ctx = await jwt_middleware._extract_auth_context(request)

        assert ctx.authenticated is True
        assert ctx.user_id == "user-123"
        assert ctx.tenant_id == "tenant-456"
        assert ctx.session_id == "session-789"
        assert ctx.auth_method == AuthMethod.JWT

    def test_build_auth_context_from_claims(self, jwt_middleware):
        """Deve construir AuthContext corretamente a partir de claims."""
        claims = {
            "sub": "user-123",
            "tenant_id": "tenant-456",
            "session_id": "session-789",
            "roles": ["user", "admin"],
        }

        ctx = jwt_middleware._build_auth_context(claims)

        assert ctx.authenticated is True
        assert ctx.user_id == "user-123"
        assert ctx.tenant_id == "tenant-456"
        assert ctx.session_id == "session-789"
        assert ctx.roles == ["user", "admin"]

    def test_build_auth_context_with_string_roles(self, jwt_middleware):
        """Deve converter string de roles para lista."""
        claims = {
            "sub": "user-123",
            "roles": "admin,user",
        }

        ctx = jwt_middleware._build_auth_context(claims)

        assert ctx.roles == ["admin", "user"]


class TestJWTAuthError:
    """Testes para JWTAuthError."""

    def test_jwt_auth_error_creation(self):
        """JWTAuthError deve ser criado com mensagem e status code."""
        error = JWTAuthError("Invalid token", status_code=401)
        assert error.message == "Invalid token"
        assert error.status_code == 401

    def test_jwt_auth_error_default_status(self):
        """JWTAuthError deve ter status code 401 por padrão."""
        error = JWTAuthError("Unauthorized")
        assert error.status_code == 401
