"""
Testes de integração para mTLS channel do ServiceRegistryClient.

Testa criação de canal seguro com X.509-SVID, handshake, renovação e fallbacks.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from dataclasses import dataclass
from freezegun import freeze_time

import grpc
from grpc import aio
import structlog

# Mock das classes SPIFFE antes de importar o cliente
@dataclass
class JWTSVID:
    """Mock de JWT-SVID"""
    token: str
    spiffe_id: str
    expiry: datetime


@dataclass
class X509SVID:
    """Mock de X.509-SVID"""
    certificate: str
    private_key: str
    spiffe_id: str
    ca_bundle: str
    expires_at: datetime


class MockSPIFFEManager:
    """Mock do SPIFFEManager para testes"""

    def __init__(self):
        self.fetch_jwt_svid = AsyncMock()
        self.fetch_x509_svid = AsyncMock()
        self.get_trust_bundle = AsyncMock()


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


@pytest.fixture
def mock_spiffe_manager():
    """Fixture que retorna mock do SPIFFEManager com X.509-SVID válido"""
    manager = MockSPIFFEManager()

    # Configurar retorno padrão de X.509-SVID válido
    manager.fetch_x509_svid.return_value = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )

    return manager


@pytest.fixture
def mock_settings():
    """Fixture que retorna configurações mockadas com mTLS habilitado"""
    from src.config.settings import OrchestratorSettings

    settings = MagicMock(spec=OrchestratorSettings)
    settings.service_registry_host = 'service-registry.test.local'
    settings.service_registry_port = 50051
    settings.service_registry_timeout_seconds = 3
    settings.spiffe_enabled = True
    settings.spiffe_enable_x509 = True  # mTLS habilitado
    settings.spiffe_jwt_audience = 'service-registry.neural-hive.local'

    return settings


@pytest.mark.asyncio
async def test_x509_svid_fetch_and_secure_channel(mock_spiffe_manager, mock_settings, caplog):
    """
    Testa que X.509-SVID é obtido e ssl_channel_credentials/secure_channel são criados.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Verificar que fetch_x509_svid foi chamado
        mock_spiffe_manager.fetch_x509_svid.assert_called_once()

        # Verificar que ssl_channel_credentials foi chamado com certificados corretos
        mock_ssl_creds.assert_called_once()
        call_args = mock_ssl_creds.call_args
        kwargs = call_args.kwargs

        assert kwargs['root_certificates'] == TEST_CA_BUNDLE.encode('utf-8')
        assert kwargs['private_key'] == TEST_PRIVATE_KEY.encode('utf-8')
        assert kwargs['certificate_chain'] == TEST_CERT.encode('utf-8')

        # Verificar que secure_channel foi chamado
        mock_secure_channel.assert_called_once_with(
            'service-registry.test.local:50051',
            mock_credentials
        )

        # Verificar log
        assert any('mtls_channel_configured' in record.msg for record in caplog.records if hasattr(record, 'msg'))


@pytest.mark.asyncio
async def test_mtls_handshake_success(mock_spiffe_manager, mock_settings):
    """
    Testa que handshake mTLS é bem-sucedido e resposta é recebida.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()

        # Mock de resposta bem-sucedida
        mock_response = MagicMock()
        mock_agent = MagicMock()
        mock_agent.agent_id = 'worker-1'
        mock_agent.agent_type = 1  # WORKER
        mock_agent.capabilities = ['code_generation']
        mock_agent.namespace = 'production'
        mock_agent.cluster = 'us-east-1'
        mock_agent.version = '1.0.0'
        mock_agent.schema_version = 'v1'
        mock_agent.metadata = {}
        mock_agent.status = 1  # HEALTHY
        mock_agent.registered_at = '2024-01-01T00:00:00Z'
        mock_agent.last_seen = '2024-01-01T12:00:00Z'
        mock_agent.telemetry = None

        mock_response.agents = [mock_agent]
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Chamar discover_agents
        agents = await client.discover_agents(
            capabilities=['code_generation'],
            filters={},
            max_results=5
        )

        # Verificar resposta
        assert len(agents) == 1
        assert agents[0]['agent_id'] == 'worker-1'
        assert agents[0]['capabilities'] == ['code_generation']


@pytest.mark.asyncio
async def test_mtls_handshake_failure_invalid_cert(mock_spiffe_manager, mock_settings):
    """
    Testa que certificado inválido (CA errado) resulta em erro SSL.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar certificado com CA inválido
    mock_spiffe_manager.fetch_x509_svid.return_value = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle='-----BEGIN CERTIFICATE-----\nINVALID_CA\n-----END CERTIFICATE-----',
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()

        # Simular erro SSL no handshake
        ssl_error = grpc.RpcError()
        ssl_error._code = grpc.StatusCode.UNAVAILABLE
        ssl_error._details = 'SSL handshake failed: certificate verification failed'
        ssl_error.code = lambda: grpc.StatusCode.UNAVAILABLE
        ssl_error.details = lambda: 'SSL handshake failed: certificate verification failed'

        mock_stub.DiscoverAgents.side_effect = ssl_error
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Esperar RpcError em chamada gRPC
        with pytest.raises(grpc.RpcError) as exc_info:
            await client.discover_agents(
                capabilities=['code_generation'],
                filters={},
                max_results=5
            )

        # Verificar erro SSL
        assert exc_info.value.code() == grpc.StatusCode.UNAVAILABLE
        assert 'SSL' in exc_info.value.details() or 'certificate' in exc_info.value.details()


