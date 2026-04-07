"""
Testes unitários para ACRClient.

Testes para integração com Azure Container Registry (ACR).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone


from src.clients.acr_client import (
    ACRClient,
    ACRToken,
    get_acr_credentials,
    detect_acr_registry,
    extract_acr_registry_name,
    ACR_TOKEN_DEFAULT_TTL,
)


class TestACRToken:
    """Testes para ACRToken."""

    def test_token_creation(self):
        """Testa criação de token."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        obtained_at = datetime.now(timezone.utc)

        token = ACRToken(
            access_token="test-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=expires_at,
            obtained_at=obtained_at,
        )

        assert token.access_token == "test-token"
        assert token.token_type == "Bearer"
        assert token.registry == "myregistry.azurecr.io"

    def test_token_is_expired(self):
        """Testa verificação de expiração."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)

        token = ACRToken(
            access_token="test-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=past,
            obtained_at=datetime.now(timezone.utc),
        )

        assert token.is_expired() is True

    def test_token_is_not_expired(self):
        """Testa verificação de token não expirado."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        token = ACRToken(
            access_token="test-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=future,
            obtained_at=datetime.now(timezone.utc),
        )

        assert token.is_expired() is False

    def test_token_should_refresh(self):
        """Testa verificação de renovação."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=3)

        token = ACRToken(
            access_token="test-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=old_time,
        )

        # TTL de 2 horas, token tem 3 horas
        assert token.should_refresh(ttl_seconds=7200) is True

    def test_token_should_not_refresh(self):
        """Testa que token novo não precisa de renovação."""
        recent = datetime.now(timezone.utc)

        token = ACRToken(
            access_token="test-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=recent,
        )

        # TTL de 2 horas, token acabou de ser criado
        assert token.should_refresh(ttl_seconds=7200) is False

    def test_token_get_credentials(self):
        """Testa obtenção de credenciais."""
        token = ACRToken(
            access_token="test-token-abc123",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=datetime.now(timezone.utc),
        )

        credentials = token.get_credentials()
        assert credentials == "test-token-abc123"


class TestACRClientInitialization:
    """Testes para inicialização do ACRClient."""

    def test_initialization_defaults(self):
        """Testa inicialização com valores padrão."""
        client = ACRClient(registry="myregistry.azurecr.io")

        assert client.registry == "myregistry.azurecr.io"
        assert client.use_managed_identity is True
        assert client.client_id is None
        assert client.client_secret is None
        assert client.tenant_id is None
        assert client.token_ttl == ACR_TOKEN_DEFAULT_TTL
        assert client.registry_name == "myregistry"

    def test_initialization_custom_values(self):
        """Testa inicialização com valores customizados."""
        client = ACRClient(
            registry="myregistry.azurecr.io",
            use_managed_identity=False,
            client_id="test-client-id",
            client_secret="test-secret",
            tenant_id="test-tenant-id",
            token_ttl=3600,
        )

        assert client.use_managed_identity is False
        assert client.client_id == "test-client-id"
        assert client.client_secret == "test-secret"
        assert client.tenant_id == "test-tenant-id"
        assert client.token_ttl == 3600


class TestGetManagedIdentityToken:
    """Testes para obtenção de token via Managed Identity."""

    def test_managed_identity_not_available(self, monkeypatch):
        """Testa que retorna None quando não há Managed Identity."""
        client = ACRClient(registry="myregistry.azurecr.io")

        # Remover variáveis de ambiente K8s
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("KUBERNETES_PORT", raising=False)

        token = client._get_managed_identity_token()

        assert token is None

    def test_managed_identity_aiohttp_not_installed(self, monkeypatch):
        """Testa quando aiohttp não está instalado."""
        client = ACRClient(registry="myregistry.azurecr.io")

        # Mock environment para simular K8s
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")

        # Mock aiohttp como não instalado
        import sys

        aiohttp_module = sys.modules.get("aiohttp")
        if aiohttp_module:
            # Se existe, remover temporariamente
            original_module = sys.modules.pop("aiohttp", None)

            token = client._get_managed_identity_token()

            # Restaurar
            if original_module:
                sys.modules["aiohttp"] = original_module

            assert token is None
        else:
            # Se não existe, o teste passa direto
            assert client._get_managed_identity_token() is None


class TestGetServicePrincipalToken:
    """Testes para obtenção de token via Service Principal."""

    def test_service_principal_incomplete_credentials(self):
        """Testa que retorna None quando credenciais estão incompletas."""
        client = ACRClient(
            registry="myregistry.azurecr.io",
            client_id="test-client-id",
            # Falta client_secret e tenant_id
        )

        token = client._get_service_principal_token()

        assert token is None

    def test_service_principal_no_credentials(self):
        """Testa que retorna None quando não há credenciais."""
        client = ACRClient(registry="myregistry.azurecr.io")

        token = client._get_service_principal_token()

        assert token is None

    @patch("src.clients.acr_client.requests")
    def test_service_principal_success(self, mock_requests):
        """Testa obtenção de token via Service Principal."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-sp-token-12345",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_requests.post.return_value = mock_response

        client = ACRClient(
            registry="myregistry.azurecr.io",
            client_id="test-client-id",
            client_secret="test-secret",
            tenant_id="test-tenant-id",
        )

        token = client._get_service_principal_token()

        assert token == "test-sp-token-12345"

    @patch("src.clients.acr_client.requests")
    def test_service_principal_failure(self, mock_requests):
        """Testa falha na obtenção de token via Service Principal."""
        # Mock response com erro
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_requests.post.return_value = mock_response

        client = ACRClient(
            registry="myregistry.azurecr.io",
            client_id="test-client-id",
            client_secret="test-secret",
            tenant_id="test-tenant-id",
        )

        token = client._get_service_principal_token()

        assert token is None


