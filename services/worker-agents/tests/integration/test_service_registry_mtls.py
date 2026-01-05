"""
Testes de integracao para mTLS entre Worker Agent e Service Registry.

Testa criacao de canal seguro com X.509-SVID, JWT-SVID em metadata e fallbacks.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
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


@dataclass
class JWTSVID:
    """Mock de JWT-SVID"""
    token: str
    spiffe_id: str
    expiry: datetime


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
        self.fetch_jwt_svid = AsyncMock()
        self.fetch_x509_svid = AsyncMock()
        self.initialize = AsyncMock()
        self.close = AsyncMock()


@pytest.fixture
def mock_spiffe_manager():
    """Fixture que retorna mock do SPIFFEManager com X.509-SVID e JWT-SVID validos"""
    manager = MockSPIFFEManager()

    # Configurar retorno padrao de X.509-SVID valido
    manager.fetch_x509_svid.return_value = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )

    # Configurar retorno padrao de JWT-SVID valido
    manager.fetch_jwt_svid.return_value = JWTSVID(
        token='valid.jwt.token',
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents',
        expiry=datetime.utcnow() + timedelta(hours=1)
    )

    return manager


@pytest.fixture
def mock_config():
    """Fixture que retorna configuracoes mockadas com SPIFFE habilitado"""
    config = MagicMock()
    config.service_registry_host = 'service-registry.test.local'
    config.service_registry_port = 50051
    config.spiffe_enabled = True
    config.spiffe_enable_x509 = True
    config.spiffe_socket_path = 'unix:///run/spire/sockets/agent.sock'
    config.spiffe_trust_domain = 'neural-hive.local'
    config.spiffe_jwt_audience = 'service-registry.neural-hive.local'
    config.spiffe_jwt_ttl_seconds = 3600
    config.environment = 'production'
    config.agent_id = 'worker-1'
    config.supported_task_types = ['BUILD', 'DEPLOY']
    config.namespace = 'neural-hive-execution'
    config.cluster = 'test-cluster'
    config.service_version = '1.0.0'
    config.http_port = 8080
    config.grpc_port = 50052
    config.max_concurrent_tasks = 5
    return config


@pytest.mark.asyncio
async def test_worker_agent_mtls_initialization(mock_spiffe_manager, mock_config):
    """Testa inicializacao do Worker Agent com mTLS via X.509-SVID"""
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True), \
         patch('src.clients.service_registry_client.SPIFFEManager') as MockSPIFFEManagerClass, \
         patch('src.clients.service_registry_client.SPIFFEConfig'), \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        # Setup mocks
        MockSPIFFEManagerClass.return_value = mock_spiffe_manager
        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel = AsyncMock()
        mock_secure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        # Criar cliente
        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Verificar que X.509-SVID foi buscado
        mock_spiffe_manager.fetch_x509_svid.assert_called_once()

        # Verificar que credenciais SSL foram criadas
        mock_ssl_creds.assert_called_once()
        call_kwargs = mock_ssl_creds.call_args.kwargs
        assert call_kwargs['root_certificates'] == TEST_CA_BUNDLE.encode('utf-8')
        assert call_kwargs['private_key'] == TEST_PRIVATE_KEY.encode('utf-8')
        assert call_kwargs['certificate_chain'] == TEST_CERT.encode('utf-8')

        # Verificar que canal seguro foi criado
        mock_secure_channel.assert_called_once_with(
            'service-registry.test.local:50051',
            mock_credentials
        )


@pytest.mark.asyncio
async def test_worker_agent_registration_with_jwt_metadata(mock_spiffe_manager, mock_config):
    """Testa registro do Worker Agent com JWT-SVID em metadata"""
    from src.clients.service_registry_client import ServiceRegistryClient
    from neural_hive_integration.proto_stubs import service_registry_pb2

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True), \
         patch('src.clients.service_registry_client.SPIFFEManager') as MockSPIFFEManagerClass, \
         patch('src.clients.service_registry_client.SPIFFEConfig'), \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        # Setup mocks
        MockSPIFFEManagerClass.return_value = mock_spiffe_manager
        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel = AsyncMock()
        mock_secure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agent_id = 'worker-1'
        mock_response.registration_token = 'token123'
        mock_response.registered_at = 1234567890
        mock_stub.Register = AsyncMock(return_value=mock_response)
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        # Criar e inicializar cliente
        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Registrar
        agent_id = await client.register()

        # Verificar que JWT-SVID foi buscado
        mock_spiffe_manager.fetch_jwt_svid.assert_called_once()

        # Verificar chamada RPC com metadata
        mock_stub.Register.assert_called_once()
        call_args = mock_stub.Register.call_args
        metadata = call_args.kwargs.get('metadata', [])

        # Verificar que Authorization header esta presente
        auth_header = None
        for key, value in metadata:
            if key == 'authorization':
                auth_header = value
                break

        assert auth_header is not None, "JWT deve estar presente em metadata"
        assert auth_header.startswith('Bearer ')
        assert 'valid.jwt.token' in auth_header
        assert agent_id == 'worker-1'


@pytest.mark.asyncio
async def test_worker_agent_mtls_required_in_production(mock_config):
    """Testa que mTLS e obrigatorio em producao"""
    from src.clients.service_registry_client import ServiceRegistryClient

    # Desabilitar SPIFFE X.509
    mock_config.spiffe_enabled = True
    mock_config.spiffe_enable_x509 = False
    mock_config.environment = 'production'

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True):
        client = ServiceRegistryClient(mock_config)

        # Deve falhar em producao sem mTLS
        with pytest.raises(RuntimeError, match="mTLS is required in production"):
            await client.initialize()


@pytest.mark.asyncio
async def test_worker_agent_insecure_allowed_in_dev(mock_config):
    """Testa que canal inseguro e permitido em desenvolvimento"""
    from src.clients.service_registry_client import ServiceRegistryClient

    # Desabilitar SPIFFE em desenvolvimento
    mock_config.spiffe_enabled = False
    mock_config.environment = 'development'

    with patch('grpc.aio.insecure_channel') as mock_insecure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        mock_channel = AsyncMock()
        mock_insecure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Verificar que canal inseguro foi usado
        mock_insecure_channel.assert_called_once()


@pytest.mark.asyncio
async def test_worker_agent_heartbeat_with_jwt_metadata(mock_spiffe_manager, mock_config):
    """Testa heartbeat do Worker Agent com JWT-SVID em metadata"""
    from src.clients.service_registry_client import ServiceRegistryClient
    from neural_hive_integration.proto_stubs import service_registry_pb2

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True), \
         patch('src.clients.service_registry_client.SPIFFEManager') as MockSPIFFEManagerClass, \
         patch('src.clients.service_registry_client.SPIFFEConfig'), \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        # Setup mocks
        MockSPIFFEManagerClass.return_value = mock_spiffe_manager
        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel = AsyncMock()
        mock_secure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.status = 1  # HEALTHY
        mock_stub.Heartbeat = AsyncMock(return_value=mock_response)
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        # Criar e inicializar cliente
        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Simular registro previo
        client._registered = True
        client.agent_id = 'worker-1'

        # Resetar contador de chamadas JWT
        mock_spiffe_manager.fetch_jwt_svid.reset_mock()

        # Enviar heartbeat
        telemetry = {
            'success_rate': 0.95,
            'avg_duration_ms': 150,
            'total_executions': 100,
            'failed_executions': 5,
            'timestamp': 1234567890.0
        }
        result = await client.heartbeat(telemetry)

        # Verificar que JWT-SVID foi buscado
        mock_spiffe_manager.fetch_jwt_svid.assert_called_once()

        # Verificar chamada RPC com metadata
        mock_stub.Heartbeat.assert_called_once()
        call_args = mock_stub.Heartbeat.call_args
        metadata = call_args.kwargs.get('metadata', [])

        # Verificar que Authorization header esta presente
        auth_header = None
        for key, value in metadata:
            if key == 'authorization':
                auth_header = value
                break

        assert auth_header is not None
        assert result is True


@pytest.mark.asyncio
async def test_worker_agent_deregister_with_jwt_metadata(mock_spiffe_manager, mock_config):
    """Testa deregister do Worker Agent com JWT-SVID em metadata"""
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True), \
         patch('src.clients.service_registry_client.SPIFFEManager') as MockSPIFFEManagerClass, \
         patch('src.clients.service_registry_client.SPIFFEConfig'), \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        # Setup mocks
        MockSPIFFEManagerClass.return_value = mock_spiffe_manager
        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel = AsyncMock()
        mock_secure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_stub.Deregister = AsyncMock(return_value=mock_response)
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        # Criar e inicializar cliente
        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Simular registro previo
        client._registered = True
        client.agent_id = 'worker-1'

        # Resetar contador de chamadas JWT
        mock_spiffe_manager.fetch_jwt_svid.reset_mock()

        # Deregister
        result = await client.deregister()

        # Verificar que JWT-SVID foi buscado
        mock_spiffe_manager.fetch_jwt_svid.assert_called_once()

        # Verificar chamada RPC com metadata
        mock_stub.Deregister.assert_called_once()
        call_args = mock_stub.Deregister.call_args
        metadata = call_args.kwargs.get('metadata', [])

        # Verificar que Authorization header esta presente
        auth_header = None
        for key, value in metadata:
            if key == 'authorization':
                auth_header = value
                break

        assert auth_header is not None
        assert result is True


@pytest.mark.asyncio
async def test_jwt_svid_failure_continues_in_dev(mock_spiffe_manager, mock_config):
    """Testa que falha ao buscar JWT-SVID continua em desenvolvimento"""
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar ambiente de desenvolvimento
    mock_config.environment = 'development'

    # Configurar JWT fetch para falhar
    mock_spiffe_manager.fetch_jwt_svid.side_effect = Exception("SPIRE agent unavailable")

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True), \
         patch('src.clients.service_registry_client.SPIFFEManager') as MockSPIFFEManagerClass, \
         patch('src.clients.service_registry_client.SPIFFEConfig'), \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        # Setup mocks
        MockSPIFFEManagerClass.return_value = mock_spiffe_manager
        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel = AsyncMock()
        mock_secure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agent_id = 'worker-1'
        mock_stub.Register = AsyncMock(return_value=mock_response)
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        # Criar e inicializar cliente
        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Registrar deve continuar sem JWT em dev
        agent_id = await client.register()

        # Verificar que RPC foi chamado mesmo sem JWT
        mock_stub.Register.assert_called_once()
        assert agent_id == 'worker-1'


@pytest.mark.asyncio
async def test_jwt_svid_failure_raises_in_production(mock_spiffe_manager, mock_config):
    """Testa que falha ao buscar JWT-SVID levanta erro em producao"""
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar ambiente de producao
    mock_config.environment = 'production'

    # Configurar JWT fetch para falhar
    mock_spiffe_manager.fetch_jwt_svid.side_effect = Exception("SPIRE agent unavailable")

    with patch('src.clients.service_registry_client.SECURITY_LIB_AVAILABLE', True), \
         patch('src.clients.service_registry_client.SPIFFEManager') as MockSPIFFEManagerClass, \
         patch('src.clients.service_registry_client.SPIFFEConfig'), \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel, \
         patch('src.clients.service_registry_client.instrument_grpc_channel') as mock_instrument, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc:

        # Setup mocks
        MockSPIFFEManagerClass.return_value = mock_spiffe_manager
        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel = AsyncMock()
        mock_secure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        # Criar e inicializar cliente
        client = ServiceRegistryClient(mock_config)
        await client.initialize()

        # Registrar deve falhar em producao sem JWT
        with pytest.raises(Exception, match="SPIRE agent unavailable"):
            await client.register()
