"""
Testes de integracao para KeycloakAdminClient

Testa operacoes de revogacao de tokens e gerenciamento de usuarios
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import httpx

from src.clients.keycloak_admin_client import KeycloakAdminClient


@pytest.fixture
def keycloak_settings():
    """Configuracoes de teste para Keycloak"""
    return {
        "keycloak_url": "http://keycloak-test.local:8080",
        "realm": "test-realm",
        "client_id": "test-admin-client",
        "client_secret": "test-secret",
        "timeout_seconds": 5,
        "token_cache_ttl_seconds": 300
    }


@pytest.fixture
def keycloak_client(keycloak_settings):
    """Fixture do KeycloakAdminClient"""
    return KeycloakAdminClient(
        keycloak_url=keycloak_settings["keycloak_url"],
        realm=keycloak_settings["realm"],
        client_id=keycloak_settings["client_id"],
        client_secret=keycloak_settings["client_secret"],
        timeout_seconds=keycloak_settings["timeout_seconds"],
        token_cache_ttl_seconds=keycloak_settings["token_cache_ttl_seconds"]
    )


@pytest.fixture
def mock_httpx_client():
    """Mock do httpx.AsyncClient"""
    return AsyncMock(spec=httpx.AsyncClient)


class TestKeycloakAdminClientConnection:
    """Testes de conexao do Keycloak Admin Client"""

    @pytest.mark.asyncio
    async def test_connect_success(self, keycloak_client, mock_httpx_client):
        """Testa conexao bem-sucedida com Keycloak"""
        # Mock da resposta de token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-admin-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        mock_httpx_client.post = AsyncMock(return_value=token_response)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()

            assert keycloak_client._http_client is not None
            assert keycloak_client._admin_token == "test-admin-token"

    @pytest.mark.asyncio
    async def test_is_healthy_after_connect(self, keycloak_client, mock_httpx_client):
        """Testa que cliente esta saudavel apos conexao"""
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        mock_httpx_client.post = AsyncMock(return_value=token_response)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()

            assert keycloak_client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_close_connection(self, keycloak_client, mock_httpx_client):
        """Testa fechamento de conexao"""
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        mock_httpx_client.post = AsyncMock(return_value=token_response)
        mock_httpx_client.aclose = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            await keycloak_client.close()

            assert keycloak_client._http_client is None
            mock_httpx_client.aclose.assert_called_once()


class TestRevokeUserSessions:
    """Testes de revogacao de sessoes de usuario"""

    @pytest.mark.asyncio
    async def test_revoke_user_sessions_success(self, keycloak_client, mock_httpx_client):
        """Testa revogacao bem-sucedida de sessoes"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock logout response
        logout_response = MagicMock()
        logout_response.status_code = 204

        mock_httpx_client.post = AsyncMock(side_effect=[token_response, logout_response])

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.revoke_user_sessions("user-123")

            assert result["success"] is True
            assert result["user_id"] == "user-123"
            assert result["action"] == "revoke_sessions"
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_revoke_user_sessions_user_not_found(self, keycloak_client, mock_httpx_client):
        """Testa revogacao quando usuario nao existe"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock 404 response
        not_found_response = MagicMock()
        not_found_response.status_code = 404

        mock_httpx_client.post = AsyncMock(side_effect=[token_response, not_found_response])

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.revoke_user_sessions("nonexistent-user")

            assert result["success"] is False
            assert result["reason"] == "User not found"

    @pytest.mark.asyncio
    async def test_revoke_user_sessions_http_error(self, keycloak_client, mock_httpx_client):
        """Testa tratamento de erro HTTP na revogacao"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock erro HTTP
        error_response = MagicMock()
        error_response.status_code = 500

        def raise_for_status():
            raise httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=error_response
            )

        error_response.raise_for_status = raise_for_status

        mock_httpx_client.post = AsyncMock(side_effect=[token_response, error_response])

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.revoke_user_sessions("user-123")

            assert result["success"] is False
            assert "HTTP error" in result["reason"]