class TestGetACRToken:
    """Testes para obtenção de token ACR."""

    def test_get_acr_token_from_cache(self):
        """Testa obtenção de token do cache."""
        client = ACRClient(registry="myregistry.azurecr.io")

        # Criar token cacheado
        cached_token = ACRToken(
            access_token="cached-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=datetime.now(timezone.utc),
        )
        client._cached_token = cached_token

        token = client.get_acr_token()

        assert token.access_token == "cached-token"

    def test_get_acr_token_no_auth_available(self):
        """Testa erro quando nenhum método de auth está disponível."""
        client = ACRClient(
            registry="myregistry.azurecr.io", use_managed_identity=False, client_id=None
        )
        client._cached_token = None

        with pytest.raises(Exception) as exc_info:
            client.get_acr_token()

        assert "Nenhum método de autenticação ACR disponível" in str(exc_info.value)


class TestGetACRCredentials:
    """Testes para obtenção de credenciais ACR."""

    def test_get_acr_credentials_format(self):
        """Testa formato de credenciais para uso com Docker/Kaniko."""
        client = ACRClient(registry="myregistry.azurecr.io")

        # Mock do token
        client._cached_token = ACRToken(
            access_token="test-token-abc",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=datetime.now(timezone.utc),
        )

        username, password = client.get_acr_credentials()

        # ACR usa token como username, password vazio
        assert username == "test-token-abc"
        assert password == ""


class TestIsACRRegistry:
    """Testes para detecção de registry ACR."""

    @pytest.mark.parametrize(
        "image_uri,expected",
        [
            ("myregistry.azurecr.io/myimage:tag", True),
            ("myregistry.azurecr.io/myimage", True),
            ("myregistry.eastus.azurecr.io/myimage:tag", True),
            ("docker.io/library/nginx", False),
            ("gcr.io/myproject/myimage", False),
            ("ghcr.io/user/repo", False),
            ("127.0.0.1:5000/image", False),
        ],
    )
    def test_is_acr_registry(self, image_uri, expected):
        """Testa detecção de registry ACR."""
        client = ACRClient(registry="myregistry.azurecr.io")
        result = client.is_acr_registry(image_uri)
        assert result is expected


