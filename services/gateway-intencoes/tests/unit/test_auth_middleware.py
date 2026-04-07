"""
Testes unitários para Auth Middleware
Testa autenticação OAuth2, validação de tokens e mTLS
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, HTTPException
from starlette.responses import Response
from starlette.datastructure import Headers
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestAuthMiddleware:
    """Testes para middleware de autenticação"""

    @pytest.fixture
    def mock_app(self):
        """Mock do app FastAPI"""
        app = MagicMock()
        app.state = MagicMock()
        return app

    @pytest.fixture
    def mock_settings(self):
        """Mock das configurações"""
        settings = MagicMock()
        settings.environment = "test"
        settings.token_validation_enabled = True
        settings.keycloak_url = "http://keycloak:8080"
        settings.keycloak_realm = "neural-hive"
        settings.keycloak_client_id = "gateway-client"
        settings.jwks_uri = "http://keycloak:8080/realms/neural-hive/protocol/openid-connect/certs"
        return settings

    @pytest.fixture
    def mock_rate_limiter(self):
        """Mock do rate limiter"""
        rl = AsyncMock()
        result = MagicMock()
        result.allowed = True
        result.limit = 100
        result.remaining = 95
        result.reset_at = 1234567890
        result.retry_after = None
        rl.check_rate_limit = AsyncMock(return_value=result)
        return rl

    @pytest.fixture
    def auth_middleware(self, mock_app, mock_settings, mock_rate_limiter):
        """Fixture do middleware de autenticação"""
        with (
            patch("middleware.auth_middleware.get_settings", return_value=mock_settings),
            patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator,
        ):
            validator = MagicMock()
            validator.validate_token = AsyncMock(
                return_value={
                    "sub": "user-123",
                    "preferred_username": "testuser",
                    "email": "test@example.com",
                    "realm_access": {"roles": ["neural-hive-user"]},
                    "client_id": "client-123",
                    "session_state": "session-abc",
                }
            )
            validator.extract_user_context = MagicMock(
                return_value={
                    "user_id": "user-123",
                    "username": "testuser",
                    "email": "test@example.com",
                    "roles": ["neural-hive-user"],
                    "client_id": "client-123",
                    "session_id": "session-abc",
                }
            )
            mock_validator.return_value = validator

            from middleware.auth_middleware import AuthMiddleware

            middleware = AuthMiddleware(
                mock_app, exclude_paths=["/health", "/metrics"], rate_limiter=mock_rate_limiter
            )
            yield middleware

    @pytest.mark.asyncio
    async def test_valid_token_passes(self, auth_middleware, mock_settings):
        """Testar que token válido passa na autenticação"""
        # Criar request mockado
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "POST"
        request.headers = Headers({"authorization": "Bearer valid-token-123"})
        request.state = MagicMock()

        # Mock do call_next
        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        # Executar middleware
        response = await auth_middleware.dispatch(request, call_next)

        # Verificar que request foi enriquecido
        assert hasattr(request.state, "user")
        assert request.state.user["username"] == "testuser"
        assert hasattr(request.state, "authenticated")
        assert request.state.authenticated is True

    @pytest.mark.asyncio
    async def test_invalid_token_blocked(self, auth_middleware, mock_settings):
        """Testar que token inválido é bloqueado"""
        from middleware.auth_middleware import AuthenticationError

        # Mock validator que lança exceção
        with patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator:
            validator = MagicMock()
            validator.validate_token = AsyncMock(side_effect=Exception("Invalid token"))
            mock_validator.return_value = validator

            request = MagicMock(spec=Request)
            request.url.path = "/api/v1/intentions"
            request.method = "GET"
            request.headers = Headers({"authorization": "Bearer invalid-token"})
            request.state = MagicMock()

            async def call_next(req):
                return MagicMock(spec=Response)

            # Executar - deve retornar erro de autenticação
            response = await auth_middleware.dispatch(request, call_next)

            # Verificar resposta de erro
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_blocked(self, auth_middleware, mock_settings):
        """Testar que ausência de token é bloqueada"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "GET"
        request.headers = Headers({})  # Sem header Authorization
        request.state = MagicMock()

        async def call_next(req):
            return MagicMock(spec=Response)

        # Executar middleware
        response = await auth_middleware.dispatch(request, call_next)

        # Verificar que retorna erro
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_excluded_paths_skip_auth(self, auth_middleware, mock_settings):
        """Testar que paths excluídos pulam autenticação"""
        request = MagicMock(spec=Request)
        request.url.path = "/health"
        request.method = "GET"
        request.headers = Headers({})  # Sem token
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        # Executar - não deve validar token
        response = await auth_middleware.dispatch(request, call_next)

        # Não deve ter usuário autenticado
        assert not hasattr(request.state, "user") or not getattr(request.state, "user", None)

    @pytest.mark.asyncio
    async def test_disabled_validation_allows_request(
        self, mock_app, mock_settings, mock_rate_limiter
    ):
        """Testar que com validação desabilitada, request passa"""
        mock_settings.token_validation_enabled = False

        with patch("middleware.auth_middleware.get_settings", return_value=mock_settings):
            from middleware.auth_middleware import AuthMiddleware

            middleware = AuthMiddleware(mock_app, exclude_paths=[], rate_limiter=mock_rate_limiter)

            request = MagicMock(spec=Request)
            request.url.path = "/api/v1/intentions"
            request.method = "GET"
            request.headers = Headers({})  # Sem token
            request.state = MagicMock()

            async def call_next(req):
                response = MagicMock(spec=Response)
                response.headers = {}
                return response

            # Executar - deve passar sem autenticação
            response = await middleware.dispatch(request, call_next)

            # Deve retornar resposta normal
            assert response is not None

    @pytest.mark.asyncio
    async def test_admin_endpoint_requires_admin_role(self, auth_middleware, mock_settings):
        """Testar que endpoint admin requer role admin"""
        # Mock com role admin
        with patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator:
            validator = MagicMock()
            validator.validate_token = AsyncMock(
                return_value={
                    "sub": "admin-123",
                    "preferred_username": "admin",
                    "email": "admin@example.com",
                    "realm_access": {"roles": ["neural-hive-admin"]},
                    "client_id": "admin-client",
                    "session_state": "session-admin",
                }
            )
            validator.extract_user_context = MagicMock(
                return_value={
                    "user_id": "admin-123",
                    "username": "admin",
                    "email": "admin@example.com",
                    "roles": ["neural-hive-admin"],
                    "client_id": "admin-client",
                    "session_id": "session-admin",
                    "is_admin": True,
                }
            )
            mock_validator.return_value = validator

            request = MagicMock(spec=Request)
            request.url.path = "/api/v1/admin/users"
            request.method = "GET"
            request.headers = Headers({"authorization": "Bearer admin-token"})
            request.state = MagicMock()

            async def call_next(req):
                response = MagicMock(spec=Response)
                response.headers = {}
                return response

            # Recarregar middleware com novo mock
            from middleware.auth_middleware import AuthMiddleware

            middleware = AuthMiddleware(
                MagicMock(), exclude_paths=[], rate_limiter=mock_rate_limiter
            )

            response = await middleware.dispatch(request, call_next)

            # Admin com role correta deve passar
            assert response is not None

    @pytest.mark.asyncio
    async def test_non_admin_blocked_from_admin_endpoint(self, auth_middleware, mock_settings):
        """Testar que usuário sem role admin é bloqueado de endpoints admin"""
        # Mock sem role admin
        with patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator:
            validator = MagicMock()
            validator.validate_token = AsyncMock(
                return_value={
                    "sub": "user-123",
                    "preferred_username": "regularuser",
                    "email": "user@example.com",
                    "realm_access": {"roles": ["neural-hive-user"]},
                    "client_id": "client-123",
                    "session_state": "session-abc",
                }
            )
            validator.extract_user_context = MagicMock(
                return_value={
                    "user_id": "user-123",
                    "username": "regularuser",
                    "email": "user@example.com",
                    "roles": ["neural-hive-user"],  # Sem role admin
                    "client_id": "client-123",
                    "session_id": "session-abc",
                    "is_admin": False,
                }
            )
            mock_validator.return_value = validator

            request = MagicMock(spec=Request)
            request.url.path = "/api/v1/admin/config"
            request.method = "GET"
            request.headers = Headers({"authorization": "Bearer user-token"})
            request.state = MagicMock()

            async def call_next(req):
                return MagicMock(spec=Response)

            from middleware.auth_middleware import AuthMiddleware

            middleware = AuthMiddleware(
                MagicMock(), exclude_paths=[], rate_limiter=mock_rate_limiter
            )

            response = await middleware.dispatch(request, call_next)

            # Deve retornar erro 403
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_rate_limit_checked_for_authenticated_user(
        self, auth_middleware, mock_settings, mock_rate_limiter
    ):
        """Testar que rate limit é verificado para usuário autenticado"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "GET"
        request.headers = Headers({"authorization": "Bearer valid-token-123"})
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        # Executar middleware
        await auth_middleware.dispatch(request, call_next)

        # Verificar que rate limit foi verificado
        mock_rate_limiter.check_rate_limit.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(self, mock_app, mock_settings):
        """Testar que rate limit excedido retorna 429"""
        # Mock rate limiter que bloqueia
        rl = AsyncMock()
        result = MagicMock()
        result.allowed = False
        result.limit = 100
        result.remaining = 0
        result.reset_at = 1234567890
        result.retry_after = 30
        rl.check_rate_limit = AsyncMock(return_value=result)

        with (
            patch("middleware.auth_middleware.get_settings", return_value=mock_settings),
            patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator,
        ):
            validator = MagicMock()
            validator.validate_token = AsyncMock(
                return_value={
                    "sub": "user-123",
                    "preferred_username": "testuser",
                    "email": "test@example.com",
                    "realm_access": {"roles": ["neural-hive-user"]},
                    "client_id": "client-123",
                    "session_state": "session-abc",
                }
            )
            validator.extract_user_context = MagicMock(
                return_value={
                    "user_id": "user-123",
                    "username": "testuser",
                    "email": "test@example.com",
                    "roles": ["neural-hive-user"],
                    "client_id": "client-123",
                    "session_id": "session-abc",
                }
            )
            mock_validator.return_value = validator

            from middleware.auth_middleware import AuthMiddleware

            middleware = AuthMiddleware(mock_app, exclude_paths=[], rate_limiter=rl)

            request = MagicMock(spec=Request)
            request.url.path = "/api/v1/intentions"
            request.method = "GET"
            request.headers = Headers({"authorization": "Bearer valid-token-123"})
            request.state = MagicMock()

            async def call_next(req):
                return MagicMock(spec=Response)

            # Executar - deve retornar 429
            response = await middleware.dispatch(request, call_next)

            assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_context_headers_added_to_request(self, auth_middleware, mock_settings):
        """Testar que headers de contexto são adicionados ao request"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "GET"
        request.headers = Headers({"authorization": "Bearer valid-token-123"})
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        # Executar middleware
        await auth_middleware.dispatch(request, call_next)

        # Verificar headers de contexto
        assert hasattr(request.state, "context_headers")
        headers = request.state.context_headers
        assert "X-User-ID" in headers
        assert headers["X-User-ID"] == "user-123"
        assert "X-Username" in headers
        assert headers["X-Username"] == "testuser"