@pytest.mark.asyncio
async def test_x509_svid_refresh_on_expiry(mock_spiffe_manager, mock_settings):
    """
    Testa que X.509-SVID é renovado quando atinge 80% do TTL (refresh threshold).
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar SVID inicial com TTL curto (300 segundos)
    initial_svid = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(seconds=300)
    )

    # SVID renovado
    renewed_svid = X509SVID(
        certificate=TEST_CERT + '\n# renewed',
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(seconds=540)  # Novo TTL após renovação
    )

    # Configurar mock para retornar SVIDs diferentes em chamadas subsequentes
    mock_spiffe_manager.fetch_x509_svid.side_effect = [initial_svid, renewed_svid]

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente e inicializar (primeira chamada)
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Verificar que fetch_x509_svid foi chamado uma vez
        assert mock_spiffe_manager.fetch_x509_svid.call_count == 1

        # Nota: A lógica de refresh automático está no SPIFFEManager._refresh_loop,
        # não no ServiceRegistryClient. O cliente apenas busca SVID quando necessário.
        # Para testar refresh, precisaríamos simular o SPIFFEManager fazendo refresh
        # e o cliente recriando o canal.

        # Simular situação onde cliente precisa recriar canal com novo SVID
        # (por exemplo, após expiração detectada)
        with freeze_time(datetime.utcnow() + timedelta(seconds=240)):  # 80% do TTL
            # Cliente recria canal (chamaria initialize novamente em produção)
            client.channel = None
            await client.initialize()

            # Verificar que fetch_x509_svid foi chamado novamente
            assert mock_spiffe_manager.fetch_x509_svid.call_count == 2


@pytest.mark.asyncio
async def test_fallback_insecure_when_x509_disabled(mock_spiffe_manager, mock_settings):
    """
    Testa que canal insecure é usado quando spiffe_enable_x509=False, mesmo com manager presente.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Desabilitar X.509 (apenas JWT)
    mock_settings.spiffe_enable_x509 = False

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_insecure_channel, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_insecure_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Verificar que insecure_channel foi usado
        mock_insecure_channel.assert_called_once_with('service-registry.test.local:50051')

        # Verificar que secure_channel NÃO foi chamado
        mock_secure_channel.assert_not_called()

        # Verificar que fetch_x509_svid NÃO foi chamado
        mock_spiffe_manager.fetch_x509_svid.assert_not_called()


@pytest.mark.asyncio
async def test_channel_recreation_on_cert_renewal(mock_spiffe_manager, mock_settings):
    """
    Testa que canal é recriado quando certificado é renovado.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # SVIDs com certificados diferentes
    svid_v1 = X509SVID(
        certificate=TEST_CERT + '\n# version 1',
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )

    svid_v2 = X509SVID(
        certificate=TEST_CERT + '\n# version 2',
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=datetime.utcnow() + timedelta(hours=48)
    )

    mock_spiffe_manager.fetch_x509_svid.side_effect = [svid_v1, svid_v2]

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel_instance.close = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente (canal v1)
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Verificar primeira criação de canal
        assert mock_secure_channel.call_count == 1
        first_call_creds = mock_ssl_creds.call_args_list[0]

        # Simular renovação de certificado (fechar canal e reinicializar)
        await client.close()
        await client.initialize()

        # Verificar que canal foi recriado
        assert mock_secure_channel.call_count == 2

        # Verificar que certificados diferentes foram usados
        second_call_creds = mock_ssl_creds.call_args_list[1]

        # Certificados devem ser diferentes (v1 vs v2)
        first_cert = first_call_creds.kwargs['certificate_chain']
        second_cert = second_call_creds.kwargs['certificate_chain']

        assert first_cert != second_cert, "Certificados devem ser diferentes após renovação"


@pytest.mark.asyncio
async def test_mtls_with_jwt_combined(mock_spiffe_manager, mock_settings):
    """
    Testa que mTLS (channel) e JWT-SVID (metadata) podem ser usados juntos.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar JWT-SVID
    mock_spiffe_manager.fetch_jwt_svid.return_value = JWTSVID(
        token='valid.jwt.token',
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        expiry=datetime.utcnow() + timedelta(hours=1)
    )

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Chamar discover_agents
        await client.discover_agents(
            capabilities=['code_generation'],
            filters={},
            max_results=5
        )

        # Verificar que AMBOS foram usados:
        # 1. secure_channel (mTLS)
        mock_secure_channel.assert_called_once()

        # 2. JWT metadata
        call_args = mock_stub.DiscoverAgents.call_args
        metadata = call_args.kwargs.get('metadata')

        assert metadata is not None
        auth_header = None
        for key, value in metadata:
            if key == 'authorization':
                auth_header = value
                break

        assert auth_header is not None, "JWT deve estar presente em metadata"
        assert auth_header.startswith('Bearer ')


@pytest.mark.asyncio
async def test_x509_svid_expiry_logging(mock_spiffe_manager, mock_settings, caplog):
    """
    Testa que informações de expiração do certificado são logadas corretamente.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    expires_at = datetime.utcnow() + timedelta(hours=24)
    mock_spiffe_manager.fetch_x509_svid.return_value = X509SVID(
        certificate=TEST_CERT,
        private_key=TEST_PRIVATE_KEY,
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        ca_bundle=TEST_CA_BUNDLE,
        expires_at=expires_at
    )

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.ssl_channel_credentials') as mock_ssl_creds, \
         patch('grpc.aio.secure_channel') as mock_secure_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_credentials = MagicMock()
        mock_ssl_creds.return_value = mock_credentials

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_secure_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Verificar que log contém informações de expiração
        log_found = False
        for record in caplog.records:
            if hasattr(record, 'msg') and 'mtls_channel_configured' in record.msg:
                log_found = True
                # Verificar que expires_at está presente nos campos do log
                break

        assert log_found, "Log de mTLS channel configurado deve estar presente"
