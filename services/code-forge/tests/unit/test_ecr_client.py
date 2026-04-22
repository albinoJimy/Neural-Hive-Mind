"""
Testes unitários para ECRClient.

Testes para integração com Amazon ECR (Elastic Container Registry).
"""

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

# Mock boto3 antes de importar ecr_client
mock_boto3_session = MagicMock()
sys.modules["boto3"] = MagicMock()
sys.modules["boto3"].Session = mock_boto3_session

from src.clients.ecr_client import (
    ECR_TOKEN_DEFAULT_TTL,
    ECRClient,
    ECRToken,
    detect_ecr_registry,
    extract_ecr_region,
    get_ecr_credentials,
)


class TestECRToken:
    """Testes para ECRToken."""

    def test_token_creation(self):
        """Testa criação de token."""
        expires_at = datetime.now(UTC) + timedelta(hours=12)
        obtained_at = datetime.now(UTC)

        token = ECRToken(
            username="AWS",
            password="password",
            endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            expires_at=expires_at,
            obtained_at=obtained_at,
        )

        assert token.username == "AWS"
        assert token.password == "password"
        assert token.endpoint == "123456789012.dkr.ecr.us-east-1.amazonaws.com"

    def test_token_is_expired(self):
        """Testa verificação de expiração."""
        past = datetime.now(UTC) - timedelta(hours=1)

        token = ECRToken(
            username="AWS",
            password="password",
            endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            expires_at=past,
            obtained_at=datetime.now(UTC),
        )

        assert token.is_expired() is True

    def test_token_is_not_expired(self):
        """Testa verificação de token não expirado."""
        future = datetime.now(UTC) + timedelta(hours=12)

        token = ECRToken(
            username="AWS",
            password="password",
            endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            expires_at=future,
            obtained_at=datetime.now(UTC),
        )

        assert token.is_expired() is False

    def test_token_should_refresh(self):
        """Testa verificação de renovação."""
        old_time = datetime.now(UTC) - timedelta(hours=2)

        token = ECRToken(
            username="AWS",
            password="password",
            endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
            obtained_at=old_time,
        )

        # TTL de 1 hora, token tem 2 horas
        assert token.should_refresh(ttl_seconds=3600) is True

    def test_token_should_not_refresh(self):
        """Testa que token novo não precisa de renovação."""
        recent = datetime.now(UTC)

        token = ECRToken(
            username="AWS",
            password="password",
            endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
            obtained_at=recent,
        )

        # TTL de 1 hora, token acabou de ser criado
        assert token.should_refresh(ttl_seconds=3600) is False

    def test_token_get_credentials(self):
        """Testa obtenção de credenciais."""
        token = ECRToken(
            username="testuser",
            password="testpass",
            endpoint="123456789012.dkr.ecr.us-east-1.amazonaws.com",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
            obtained_at=datetime.now(UTC),
        )

        username, password = token.get_credentials()
        assert username == "testuser"
        assert password == "testpass"


class TestECRClientInitialization:
    """Testes para inicialização do ECRClient."""

    def test_initialization_defaults(self):
        """Testa inicialização com valores padrão."""
        client = ECRClient()

        assert client.region == "us-east-1"
        assert client.use_irsa is True
        assert client.access_key_id is None
        assert client.secret_access_key is None
        assert client.token_ttl == ECR_TOKEN_DEFAULT_TTL

    def test_initialization_custom_values(self):
        """Testa inicialização com valores customizados."""
        client = ECRClient(
            region="eu-west-1",
            use_irsa=False,
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            token_ttl=7200,
        )

        assert client.region == "eu-west-1"
        assert client.use_irsa is False
        assert client.access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert client.secret_access_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert client.token_ttl == 7200


class TestGetBoto3Session:
    """Testes para obtenção de sessão boto3."""

    def test_get_boto3_session_with_irsa(self):
        """Testa criação de sessão com IRSA."""
        mock_session = MagicMock()
        mock_boto3_session_session = MagicMock()
        mock_boto3_session_session.return_value = mock_session

        client = ECRClient(use_irsa=True)
        client._boto3_session = None  # Reset para forçar nova criação
        session = client._get_boto3_session()

        assert session is not None

    def test_get_boto3_session_reuse(self):
        """Testa que sessão é reutilizada."""
        mock_session = MagicMock()

        client = ECRClient()

        session1 = client._get_boto3_session()
        session2 = client._get_boto3_session()

        # Sessão deve ser a mesma (reutilizada)
        assert session1 is session2