class TestDisableUser:
    """Testes de desabilitacao de usuario"""

    @pytest.mark.asyncio
    async def test_disable_user_success(self, keycloak_client, mock_httpx_client):
        """Testa desabilitacao bem-sucedida de usuario"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock disable response
        disable_response = MagicMock()
        disable_response.status_code = 204

        mock_httpx_client.post = AsyncMock(return_value=token_response)
        mock_httpx_client.put = AsyncMock(return_value=disable_response)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.disable_user("user-123")

            assert result["success"] is True
            assert result["action"] == "disable_user"
            mock_httpx_client.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_user_not_found(self, keycloak_client, mock_httpx_client):
        """Testa desabilitacao quando usuario nao existe"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock 404 response
        not_found_response = MagicMock()
        not_found_response.status_code = 404

        mock_httpx_client.post = AsyncMock(return_value=token_response)
        mock_httpx_client.put = AsyncMock(return_value=not_found_response)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.disable_user("nonexistent-user")

            assert result["success"] is False
            assert result["reason"] == "User not found"


class TestEnableUser:
    """Testes de reabilitacao de usuario"""

    @pytest.mark.asyncio
    async def test_enable_user_success(self, keycloak_client, mock_httpx_client):
        """Testa reabilitacao bem-sucedida de usuario"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock enable response
        enable_response = MagicMock()
        enable_response.status_code = 204

        mock_httpx_client.post = AsyncMock(return_value=token_response)
        mock_httpx_client.put = AsyncMock(return_value=enable_response)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.enable_user("user-123")

            assert result["success"] is True
            assert result["action"] == "enable_user"


class TestGetUserSessions:
    """Testes de listagem de sessoes de usuario"""

    @pytest.mark.asyncio
    async def test_get_user_sessions_success(self, keycloak_client, mock_httpx_client):
        """Testa listagem bem-sucedida de sessoes"""
        # Mock token
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 300
        }
        token_response.raise_for_status = MagicMock()

        # Mock sessions response
        sessions_response = MagicMock()
        sessions_response.status_code = 200
        sessions_response.json.return_value = [
            {"id": "session-1", "username": "user-123"},
            {"id": "session-2", "username": "user-123"}
        ]

        mock_httpx_client.post = AsyncMock(return_value=token_response)
        mock_httpx_client.get = AsyncMock(return_value=sessions_response)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()
            result = await keycloak_client.get_user_sessions("user-123")

            assert result["success"] is True
            assert result["session_count"] == 2
            assert len(result["sessions"]) == 2


class TestTokenRefresh:
    """Testes de renovacao de token admin"""

    @pytest.mark.asyncio
    async def test_token_auto_refresh(self, keycloak_client, mock_httpx_client):
        """Testa renovacao automatica de token expirado"""
        # Mock token expirado (expires_in = 1 segundo)
        expired_token_response = MagicMock()
        expired_token_response.status_code = 200
        expired_token_response.json.return_value = {
            "access_token": "expired-token",
            "expires_in": 1
        }
        expired_token_response.raise_for_status = MagicMock()

        # Mock novo token
        new_token_response = MagicMock()
        new_token_response.status_code = 200
        new_token_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 300
        }
        new_token_response.raise_for_status = MagicMock()

        # Mock logout response
        logout_response = MagicMock()
        logout_response.status_code = 204

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return expired_token_response
            elif "logout" in str(args):
                return logout_response
            else:
                return new_token_response

        mock_httpx_client.post = mock_post

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            await keycloak_client.connect()

            # Token atual esta quase expirado
            import time
            time.sleep(0.1)

            # Forcar expiracao do token
            keycloak_client._token_expires_at = datetime.now(timezone.utc)

            # Proxima chamada deve renovar token
            result = await keycloak_client.revoke_user_sessions("user-123")

            # Verificar que token foi renovado
            assert result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
