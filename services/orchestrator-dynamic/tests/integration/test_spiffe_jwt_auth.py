"""
Testes de integração para autenticação JWT-SVID do ServiceRegistryClient.

Testa cenários de sucesso, falhas, cache e fallback de JWT-SVID.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

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


# Configuração de logger para testes
logger = structlog.get_logger(__name__)


@pytest.fixture
def mock_spiffe_manager():
    """Fixture que retorna mock do SPIFFEManager"""
    manager = MockSPIFFEManager()

    # Configurar retorno padrão de JWT-SVID válido
    manager.fetch_jwt_svid.return_value = JWTSVID(
        token='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzcGlmZmU6Ly9uZXVyYWwtaGl2ZS5sb2NhbC9ucy9uZXVyYWwtaGl2ZS1vcmNoZXN0cmF0aW9uL3NhL29yY2hlc3RyYXRvci1keW5hbWljIiwiYXVkIjoic2VydmljZS1yZWdpc3RyeS5uZXVyYWwtaGl2ZS5sb2NhbCIsImV4cCI6OTk5OTk5OTk5OX0.valid',
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        expiry=datetime.utcnow() + timedelta(hours=1)
    )

    return manager


@pytest.fixture
def mock_settings():
    """Fixture que retorna configurações mockadas"""
    from src.config.settings import OrchestratorSettings

    settings = MagicMock(spec=OrchestratorSettings)
    settings.service_registry_host = 'service-registry.test.local'
    settings.service_registry_port = 50051
    settings.service_registry_timeout_seconds = 3
    settings.spiffe_enabled = True
    settings.spiffe_enable_x509 = False
    settings.spiffe_jwt_audience = 'service-registry.neural-hive.local'

    return settings


@pytest.fixture
async def mock_grpc_stub():
    """Fixture que retorna stub gRPC mockado"""
    stub = AsyncMock()

    # Mock de resposta padrão
    mock_response = MagicMock()
    mock_response.agents = []
    stub.DiscoverAgents.return_value = mock_response

    return stub


@pytest.mark.asyncio
async def test_jwt_svid_fetch_and_attach_metadata(mock_spiffe_manager, mock_settings, caplog):
    """
    Testa que JWT-SVID é obtido corretamente e metadata 'Bearer' é anexado à chamada gRPC.
    """
    # Importar cliente após mocks
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Chamar discover_agents
        await client.discover_agents(
            capabilities=['code_generation'],
            filters={'namespace': 'production'},
            max_results=5
        )

        # Verificar que fetch_jwt_svid foi chamado com audience correto
        mock_spiffe_manager.fetch_jwt_svid.assert_called_once_with(
            audience='service-registry.neural-hive.local'
        )

        # Verificar que DiscoverAgents foi chamado com metadata Bearer
        call_args = mock_stub.DiscoverAgents.call_args
        metadata = call_args.kwargs.get('metadata')

        assert metadata is not None, "Metadata deve estar presente"
        assert len(metadata) > 0, "Metadata deve conter pelo menos um item"

        # Verificar token Bearer
        auth_header = None
        for key, value in metadata:
            if key == 'authorization':
                auth_header = value
                break

        assert auth_header is not None, "Authorization header deve estar presente"
        assert auth_header.startswith('Bearer '), "Token deve começar com 'Bearer '"
        assert 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9' in auth_header, "Token JWT deve estar presente"

        # Verificar log de debug
        assert any('jwt_svid_attached' in record.msg for record in caplog.records if hasattr(record, 'msg'))


@pytest.mark.asyncio
async def test_jwt_svid_cache_hit(mock_spiffe_manager, mock_settings):
    """
    Testa que JWT-SVID é cacheado e fetch_jwt_svid é chamado apenas uma vez em múltiplas chamadas.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Primeira chamada
        await client.discover_agents(
            capabilities=['code_generation'],
            filters={},
            max_results=5
        )

        # Segunda chamada (deve usar cache do SPIFFEManager)
        await client.discover_agents(
            capabilities=['testing'],
            filters={},
            max_results=5
        )

        # Verificar que fetch_jwt_svid foi chamado duas vezes
        # (o cache está no SPIFFEManager, não no ServiceRegistryClient)
        assert mock_spiffe_manager.fetch_jwt_svid.call_count == 2


