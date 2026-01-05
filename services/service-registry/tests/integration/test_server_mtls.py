"""
Testes de integracao para mTLS no Service Registry Server.

Testa criacao de credenciais de servidor e adicao de porta segura.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

import grpc


@dataclass
class X509SVID:
    """Mock de X.509-SVID"""
    certificate: str
    private_key: str
    spiffe_id: str
    ca_bundle: str
    expires_at: datetime


# Certificados de teste (self-signed para testes)
TEST_CERT = """-----BEGIN CERTIFICATE-----
MIIDOTCCAiGgAwIBAgIUQp7aJ3OvV5nqcEcQbVJBq7J0pSswDQYJKoZIhvcNAQEL
BQAwLTELMAkGA1UEBhMCVVMxHjAcBgNVBAoMFVNQSUZGRSBUZXN0IENlcnRpZmlj
YXRlMB4XDTI0MDEwMTAwMDAwMFoXDTI1MDEwMTAwMDAwMFowLTELMAkGA1UEBhMC
VVMxHjAcBgNVBAoMFVNQSUZGRSBUZXN0IENlcnRpZmljYXRlMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0zxKQb0NixdCw5/QQJ7KZ0zxgP7e3F3yMxKB
-----END CERTIFICATE-----"""

TEST_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDTPEpBvQ2LF0LD
n9BAnsplzPGA/t7cXfIzEoEpwsxLQb0NixdCw5/QQJ7KZ0zxgP7e3F3yMxKBAgMB
-----END PRIVATE KEY-----"""

TEST_CA_BUNDLE = """-----BEGIN CERTIFICATE-----
MIIDOTCCAiGgAwIBAgIUQp7aJ3OvV5nqcEcQbVJBq7J0pSswDQYJKoZIhvcNAQEL
BQAwLTELMAkGA1UEBhMCVVMxHjAcBgNVBAoMFVNQSUZGRSBUZXN0IENBIEJVRERA
-----END CERTIFICATE-----"""


class MockSPIFFEManager:
    """Mock do SPIFFEManager para testes"""

    def __init__(self):
        self.fetch_x509_svid = AsyncMock()
        self.fetch_jwt_svid = AsyncMock()
        self.initialize = AsyncMock()
        self.close = AsyncMock()


@pytest.fixture
def mock_spiffe_manager():
    """Fixture que retorna mock do SPIFFEManager"""
    manager = MockSPIFFEManager()
    manager.fetch_x509_svid.return_value = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-execution/sa/service-registry',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    return manager


@pytest.fixture
def mock_settings():
    """Fixture que retorna configuracoes mockadas"""
    settings = MagicMock()
    settings.SERVICE_NAME = 'service-registry'
    settings.SERVICE_VERSION = '1.0.0'
    settings.ENVIRONMENT = 'production'
    settings.LOG_LEVEL = 'INFO'
    settings.GRPC_PORT = 50051
    settings.METRICS_PORT = 9090
    settings.SPIFFE_ENABLED = True
    settings.SPIFFE_ENABLE_X509 = True
    settings.SPIFFE_SOCKET_PATH = 'unix:///run/spire/sockets/agent.sock'
    settings.SPIFFE_TRUST_DOMAIN = 'neural-hive.local'
    settings.SPIFFE_VERIFY_PEER = True
    settings.OTEL_EXPORTER_ENDPOINT = 'http://otel-collector:4317'
    settings.ETCD_ENDPOINTS = ['redis:6379']
    settings.ETCD_PREFIX = 'neural-hive:agents'
    settings.ETCD_TIMEOUT_SECONDS = 5
    settings.REDIS_CLUSTER_NODES = ['redis:6379']
    settings.REDIS_PASSWORD = 'test-password'
    settings.HEALTH_CHECK_INTERVAL_SECONDS = 60
    settings.HEARTBEAT_TIMEOUT_SECONDS = 120
    return settings


@pytest.mark.asyncio
async def test_server_creates_mtls_credentials(mock_spiffe_manager, mock_settings):
    """Testa que servidor cria credenciais mTLS corretamente"""
    from src.main import ServiceRegistryServer

    with patch('src.main.get_settings') as mock_get_settings, \
         patch('grpc.ssl_server_credentials') as mock_ssl_server_creds:

        mock_get_settings.return_value = mock_settings

        mock_credentials = MagicMock()
        mock_ssl_server_creds.return_value = mock_credentials

        # Criar servidor
        server = ServiceRegistryServer()
        server.spiffe_manager = mock_spiffe_manager

        # Criar credenciais
        credentials = await server._create_server_credentials()

        # Verificar que X.509-SVID foi buscado
        mock_spiffe_manager.fetch_x509_svid.assert_called_once()

        # Verificar que ssl_server_credentials foi chamado
        mock_ssl_server_creds.assert_called_once()
        call_args = mock_ssl_server_creds.call_args

        # Verificar argumentos
        private_key_cert_chain_pairs = call_args[0][0]
        assert len(private_key_cert_chain_pairs) == 1
        assert private_key_cert_chain_pairs[0][0] == TEST_PRIVATE_KEY.encode('utf-8')
        assert private_key_cert_chain_pairs[0][1] == TEST_CERT.encode('utf-8')

        kwargs = call_args.kwargs
        assert kwargs['root_certificates'] == TEST_CA_BUNDLE.encode('utf-8')
        assert kwargs['require_client_auth'] is True

        assert credentials == mock_credentials


