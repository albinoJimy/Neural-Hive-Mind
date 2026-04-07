"""
Testes unitários para GCRClient.

Testes para integração com Google Container Registry (GCR).
"""

import pytest
import json
import base64
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from pathlib import Path


@pytest.fixture
def temp_service_account_key(tmp_path):
    """Cria um arquivo temporário de service account key."""
    key_data = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key-id",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest-key\n-----END RSA PRIVATE KEY-----",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "access_token": "ya29.test-token-12345",
        "expires_in": 3600,
    }
    key_file = tmp_path / "service-account.json"
    key_file.write_text(json.dumps(key_data))
    return str(key_file)


@pytest.fixture
def mock_k8s_token_file(tmp_path):
    """Cria um arquivo temporário simulando token de service account K8s."""
    token_file = tmp_path / "token"
    token_file.write_text("mock-k8s-service-account-token")
    return str(token_file)


from src.clients.gcr_client import (
    GCRClient,
    GCRToken,
    get_gcr_credentials,
    detect_gcr_registry,
    extract_gcr_project,
    GCR_TOKEN_DEFAULT_TTL,
)


class TestGCRToken:
    """Testes para GCRToken."""

    def test_token_creation(self):
        """Testa criação de token."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        obtained_at = datetime.now(timezone.utc)

        token = GCRToken(
            access_token="test-token",
            token_type="oauth2_access_token",
            expires_at=expires_at,
            obtained_at=obtained_at,
        )

        assert token.access_token == "test-token"
        assert token.token_type == "oauth2_access_token"

    def test_token_is_expired(self):
        """Testa verificação de expiração."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)

        token = GCRToken(
            access_token="test-token",
            token_type="oauth2_access_token",
            expires_at=past,
            obtained_at=datetime.now(timezone.utc),
        )

        assert token.is_expired() is True

    def test_token_is_not_expired(self):
        """Testa verificação de token não expirado."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        token = GCRToken(
            access_token="test-token",
            token_type="oauth2_access_token",
            expires_at=future,
            obtained_at=datetime.now(timezone.utc),
        )

        assert token.is_expired() is False

    def test_token_should_refresh(self):
        """Testa verificação de renovação."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)

        token = GCRToken(
            access_token="test-token",
            token_type="oauth2_access_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=old_time,
        )

        # TTL de 1 hora, token tem 2 horas
        assert token.should_refresh(ttl_seconds=3600) is True

    def test_token_should_not_refresh(self):
        """Testa que token novo não precisa de renovação."""
        recent = datetime.now(timezone.utc)

        token = GCRToken(
            access_token="test-token",
            token_type="oauth2_access_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=recent,
        )

        # TTL de 1 hora, token acabou de ser criado
        assert token.should_refresh(ttl_seconds=3600) is False

    def test_token_get_credentials(self):
        """Testa obtenção de credenciais."""
        token = GCRToken(
            access_token="test-token-abc123",
            token_type="oauth2_access_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=datetime.now(timezone.utc),
        )

        credentials = token.get_credentials()
        assert credentials == "oauth2accesstoken://test-token-abc123"


class TestGCRClientInitialization:
    """Testes para inicialização do GCRClient."""

    def test_initialization_defaults(self):
        """Testa inicialização com valores padrão."""
        client = GCRClient()

        assert client.registry == "gcr.io"
        assert client.use_workload_identity is True
        assert client.service_account_key_path is None
        assert client.service_account_email is None
        assert client.token_ttl == GCR_TOKEN_DEFAULT_TTL
        assert client._cached_token is None

    def test_initialization_custom_values(self):
        """Testa inicialização com valores customizados."""
        client = GCRClient(
            registry="eu.gcr.io",
            use_workload_identity=False,
            service_account_key_path="/path/to/key.json",
            service_account_email="test@test-project.iam.gserviceaccount.com",
            token_ttl=7200,
        )

        assert client.registry == "eu.gcr.io"
        assert client.use_workload_identity is False
        assert client.service_account_key_path == "/path/to/key.json"
        assert client.service_account_email == "test@test-project.iam.gserviceaccount.com"
        assert client.token_ttl == 7200