class TestGetRegistryEndpoint:
    """Testes para construção de endpoint do registry."""

    def test_get_registry_endpoint_default(self):
        """Testa endpoint padrão."""
        client = ACRClient(registry="myregistry.azurecr.io")
        endpoint = client.get_registry_endpoint()
        assert endpoint == "myregistry.azurecr.io"

    def test_get_registry_endpoint_custom_name(self):
        """Testa endpoint com nome customizado."""
        client = ACRClient(registry="myregistry.azurecr.io")
        endpoint = client.get_registry_endpoint(registry_name="otherregistry")
        assert endpoint == "otherregistry.azurecr.io"


class TestRefreshIfNeeded:
    """Testes para renovação de token."""

    def test_refresh_needed(self):
        """Testa que token é renovado quando necessário."""
        client = ACRClient(token_ttl=3600)

        # Criar token antigo (2 horas)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        client._cached_token = ACRToken(
            access_token="old-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=old_time,
        )

        # Mock _get_managed_identity_token para retornar novo token
        with patch.object(client, "_get_managed_identity_token", return_value="new-token"):
            with patch.object(client, "_get_service_principal_token", return_value=None):
                refreshed = client.refresh_if_needed()

                assert refreshed is True

    def test_refresh_not_needed(self):
        """Testa que token não é renovado se recente."""
        client = ACRClient(token_ttl=7200)

        # Criar token recente (5 minutos)
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        client._cached_token = ACRToken(
            access_token="current-token",
            token_type="Bearer",
            registry="myregistry.azurecr.io",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=recent,
        )

        refreshed = client.refresh_if_needed()

        assert refreshed is False
        assert client._cached_token.access_token == "current-token"


class TestInvalidateCache:
    """Testes para invalidação de cache."""

    def test_invalidate_cache(self):
        """Testa invalidação do cache."""
        client = ACRClient(registry="myregistry.azurecr.io")
        client._cached_token = MagicMock()

        client.invalidate_cache()

        assert client._cached_token is None


class TestConvenienceFunctions:
    """Testes para funções de conveniência."""

    @patch("src.clients.acr_client.ACRClient")
    def test_get_acr_credentials(self, mock_client_class):
        """Testa função de conveniência get_acr_credentials."""
        mock_client = MagicMock()
        mock_client.get_acr_credentials.return_value = ("user", "")
        mock_client_class.return_value = mock_client

        username, password = get_acr_credentials("myregistry.azurecr.io")

        assert username == "user"
        assert password == ""
        mock_client_class.assert_called_once()

    def test_detect_acr_registry_true(self):
        """Testa detecção de ACR - positivo."""
        assert detect_acr_registry("myregistry.azurecr.io/myimage") is True
        assert detect_acr_registry("myregistry.azurecr.io/myimage:latest") is True
        assert detect_acr_registry("myregistry.eastus.azurecr.io/myimage:v1") is True

    def test_detect_acr_registry_false(self):
        """Testa detecção de ACR - negativo."""
        assert detect_acr_registry("docker.io/library/nginx") is False
        assert detect_acr_registry("gcr.io/myproject/myimage") is False
        assert detect_acr_registry("127.0.0.1:5000/image") is False

    def test_extract_acr_registry_name(self):
        """Testa extração de nome do registry."""
        assert extract_acr_registry_name("myregistry.azurecr.io/myimage:tag") == "myregistry"
        assert extract_acr_registry_name("myregistry.azurecr.io/myimage") == "myregistry"
        assert (
            extract_acr_registry_name("myregistry.eastus.azurecr.io/myimage") == "myregistry.eastus"
        )

    def test_extract_acr_registry_name_non_acr(self):
        """Testa extração de nome para URI não-ACR."""
        assert extract_acr_registry_name("docker.io/library/nginx") is None
        assert extract_acr_registry_name("gcr.io/myproject/myimage") is None