class TestGetECRToken:
    """Testes para obtenção de token ECR."""

    def setup_method(self):
        """Setup para cada teste."""
        # Reset mock
        mock_boto3_session_session = MagicMock()
        sys.modules["boto3"].Session = mock_boto3_session_session

    def test_get_ecr_token_cache_miss(self):
        """Testa cache miss - obtém novo token."""
        mock_session = MagicMock()
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "authorizationToken": "QUVXUzpQQVNTV09SRA==",  # base64("AWS:PASSWORD")
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                }
            ]
        }
        mock_session.client.return_value = mock_ecr
        sys.modules["boto3"].Session.return_value = mock_session

        client = ECRClient()
        client._cached_token = None  # Garantir cache vazio

        token = client.get_ecr_token()

        assert token.username == "AWS"
        assert token.password == "PASSWORD"
        assert token.endpoint == "123456789012.dkr.ecr.us-east-1.amazonaws.com"
        mock_ecr.get_authorization_token.assert_called_once()

    def test_get_ecr_token_with_registry_id(self):
        """Testa obtenção com registry ID específico."""
        mock_session = MagicMock()
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "authorizationToken": "QUVXUzpQQVNTV09SRA==",
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                }
            ]
        }
        mock_session.client.return_value = mock_ecr
        sys.modules["boto3"].Session.return_value = mock_session

        client = ECRClient()

        token = client.get_ecr_token(registry_id="123456789012")

        mock_ecr.get_authorization_token.assert_called_once_with(registryIds=["123456789012"])


class TestGetECRCredentials:
    """Testes para obtenção de credenciais ECR."""

    def test_get_ecr_credentials(self):
        """Testa obtenção de credenciais."""
        mock_session = MagicMock()
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "authorizationToken": "QUVXUzpQQVNTV09SRA==",
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                }
            ]
        }
        mock_session.client.return_value = mock_ecr
        mock_boto3.Session.return_value = mock_session

        client = ECRClient()
        client._cached_token = None

        username, password, endpoint = client.get_ecr_credentials()

        assert username == "AWS"
        assert password == "PASSWORD"
        assert endpoint == "123456789012.dkr.ecr.us-east-1.amazonaws.com"


class TestIsIRSAAvailable:
    """Testes para detecção de IRSA."""

    def test_irsa_available_with_env_vars(self, monkeypatch):
        """Testa detecção de IRSA via variáveis de ambiente."""
        client = ECRClient(use_irsa=True)

        monkeypatch.setenv("AWS_WEB_IDENTITY_TOKEN_FILE", "/token")
        monkeypatch.setenv("AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/test")

        assert client.is_irsa_available() is True

    def test_irsa_not_available_without_env_vars(self, monkeypatch):
        """Testa que IRSA não está disponível sem variáveis."""
        import os

        # Salvar valores originais
        original_token = os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")
        original_arn = os.environ.get("AWS_ROLE_ARN")

        # Remover variáveis
        if "AWS_WEB_IDENTITY_TOKEN_FILE" in os.environ:
            del os.environ["AWS_WEB_IDENTITY_TOKEN_FILE"]
        if "AWS_ROLE_ARN" in os.environ:
            del os.environ["AWS_ROLE_ARN"]

        client = ECRClient(use_irsa=True)

        # Sem mock de STS, retorna False
        assert client.is_irsa_available() is False

        # Restaurar valores originais
        if original_token:
            os.environ["AWS_WEB_IDENTITY_TOKEN_FILE"] = original_token
        if original_arn:
            os.environ["AWS_ROLE_ARN"] = original_arn

    def test_irsa_disabled(self):
        """Testa que IRSA disabled retorna False."""
        client = ECRClient(use_irsa=False)
        assert client.is_irsa_available() is False