class TestOptionalAuthMiddleware:
    """Testes para middleware de autenticação opcional"""

    @pytest.fixture
    def mock_app(self):
        """Mock do app FastAPI"""
        return MagicMock()

    @pytest.fixture
    def optional_auth_middleware(self, mock_app):
        """Fixture do middleware de autenticação opcional"""
        with patch("middleware.auth_middleware.get_settings") as mock_settings:
            settings = MagicMock()
            settings.environment = "test"
            mock_settings.return_value = settings

            from middleware.auth_middleware import OptionalAuthMiddleware

            middleware = OptionalAuthMiddleware(mock_app)
            yield middleware

    @pytest.mark.asyncio
    async def test_valid_token_sets_user_context(self, optional_auth_middleware):
        """Testar que token válido define contexto do usuário"""
        with patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator:
            validator = MagicMock()
            validator.validate_token = AsyncMock(
                return_value={"sub": "user-123", "preferred_username": "testuser"}
            )
            validator.extract_user_context = MagicMock(
                return_value={"user_id": "user-123", "username": "testuser"}
            )
            mock_validator.return_value = validator

            request = MagicMock(spec=Request)
            request.headers = Headers({"authorization": "Bearer valid-token"})
            request.state = MagicMock()

            async def call_next(req):
                return MagicMock(spec=Response)

            await optional_auth_middleware.dispatch(request, call_next)

            assert request.state.authenticated is True
            assert request.state.user is not None
            assert request.state.user["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_no_token_still_passes(self, optional_auth_middleware):
        """Testar que ausência de token ainda permite request"""
        request = MagicMock(spec=Request)
        request.headers = Headers({})  # Sem token
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        # Não deve lançar exceção
        response = await optional_auth_middleware.dispatch(request, call_next)

        assert request.state.authenticated is False
        assert request.state.user is None

    @pytest.mark.asyncio
    async def test_invalid_token_ignored(self, optional_auth_middleware):
        """Testar que token inválido é ignorado (não bloqueia)"""
        with patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator:
            validator = MagicMock()
            validator.validate_token = AsyncMock(side_effect=Exception("Invalid token"))
            mock_validator.return_value = validator

            request = MagicMock(spec=Request)
            request.headers = Headers({"authorization": "Bearer invalid-token"})
            request.state = MagicMock()

            async def call_next(req):
                return MagicMock(spec=Response)

            # Não deve lançar exceção
            response = await optional_auth_middleware.dispatch(request, call_next)

            assert request.state.authenticated is False


class TestGetCurrentUser:
    """Testes para dependência get_current_user"""

    @pytest.mark.asyncio
    async def test_get_current_user_authenticated(self):
        """Testar obter usuário atual autenticado"""
        from middleware.auth_middleware import get_current_user

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.authenticated = True
        request.state.user = {"user_id": "user-123", "username": "testuser"}

        user = await get_current_user(request)

        assert user["username"] == "testuser"
        assert user["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_get_current_user_not_authenticated_raises_exception(self):
        """Testar que usuário não autenticado lança exceção"""
        from middleware.auth_middleware import get_current_user

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.authenticated = False

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401


class TestMTLSValidation:
    """Testes para validação mTLS"""

    @pytest.fixture
    def auth_middleware_with_mtls(self):
        """Fixture com middleware configurado para mTLS"""
        mock_app = MagicMock()
        mock_settings = MagicMock()
        mock_settings.environment = "test"
        mock_settings.token_validation_enabled = True
        mock_settings.keycloak_realm = "neural-hive"

        with (
            patch("middleware.auth_middleware.get_settings", return_value=mock_settings),
            patch("middleware.auth_middleware.get_oauth2_validator") as mock_validator,
        ):
            validator = MagicMock()
            validator.validate_token = AsyncMock(
                return_value={"sub": "user-123", "preferred_username": "testuser"}
            )
            validator.extract_user_context = MagicMock(
                return_value={"user_id": "user-123", "username": "testuser"}
            )
            mock_validator.return_value = validator

            from middleware.auth_middleware import AuthMiddleware

            middleware = AuthMiddleware(mock_app, exclude_paths=[])
            yield middleware

    @pytest.mark.asyncio
    async def test_valid_mtls_certificate_enriches_context(self, auth_middleware_with_mtls):
        """Testar que certificado mTLS válido enriquece contexto"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "GET"
        request.headers = Headers(
            {
                "authorization": "Bearer valid-token",
                "x-ssl-client-cert": "-----BEGIN CERTIFICATE-----\nMIIC...",  # Certificado PEM
                "x-ssl-client-subject": "CN=user123,O=ExampleCorp",
                "x-ssl-client-issuer": "CN=ExampleCA",
                "x-ssl-client-fingerprint": "a1:b2:c3:d4:e5:f6",
                "x-ssl-client-verify": "SUCCESS",
            }
        )
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        await auth_middleware_with_mtls.dispatch(request, call_next)

        # Verificar contexto mTLS
        assert hasattr(request.state, "mtls")
        mtls_context = request.state.mtls
        assert mtls_context is not None
        assert mtls_context.get("verified") is True

    @pytest.mark.asyncio
    async def test_missing_mtls_certificate_skips_validation(self, auth_middleware_with_mtls):
        """Testar que ausência de certificado mTLS não bloqueia"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "GET"
        request.headers = Headers(
            {
                "authorization": "Bearer valid-token"
                # Sem headers mTLS
            }
        )
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        # Não deve bloquear
        response = await auth_middleware_with_mtls.dispatch(request, call_next)

        assert response is not None
        assert request.state.mtls is None

    @pytest.mark.asyncio
    async def test_failed_mtls_verification_skips_mtls_context(self, auth_middleware_with_mtls):
        """Testar que certificado mTLS não verificado não adiciona contexto mTLS"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/intentions"
        request.method = "GET"
        request.headers = Headers(
            {
                "authorization": "Bearer valid-token",
                "x-ssl-client-cert": "-----BEGIN CERTIFICATE-----\n...",
                "x-ssl-client-verify": "FAILED",  # Verificação falhou
            }
        )
        request.state = MagicMock()

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        await auth_middleware_with_mtls.dispatch(request, call_next)

        # Contexto mTLS deve ser None ou não verificado
        mtls_context = request.state.mtls
        assert mtls_context is None or mtls_context.get("verified") is not True