class TestGetWorkloadIdentityToken:
    """Testes para obtenção de token via Workload Identity."""

    def test_wif_token_from_k8s_service_account(self, monkeypatch, mock_k8s_token_file):
        """Testa obtenção de token via service account K8s."""
        client = GCRClient()

        # Mock environment variables para simular GKE
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
        monkeypatch.setenv("KUBERNETES_PORT", "443")

        # Mock do caminho do token de service account
        token_path = mock_k8s_token_file

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = (
                "mock-k8s-service-account-token"
            )

            # Patch do path do token
            with patch.object(Path, "exists", return_value=True):
                # Mock direto da função file read
                original_exists = Path.exists

                def mock_exists(self_path):
                    if "serviceaccount/token" in str(self_path):
                        return True
                    return original_exists(self_path)

                monkeypatch.setattr("pathlib.Path.exists", mock_exists)

                token = client._get_workload_identity_token()

                assert token is not None

    def test_wif_token_from_env_var(self, monkeypatch):
        """Testa obtenção de token via variável de ambiente."""
        client = GCRClient()
        monkeypatch.setenv("GCR_TOKEN", "env-provided-token")

        token = client._get_workload_identity_token()

        assert token == "env-provided-token"

    def test_wif_token_not_available(self, monkeypatch):
        """Testa que retorna None quando não há WIF disponível."""
        client = GCRClient()

        # Remover variáveis de ambiente
        monkeypatch.delenv("GCR_TOKEN", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("KUBERNETES_PORT", raising=False)

        token = client._get_workload_identity_token()

        assert token is None


class TestGetServiceAccountToken:
    """Testes para obtenção de token via Service Account key."""

    def test_service_account_token_success(self, temp_service_account_key):
        """Testa obtenção de token via service account key."""
        client = GCRClient(
            service_account_key_path=temp_service_account_key,
            service_account_email="test@test-project.iam.gserviceaccount.com",
        )

        token = client._get_service_account_token()

        assert token == "ya29.test-token-12345"

    def test_service_account_token_no_key_path(self):
        """Testa que retorna None quando não há key path."""
        client = GCRClient(service_account_key_path=None)

        token = client._get_service_account_token()

        assert token is None

    def test_service_account_token_file_not_found(self):
        """Testa erro quando arquivo não existe."""
        client = GCRClient(service_account_key_path="/nonexistent/path/key.json")

        token = client._get_service_account_token()

        assert token is None

    def test_service_account_token_invalid_json(self, tmp_path):
        """Testa erro quando arquivo não é JSON válido."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json")

        client = GCRClient(service_account_key_path=str(invalid_file))

        token = client._get_service_account_token()

        assert token is None

    def test_service_account_token_missing_access_token(self, tmp_path):
        """Testa erro quando JSON não tem access_token."""
        key_data = {
            "type": "service_account",
            "project_id": "test-project"
            # Falta access_token
        }
        key_file = tmp_path / "incomplete.json"
        key_file.write_text(json.dumps(key_data))

        client = GCRClient(service_account_key_path=str(key_file))

        token = client._get_service_account_token()

        assert token is None


class TestGetGCRToken:
    """Testes para obtenção de token GCR."""

    def test_get_gcr_token_from_cache(self):
        """Testa obtenção de token do cache."""
        client = GCRClient()

        # Criar token cacheado
        cached_token = GCRToken(
            access_token="cached-token",
            token_type="oauth2_access_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=datetime.now(timezone.utc),
        )
        client._cached_token = cached_token

        token = client.get_gcr_token()

        assert token.access_token == "cached-token"

    def test_get_gcr_token_from_wif(self, monkeypatch):
        """Testa obtenção de token via Workload Identity."""
        client = GCRClient(use_workload_identity=True)
        client._cached_token = None

        monkeypatch.setenv("GCR_TOKEN", "wif-token")

        token = client.get_gcr_token()

        assert token.access_token == "wif-token"
        assert token.token_type == "oauth2_access_token"

    def test_get_gcr_token_fallback_to_service_account(self, temp_service_account_key, monkeypatch):
        """Testa fallback para service account key."""
        client = GCRClient(
            use_workload_identity=True, service_account_key_path=temp_service_account_key
        )
        client._cached_token = None

        # Sem token WIF
        monkeypatch.delenv("GCR_TOKEN", raising=False)

        token = client.get_gcr_token()

        assert token.access_token == "ya29.test-token-12345"

    def test_get_gcr_token_no_auth_available(self):
        """Testa erro quando nenhum método de auth está disponível."""
        client = GCRClient(use_workload_identity=False, service_account_key_path=None)
        client._cached_token = None

        with pytest.raises(Exception) as exc_info:
            client.get_gcr_token()

        assert "Nenhum método de autenticação GCR disponível" in str(exc_info.value)


class TestGetGCRCredentials:
    """Testes para obtenção de credenciais GCR."""

    def test_get_gcr_credentials_format(self, monkeypatch):
        """Testa formato de credenciais para uso com Docker/Kaniko."""
        client = GCRClient()
        client._cached_token = None
        monkeypatch.setenv("GCR_TOKEN", "test-token-abc")

        credentials = client.get_gcr_credentials()

        assert credentials == "oauth2accesstoken://test-token-abc"


class TestIsGCRRegistry:
    """Testes para detecção de registry GCR."""

    @pytest.mark.parametrize(
        "image_uri,expected",
        [
            ("gcr.io/project/image:tag", True),
            ("gcr.io/project/image", True),
            ("us.gcr.io/project/image:tag", True),
            ("eu.gcr.io/project/image:tag", True),
            ("asia.gcr.io/project/image:tag", True),
            ("asia-east1.gcr.io/project/image:tag", True),
            ("st.gcr.io/project/image:tag", True),
            ("docker.io/library/nginx", False),
            ("ghcr.io/user/repo", False),
            ("registry.gitlab.com/project/image", False),
            ("127.0.0.1:5000/image", False),
        ],
    )
    def test_is_gcr_registry(self, image_uri, expected):
        """Testa detecção de registry GCR."""
        client = GCRClient()
        result = client.is_gcr_registry(image_uri)
        assert result is expected


class TestGetRegistryEndpoint:
    """Testes para construção de endpoint do registry."""

    def test_get_registry_endpoint_us(self):
        """Testa endpoint para região US."""
        client = GCRClient()
        endpoint = client.get_registry_endpoint(region="us")
        assert endpoint == "gcr.io"

    def test_get_registry_endpoint_eu(self):
        """Testa endpoint para região EU."""
        client = GCRClient()
        endpoint = client.get_registry_endpoint(region="eu")
        assert endpoint == "eu.gcr.io"

    def test_get_registry_endpoint_asia(self):
        """Testa endpoint para região Asia."""
        client = GCRClient()
        endpoint = client.get_registry_endpoint(region="asia")
        assert endpoint == "asia.gcr.io"


class TestGetFullImageURI:
    """Testes para construção de URI completa da imagem."""

    def test_get_full_image_uri_with_tag(self):
        """Testa URI com tag."""
        client = GCRClient()
        uri = client.get_full_image_uri(
            project_id="my-project", image_name="my-image", tag="v1.0.0"
        )
        assert uri == "gcr.io/my-project/my-image:v1.0.0"

    def test_get_full_image_uri_default_tag(self):
        """Testa URI com tag padrão (latest)."""
        client = GCRClient()
        uri = client.get_full_image_uri(project_id="my-project", image_name="my-image")
        assert uri == "gcr.io/my-project/my-image:latest"

    def test_get_full_image_uri_custom_registry(self):
        """Testa URI com registry customizado."""
        client = GCRClient(registry="eu.gcr.io")
        uri = client.get_full_image_uri(project_id="my-project", image_name="my-image", tag="v2.0")
        assert uri == "eu.gcr.io/my-project/my-image:v2.0"


class TestRefreshIfNeeded:
    """Testes para renovação de token."""

    def test_refresh_needed(self, monkeypatch):
        """Testa que token é renovado quando necessário."""
        client = GCRClient(token_ttl=3600)

        # Criar token antigo (2 horas)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        client._cached_token = GCRToken(
            access_token="old-token",
            token_type="oauth2_access_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            obtained_at=old_time,
        )

        monkeypatch.setenv("GCR_TOKEN", "new-refreshed-token")

        refreshed = client.refresh_if_needed()

        assert refreshed is True
        assert client._cached_token.access_token == "new-refreshed-token"

    def test_refresh_not_needed(self):
        """Testa que token não é renovado se recente."""
        client = GCRClient(token_ttl=3600)

        # Criar token recente (5 minutos)
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        client._cached_token = GCRToken(
            access_token="current-token",
            token_type="oauth2_access_token",
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
        client = GCRClient()
        client._cached_token = MagicMock()

        client.invalidate_cache()

        assert client._cached_token is None


class TestConvenienceFunctions:
    """Testes para funções de conveniência."""

    @patch("src.clients.gcr_client.GCRClient")
    def test_get_gcr_credentials(self, mock_client_class, monkeypatch):
        """Testa função de conveniência get_gcr_credentials."""
        mock_client = MagicMock()
        mock_client.get_gcr_credentials.return_value = "oauth2accesstoken://test-token"
        mock_client_class.return_value = mock_client

        credentials = get_gcr_credentials("gcr.io/project/image")

        assert credentials == "oauth2accesstoken://test-token"
        mock_client_class.assert_called_once()

    def test_detect_gcr_registry_true(self):
        """Testa detecção de GCR - positivo."""
        assert detect_gcr_registry("gcr.io/myproject/myimage") is True
        assert detect_gcr_registry("us.gcr.io/myproject/myimage:latest") is True
        assert detect_gcr_registry("eu.gcr.io/myproject/myimage:v1") is True

    def test_detect_gcr_registry_false(self):
        """Testa detecção de GCR - negativo."""
        assert detect_gcr_registry("docker.io/library/nginx") is False
        assert detect_gcr_registry("ghcr.io/user/repo") is False
        assert detect_gcr_registry("127.0.0.1:5000/image") is False

    def test_extract_gcr_project_standard(self):
        """Testa extração de project ID - formato padrão."""
        assert extract_gcr_project("gcr.io/my-project/image:tag") == "my-project"
        assert extract_gcr_project("gcr.io/my-project/image") == "my-project"

    def test_extract_gcr_project_regional(self):
        """Testa extração de project ID - formato regional."""
        assert extract_gcr_project("us.gcr.io/my-project/image:tag") == "my-project"
        assert extract_gcr_project("eu.gcr.io/my-project/image:v1.0") == "my-project"
        assert extract_gcr_project("asia-east1.gcr.io/my-project/image") == "my-project"

    def test_extract_gcr_project_non_gcr(self):
        """Testa extração de project ID para URI não-GCR."""
        assert extract_gcr_project("docker.io/library/nginx") is None
        assert extract_gcr_project("ghcr.io/user/repo") is None

    def test_extract_gcr_project_malformed(self):
        """Testa extração de project ID com URI malformada."""
        assert extract_gcr_project("gcr.io/") is None
        assert extract_gcr_project("gcr.io") is None