class TestGetRegistryURI:
    """Testes para construção de URI do registry."""

    def test_get_registry_uri_with_account_id(self):
        """Testa construção com account ID fornecido."""
        client = ECRClient(region="us-west-2")

        uri = client.get_registry_uri(account_id="123456789012")

        assert uri == "123456789012.dkr.ecr.us-west-2.amazonaws.com"

    def test_get_registry_uri_auto_detect(self):
        """Testa auto-detecção de account ID via STS."""
        mock_session = MagicMock()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "987654321098",
            "UserId": "AIDAI...",
            "Arn": "arn:aws:iam::987654321098:user/test",
        }
        mock_session.client.return_value = mock_sts
        mock_boto3.Session.return_value = mock_session

        client = ECRClient(region="eu-central-1")

        uri = client.get_registry_uri()

        assert uri == "987654321098.dkr.ecr.eu-central-1.amazonaws.com"


class TestRefreshIfNeeded:
    """Testes para renovação de token."""

    def test_refresh_needed(self):
        """Testa que token é renovado quando necessário."""
        mock_session = MagicMock()
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "authorizationToken": "TkVXOnBBU1NXT1JE",
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                }
            ]
        }
        mock_session.client.return_value = mock_ecr
        mock_boto3.Session.return_value = mock_session

        client = ECRClient(token_ttl=3600)  # 1 hora

        # Criar token antigo (2 horas)
        old_time = datetime.now(UTC) - timedelta(hours=2)
        client._cached_token = ECRToken(
            username="OLD",
            password="OLD",
            endpoint="old.dkr.ecr.amazonaws.com",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
            obtained_at=old_time,
        )

        refreshed = client.refresh_if_needed()

        assert refreshed is True
        mock_ecr.get_authorization_token.assert_called_once()

    def test_refresh_not_needed(self):
        """Testa que token não é renovado se recente."""
        client = ECRClient(token_ttl=3600)

        # Criar token recente (5 minutos)
        recent = datetime.now(UTC) - timedelta(minutes=5)
        client._cached_token = ECRToken(
            username="CURRENT",
            password="CURRENT",
            endpoint="current.dkr.ecr.amazonaws.com",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
            obtained_at=recent,
        )

        refreshed = client.refresh_if_needed()

        assert refreshed is False


class TestInvalidateCache:
    """Testes para invalidação de cache."""

    def test_invalidate_cache(self):
        """Testa invalidação do cache."""
        client = ECRClient()
        client._cached_token = MagicMock()

        client.invalidate_cache()

        assert client._cached_token is None


class TestConvenienceFunctions:
    """Testes para funções de conveniência."""

    @patch("src.clients.ecr_client.ECRClient")
    def test_get_ecr_credentials(self, mock_client_class):
        """Testa função de conveniência get_ecr_credentials."""
        mock_client = MagicMock()
        mock_client.get_ecr_credentials.return_value = ("user", "pass", "endpoint")
        mock_client_class.return_value = mock_client

        username, password = get_ecr_credentials("123456789012.dkr.ecr.us-east-1.amazonaws.com")

        assert username == "user"
        assert password == "pass"
        mock_client_class.assert_called_once()
        mock_client.get_ecr_credentials.assert_called_once()

    def test_detect_ecr_registry_true(self):
        """Testa detecção de ECR - positivo."""
        assert detect_ecr_registry("123456789012.dkr.ecr.us-east-1.amazonaws.com/myapp") is True
        assert (
            detect_ecr_registry("123456789012.dkr.ecr.eu-west-1.amazonaws.com/myapp:latest") is True
        )

    def test_detect_ecr_registry_false(self):
        """Testa detecção de ECR - negativo."""
        assert detect_ecr_registry("docker.io/library/nginx") is False
        assert detect_ecr_registry("gcr.io/myproject/myimage") is False
        assert detect_ecr_registry("ghcr.io/user/repo") is False

    def test_extract_ecr_region(self):
        """Testa extração de região de URI ECR."""
        assert (
            extract_ecr_region("123456789012.dkr.ecr.us-east-1.amazonaws.com/myapp") == "us-east-1"
        )
        assert (
            extract_ecr_region("123456789012.dkr.ecr.eu-west-1.amazonaws.com/myapp:latest")
            == "eu-west-1"
        )
        assert (
            extract_ecr_region("123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/myapp")
            == "ap-southeast-1"
        )

    def test_extract_ecr_region_non_ecr(self):
        """Testa extração de região para URI não-ECR."""
        assert extract_ecr_region("docker.io/library/nginx") is None
        assert extract_ecr_region("gcr.io/myproject/myimage") is None