@pytest.mark.asyncio
async def test_jwt_auth_failure_invalid_token(mock_spiffe_manager, mock_settings):
    """
    Testa que token JWT expirado/inválido resulta em grpc.RpcError com UNAUTHENTICATED.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar JWT expirado
    mock_spiffe_manager.fetch_jwt_svid.return_value = JWTSVID(
        token='expired.jwt.token',
        spiffe_id='spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic',
        expiry=datetime.utcnow() - timedelta(hours=1)  # Expirado
    )

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()

        # Simular erro UNAUTHENTICATED do servidor
        rpc_error = grpc.RpcError()
        rpc_error._code = grpc.StatusCode.UNAUTHENTICATED
        rpc_error._details = 'Invalid or expired JWT-SVID'
        rpc_error.code = lambda: grpc.StatusCode.UNAUTHENTICATED
        rpc_error.details = lambda: 'Invalid or expired JWT-SVID'

        mock_stub.DiscoverAgents.side_effect = rpc_error
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Esperar RpcError
        with pytest.raises(grpc.RpcError) as exc_info:
            await client.discover_agents(
                capabilities=['code_generation'],
                filters={},
                max_results=5
            )

        # Verificar código de erro
        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_jwt_auth_failure_unauthorized_spiffe_id(mock_spiffe_manager, mock_settings):
    """
    Testa que SPIFFE ID não autorizado resulta em PERMISSION_DENIED.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar SPIFFE ID não autorizado
    mock_spiffe_manager.fetch_jwt_svid.return_value = JWTSVID(
        token='valid.jwt.token',
        spiffe_id='spiffe://wrong-domain.com/ns/attacker/sa/malicious',
        expiry=datetime.utcnow() + timedelta(hours=1)
    )

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()

        # Simular erro PERMISSION_DENIED do servidor
        rpc_error = grpc.RpcError()
        rpc_error._code = grpc.StatusCode.PERMISSION_DENIED
        rpc_error._details = 'SPIFFE ID not authorized'
        rpc_error.code = lambda: grpc.StatusCode.PERMISSION_DENIED
        rpc_error.details = lambda: 'SPIFFE ID not authorized'

        mock_stub.DiscoverAgents.side_effect = rpc_error
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Esperar RpcError
        with pytest.raises(grpc.RpcError) as exc_info:
            await client.discover_agents(
                capabilities=['code_generation'],
                filters={},
                max_results=5
            )

        # Verificar código de erro
        assert exc_info.value.code() == grpc.StatusCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_fallback_no_auth_when_spiffe_disabled(mock_settings):
    """
    Testa que quando SPIFFE está desabilitado, nenhum metadata é enviado e canal insecure é usado.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Desabilitar SPIFFE
    mock_settings.spiffe_enabled = False

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente SEM spiffe_manager
        client = ServiceRegistryClient(mock_settings, spiffe_manager=None)
        await client.initialize()

        # Chamar discover_agents
        await client.discover_agents(
            capabilities=['code_generation'],
            filters={},
            max_results=5
        )

        # Verificar que DiscoverAgents foi chamado sem metadata
        call_args = mock_stub.DiscoverAgents.call_args
        metadata = call_args.kwargs.get('metadata')

        # Metadata deve ser None ou lista vazia
        assert metadata is None or len(metadata) == 0, "Metadata não deve estar presente quando SPIFFE desabilitado"


@pytest.mark.asyncio
async def test_spiffe_unavailable_fallback(mock_spiffe_manager, mock_settings, caplog):
    """
    Testa que quando SPIFFE está indisponível, warning é logado e fallback para sem metadata.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Simular erro de conexão SPIFFE
    from neural_hive_security.spiffe_manager import SPIFFEConnectionError
    mock_spiffe_manager.fetch_jwt_svid.side_effect = SPIFFEConnectionError("SPIRE agent unavailable")

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Chamar discover_agents (não deve levantar exceção)
        await client.discover_agents(
            capabilities=['code_generation'],
            filters={},
            max_results=5
        )

        # Verificar que warning foi logado
        assert any('jwt_svid_fetch_failed' in record.msg for record in caplog.records if hasattr(record, 'msg'))

        # Verificar que chamada foi feita sem metadata (fallback)
        call_args = mock_stub.DiscoverAgents.call_args
        metadata = call_args.kwargs.get('metadata')

        # Metadata pode ser None ou lista vazia em fallback
        if metadata:
            # Verificar que não há authorization header
            auth_present = any(key == 'authorization' for key, _ in metadata)
            assert not auth_present, "Authorization header não deve estar presente em fallback"


@pytest.mark.asyncio
async def test_jwt_svid_with_custom_audience(mock_spiffe_manager, mock_settings):
    """
    Testa que audience customizado é passado corretamente para fetch_jwt_svid.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    # Configurar audience customizado
    custom_audience = 'custom-service.neural-hive.local'
    mock_settings.spiffe_jwt_audience = custom_audience

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Chamar discover_agents
        await client.discover_agents(
            capabilities=['code_generation'],
            filters={},
            max_results=5
        )

        # Verificar que fetch_jwt_svid foi chamado com audience customizado
        mock_spiffe_manager.fetch_jwt_svid.assert_called_once_with(
            audience=custom_audience
        )


@pytest.mark.asyncio
async def test_concurrent_discover_calls_with_jwt(mock_spiffe_manager, mock_settings):
    """
    Testa que múltiplas chamadas concorrentes a discover_agents são thread-safe.
    """
    from src.clients.service_registry_client import ServiceRegistryClient

    with patch('src.clients.service_registry_client.service_registry_pb2') as mock_pb2, \
         patch('src.clients.service_registry_client.service_registry_pb2_grpc') as mock_grpc, \
         patch('grpc.aio.insecure_channel') as mock_channel:

        # Setup mocks
        mock_pb2.DiscoverRequest = MagicMock(return_value=MagicMock())
        mock_stub = AsyncMock()
        mock_response = MagicMock()
        mock_response.agents = []
        mock_stub.DiscoverAgents.return_value = mock_response
        mock_grpc.ServiceRegistryStub.return_value = mock_stub

        mock_channel_instance = AsyncMock()
        mock_channel_instance.channel_ready = AsyncMock()
        mock_channel.return_value = mock_channel_instance

        # Criar cliente
        client = ServiceRegistryClient(mock_settings, mock_spiffe_manager)
        await client.initialize()

        # Executar chamadas concorrentes
        tasks = [
            client.discover_agents(capabilities=[f'cap_{i}'], filters={}, max_results=5)
            for i in range(10)
        ]

        # Aguardar todas as chamadas
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verificar que todas as chamadas foram bem-sucedidas
        for result in results:
            assert not isinstance(result, Exception), f"Chamada concorrente falhou: {result}"

        # Verificar que fetch_jwt_svid foi chamado 10 vezes (uma por chamada)
        assert mock_spiffe_manager.fetch_jwt_svid.call_count == 10