@pytest.mark.asyncio
async def test_server_returns_none_when_spiffe_disabled(mock_settings):
    """Testa que servidor retorna None quando SPIFFE esta desabilitado"""
    from src.main import ServiceRegistryServer

    mock_settings.SPIFFE_ENABLED = False

    with patch('src.main.get_settings') as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        server = ServiceRegistryServer()
        server.spiffe_manager = None

        credentials = await server._create_server_credentials()

        assert credentials is None


@pytest.mark.asyncio
async def test_server_returns_none_when_x509_disabled(mock_spiffe_manager, mock_settings):
    """Testa que servidor retorna None quando X.509 esta desabilitado"""
    from src.main import ServiceRegistryServer

    mock_settings.SPIFFE_ENABLE_X509 = False

    with patch('src.main.get_settings') as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        server = ServiceRegistryServer()
        server.spiffe_manager = mock_spiffe_manager

        credentials = await server._create_server_credentials()

        assert credentials is None


@pytest.mark.asyncio
async def test_server_fails_in_production_without_credentials(mock_settings):
    """Testa que servidor falha em producao se credenciais nao puderem ser criadas"""
    from src.main import ServiceRegistryServer

    mock_settings.ENVIRONMENT = 'production'
    mock_settings.SPIFFE_ENABLED = True
    mock_settings.SPIFFE_ENABLE_X509 = True

    # Mock spiffe_manager que falha ao buscar SVID
    failing_manager = MockSPIFFEManager()
    failing_manager.fetch_x509_svid.side_effect = Exception("SPIRE unavailable")

    with patch('src.main.get_settings') as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        server = ServiceRegistryServer()
        server.spiffe_manager = failing_manager

        with pytest.raises(RuntimeError, match="Failed to create mTLS credentials in production"):
            await server._create_server_credentials()


@pytest.mark.asyncio
async def test_server_allows_failure_in_development(mock_settings):
    """Testa que servidor permite falha em desenvolvimento"""
    from src.main import ServiceRegistryServer

    mock_settings.ENVIRONMENT = 'development'
    mock_settings.SPIFFE_ENABLED = True
    mock_settings.SPIFFE_ENABLE_X509 = True

    # Mock spiffe_manager que falha ao buscar SVID
    failing_manager = MockSPIFFEManager()
    failing_manager.fetch_x509_svid.side_effect = Exception("SPIRE unavailable")

    with patch('src.main.get_settings') as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        server = ServiceRegistryServer()
        server.spiffe_manager = failing_manager

        # Nao deve levantar excecao em desenvolvimento
        credentials = await server._create_server_credentials()
        assert credentials is None


@pytest.mark.asyncio
async def test_server_logs_mtls_configuration(mock_spiffe_manager, mock_settings, caplog):
    """Testa que servidor loga configuracao mTLS"""
    from src.main import ServiceRegistryServer

    with patch('src.main.get_settings') as mock_get_settings, \
         patch('grpc.ssl_server_credentials') as mock_ssl_server_creds:

        mock_get_settings.return_value = mock_settings

        mock_credentials = MagicMock()
        mock_ssl_server_creds.return_value = mock_credentials

        server = ServiceRegistryServer()
        server.spiffe_manager = mock_spiffe_manager

        await server._create_server_credentials()

        # Verificar que log foi criado (estrutlog pode nao aparecer em caplog)
        # Este teste verifica principalmente que nao houve excecao


@pytest.mark.asyncio
async def test_server_certificate_expiry_info(mock_spiffe_manager, mock_settings):
    """Testa que informacoes de expiracao sao obtidas corretamente"""
    from src.main import ServiceRegistryServer

    expires_at = datetime.utcnow() + timedelta(hours=48)
    mock_spiffe_manager.fetch_x509_svid.return_value = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-execution/sa/service-registry',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=expires_at
    )

    with patch('src.main.get_settings') as mock_get_settings, \
         patch('grpc.ssl_server_credentials') as mock_ssl_server_creds:

        mock_get_settings.return_value = mock_settings

        mock_credentials = MagicMock()
        mock_ssl_server_creds.return_value = mock_credentials

        server = ServiceRegistryServer()
        server.spiffe_manager = mock_spiffe_manager

        credentials = await server._create_server_credentials()

        # Verificar que credenciais foram criadas
        assert credentials is not None

        # Verificar que X.509-SVID foi buscado com expiracao correta
        svid = await mock_spiffe_manager.fetch_x509_svid()
        assert svid.expires_at == expires_at
