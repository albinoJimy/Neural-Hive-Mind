"""Testes unitários para Auth Middleware."""

import pytest
from fastapi import HTTPException, status

from src.api.auth import (
    get_current_user_optional,
    get_current_user,
    get_current_user_with_permissions,
    PermissionChecker,
    require_admin,
    require_approver,
    require_permission,
    UnauthorizedError,
    ForbiddenError,
    get_user_id_from_payload,
)
from src.services.token_service import TokenService, TokenPayload


class TestAuthMiddleware:
    """Testes para middleware de autenticação (síncronos)."""

    @pytest.fixture
    def token_service(self):
        """Fixture para TokenService."""
        return TokenService()

    @pytest.fixture
    def valid_token(self, token_service):
        """Fixture para token válido."""
        return token_service.create_access_token("user-123", ["read", "write"])

    @pytest.fixture
    def admin_token(self, token_service):
        """Fixture para token de admin."""
        return token_service.create_access_token("admin-001", ["admin", "read"])

    @pytest.fixture
    def token_payload(self, token_service, valid_token):
        """Fixture para TokenPayload."""
        return token_service.decode_token(valid_token)

    def test_get_user_id_from_payload(self, token_payload):
        """Testa extração de user_id do payload."""
        user_id = get_user_id_from_payload(token_payload)
        assert user_id == "user-123"

    def test_unauthorized_error(self):
        """Testa criação de UnauthorizedError."""
        error = UnauthorizedError("Test error")
        assert error.status_code == status.HTTP_401_UNAUTHORIZED
        assert error.detail == "Test error"
        assert "WWW-Authenticate" in error.headers

    def test_forbidden_error(self):
        """Testa criação de ForbiddenError."""
        error = ForbiddenError("Test forbidden")
        assert error.status_code == status.HTTP_403_FORBIDDEN
        assert error.detail == "Test forbidden"

    def test_permission_checker_factory(self):
        """Testa factory PermissionChecker."""
        checker = PermissionChecker(["admin", "write"])
        assert checker.required_permissions == ["admin", "write"]

    def test_require_permission_factory(self):
        """Testa factory require_permission."""
        checker = require_permission("approve")
        assert checker.required_permissions == ["approve"]

    def test_require_any_permission(self):
        """Testa factory require_any_permission."""
        from src.api.auth import require_any_permission
        checker = require_any_permission("read", "write", "admin")
        assert checker.required_permissions == ["read", "write", "admin"]

    def test_require_admin_is_permission_checker(self):
        """Testa que require_admin é PermissionChecker."""
        assert isinstance(require_admin, PermissionChecker)
        assert require_admin.required_permissions == ["admin"]

    def test_require_approver_is_permission_checker(self):
        """Testa que require_approver é PermissionChecker."""
        assert isinstance(require_approver, PermissionChecker)
        # require_approver tem ["approve"]
        assert require_approver.required_permissions == ["approve"]


@pytest.mark.asyncio
class TestAuthWithFastAPI:
    """Testes de integração com FastAPI (assíncronos)."""

    @pytest.fixture
    def token_service(self):
        """Fixture para TokenService."""
        return TokenService()

    @pytest.fixture
    def user_token(self, token_service):
        """Fixture para token de usuário comum."""
        return token_service.create_access_token("user-123", ["read"])

    @pytest.fixture
    def admin_token(self, token_service):
        """Fixture para token de admin."""
        return token_service.create_access_token("admin-001", ["admin", "read", "write"])

    @pytest.fixture
    def mock_http_creds(self, user_token):
        """Cria mock de HTTPAuthorizationCredentials."""
        from fastapi.security import HTTPAuthorizationCredentials
        return HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials=user_token
        )

    @pytest.fixture
    def mock_admin_creds(self, admin_token):
        """Cria mock de HTTPAuthorizationCredentials para admin."""
        from fastapi.security import HTTPAuthorizationCredentials
        return HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials=admin_token
        )

    @pytest.fixture
    def mock_invalid_creds(self):
        """Cria mock de HTTPAuthorizationCredentials inválido."""
        from fastapi.security import HTTPAuthorizationCredentials
        return HTTPAuthorizationCredentials(
            scheme="bearer",
            credentials="invalid.token.here"
        )

    async def test_get_current_user_optional_with_token(self, token_service, mock_http_creds):
        """Testa get_current_user_optional com token válido."""
        result = await get_current_user_optional(
            credentials=mock_http_creds,
            token_service=token_service
        )
        assert result is not None
        assert result.sub == "user-123"

    async def test_get_current_user_optional_without_token(self, token_service):
        """Testa get_current_user_optional sem token."""
        result = await get_current_user_optional(
            credentials=None,
            token_service=token_service
        )
        assert result is None

    async def test_get_current_user_with_valid_token(self, token_service, mock_http_creds):
        """Testa get_current_user com token válido."""
        result = await get_current_user(
            credentials=mock_http_creds,
            token_service=token_service
        )
        assert result is not None
        assert result.sub == "user-123"

    async def test_get_current_user_without_token(self, token_service):
        """Testa get_current_user sem token lança exceção."""
        with pytest.raises(UnauthorizedError):
            await get_current_user(
                credentials=None,
                token_service=token_service
            )

    async def test_get_current_user_with_invalid_token(self, token_service, mock_invalid_creds):
        """Testa get_current_user com token inválido lança exceção."""
        with pytest.raises(UnauthorizedError):
            await get_current_user(
                credentials=mock_invalid_creds,
                token_service=token_service
            )

    async def test_get_current_user_with_permissions_sufficient(self, token_service, mock_admin_creds):
        """Testa get_current_user_with_permissions com permissões suficientes."""
        result = await get_current_user_with_permissions(
            required_permissions=["admin"],
            credentials=mock_admin_creds,
            token_service=token_service
        )
        assert result is not None
        assert result.sub == "admin-001"

    async def test_get_current_user_with_permissions_insufficient(self, token_service, mock_http_creds):
        """Testa get_current_user_with_permissions com permissões insuficientes."""
        with pytest.raises(ForbiddenError):
            await get_current_user_with_permissions(
                required_permissions=["admin"],
                credentials=mock_http_creds,
                token_service=token_service
            )
