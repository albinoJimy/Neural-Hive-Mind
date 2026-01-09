"""
Testes unitários para o cliente gRPC do Queen Agent.

Valida comunicação entre Consensus Engine e Queen Agent via gRPC.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import grpc
import uuid


@pytest.fixture
def mock_queen_agent_config():
    """Configuração mock para o cliente Queen Agent."""
    config = MagicMock()
    config.queen_agent_grpc_host = 'queen-agent'
    config.queen_agent_grpc_port = 50051
    config.spiffe_enabled = False
    config.spiffe_enable_x509 = False
    config.environment = 'development'
    return config


@pytest.fixture
def mock_queen_agent_config_with_mtls():
    """Configuração mock com mTLS habilitado."""
    config = MagicMock()
    config.queen_agent_grpc_host = 'queen-agent'
    config.queen_agent_grpc_port = 50051
    config.spiffe_enabled = True
    config.spiffe_enable_x509 = True
    config.spiffe_socket_path = 'unix:///run/spire/sockets/agent.sock'
    config.spiffe_trust_domain = 'neural-hive.local'
    config.spiffe_jwt_audience = 'neural-hive.local'
    config.spiffe_jwt_ttl_seconds = 3600
    config.environment = 'production'
    return config


@pytest.fixture
def sample_strategic_decision_response():
    """Response mock de decisão estratégica."""
    response = MagicMock()
    response.decision_id = str(uuid.uuid4())
    response.decision_type = 'SLA_VIOLATION_RESPONSE'
    response.confidence_score = 0.85
    response.risk_score = 0.2
    response.reasoning_summary = 'Decisão baseada em análise de SLA'
    response.action = 'SCALE_UP'
    response.target_entities = ['service-a', 'service-b']
    response.created_at = 1704067200000
    return response


@pytest.fixture
def sample_system_status_response():
    """Response mock de status do sistema."""
    response = MagicMock()
    response.system_score = 0.92
    response.sla_compliance = 0.98
    response.error_rate = 0.02
    response.resource_saturation = 0.65
    response.active_incidents = 1
    response.timestamp = 1704067200000
    return response


@pytest.fixture
def sample_make_decision_response():
    """Response mock de criação de decisão."""
    response = MagicMock()
    response.success = True
    response.decision_id = str(uuid.uuid4())
    response.decision_type = 'RESOURCE_OPTIMIZATION'
    response.confidence_score = 0.88
    response.risk_score = 0.15
    response.reasoning_summary = 'Otimização baseada em métricas'
    response.message = 'Decisão criada com sucesso'
    return response


@pytest.fixture
def sample_list_decisions_response(sample_strategic_decision_response):
    """Response mock de listagem de decisões."""
    response = MagicMock()
    response.decisions = [sample_strategic_decision_response]
    response.total = 1
    return response


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueenAgentGRPCClientInitialization:
    """Testes de inicialização do cliente."""

    @patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel')
    @patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel')
    async def test_initialize_insecure_channel(
        self,
        mock_instrument,
        mock_insecure_channel,
        mock_queen_agent_config
    ):
        """Verifica inicialização com canal inseguro em desenvolvimento."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        mock_channel = AsyncMock()
        mock_channel.channel_ready = AsyncMock()
        mock_insecure_channel.return_value = mock_channel
        mock_instrument.return_value = mock_channel

        client = QueenAgentGRPCClient(mock_queen_agent_config)
        await client.initialize()

        mock_insecure_channel.assert_called_once()
        assert client.channel is not None
        assert client.stub is not None

        await client.close()

    async def test_initialize_handles_timeout(self, mock_queen_agent_config):
        """Verifica tratamento de timeout na inicialização."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient
        import asyncio

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_channel.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                client = QueenAgentGRPCClient(mock_queen_agent_config)
                # Não deve lançar exceção, apenas log warning
                await client.initialize()
                await client.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueenAgentGRPCClientGetDecision:
    """Testes de busca de decisão estratégica."""

    async def test_get_strategic_decision_success(
        self,
        mock_queen_agent_config,
        sample_strategic_decision_response
    ):
        """Verifica busca de decisão com sucesso."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    mock_stub.GetStrategicDecision = AsyncMock(
                        return_value=sample_strategic_decision_response
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.get_strategic_decision('dec-123')

                    assert result is not None
                    assert result['decision_id'] == sample_strategic_decision_response.decision_id
                    assert result['decision_type'] == 'SLA_VIOLATION_RESPONSE'
                    assert result['confidence_score'] == 0.85

                    await client.close()

    async def test_get_strategic_decision_not_initialized(self, mock_queen_agent_config):
        """Verifica retorno None quando stub não inicializado."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        client = QueenAgentGRPCClient(mock_queen_agent_config)
        # Não inicializar

        result = await client.get_strategic_decision('dec-123')

        assert result is None

    async def test_get_strategic_decision_retry_on_unavailable(
        self,
        mock_queen_agent_config,
        sample_strategic_decision_response
    ):
        """Verifica retry quando serviço está indisponível."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()

                    # Primeiro: erro, segundo: sucesso
                    rpc_error = grpc.aio.AioRpcError(
                        code=grpc.StatusCode.UNAVAILABLE,
                        initial_metadata=None,
                        trailing_metadata=None,
                        details='Service unavailable'
                    )

                    mock_stub.GetStrategicDecision = AsyncMock(
                        side_effect=[rpc_error, sample_strategic_decision_response]
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    with patch('asyncio.sleep', new_callable=AsyncMock):
                        result = await client.get_strategic_decision('dec-123')

                    assert result is not None
                    assert result['decision_id'] == sample_strategic_decision_response.decision_id

                    await client.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueenAgentGRPCClientMakeDecision:
    """Testes de criação de decisão estratégica."""

    async def test_make_strategic_decision_success(
        self,
        mock_queen_agent_config,
        sample_make_decision_response
    ):
        """Verifica criação de decisão com sucesso."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    mock_stub.MakeStrategicDecision = AsyncMock(
                        return_value=sample_make_decision_response
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.make_strategic_decision(
                        event_type='sla_violation',
                        source_id='consensus-engine',
                        trigger_data={'severity': 'high'}
                    )

                    assert result is not None
                    assert result['success'] is True
                    assert result['decision_id'] == sample_make_decision_response.decision_id

                    await client.close()

    async def test_make_strategic_decision_failure(self, mock_queen_agent_config):
        """Verifica tratamento de falha na criação."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    failed_response = MagicMock()
                    failed_response.success = False
                    failed_response.message = 'Decisão rejeitada'
                    mock_stub.MakeStrategicDecision = AsyncMock(return_value=failed_response)
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.make_strategic_decision(
                        event_type='test',
                        source_id='test'
                    )

                    assert result is not None
                    assert result['success'] is False
                    assert result['message'] == 'Decisão rejeitada'

                    await client.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueenAgentGRPCClientSystemStatus:
    """Testes de status do sistema."""

    async def test_get_system_status_success(
        self,
        mock_queen_agent_config,
        sample_system_status_response
    ):
        """Verifica busca de status com sucesso."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    mock_stub.GetSystemStatus = AsyncMock(
                        return_value=sample_system_status_response
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.get_system_status()

                    assert result is not None
                    assert result['system_score'] == 0.92
                    assert result['sla_compliance'] == 0.98
                    assert result['active_incidents'] == 1

                    await client.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueenAgentGRPCClientListDecisions:
    """Testes de listagem de decisões."""

    async def test_list_strategic_decisions_success(
        self,
        mock_queen_agent_config,
        sample_list_decisions_response
    ):
        """Verifica listagem de decisões com sucesso."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    mock_stub.ListStrategicDecisions = AsyncMock(
                        return_value=sample_list_decisions_response
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.list_strategic_decisions(
                        decision_type='SLA_VIOLATION_RESPONSE',
                        limit=10
                    )

                    assert result is not None
                    assert result['total'] == 1
                    assert len(result['decisions']) == 1

                    await client.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestQueenAgentGRPCClientHealthCheck:
    """Testes de health check."""

    async def test_health_check_healthy(
        self,
        mock_queen_agent_config,
        sample_system_status_response
    ):
        """Verifica health check quando serviço está saudável."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    mock_stub.GetSystemStatus = AsyncMock(
                        return_value=sample_system_status_response
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.health_check()

                    assert result['status'] == 'SERVING'
                    assert 'details' in result

                    await client.close()

    async def test_health_check_unhealthy(self, mock_queen_agent_config):
        """Verifica health check quando serviço está indisponível."""
        from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

        with patch('src.clients.queen_agent_grpc_client.grpc.aio.insecure_channel') as mock_channel_cls:
            channel = AsyncMock()
            channel.channel_ready = AsyncMock()
            mock_channel_cls.return_value = channel

            with patch('src.clients.queen_agent_grpc_client.instrument_grpc_channel', return_value=channel):
                with patch('src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub') as mock_stub_cls:
                    mock_stub = AsyncMock()
                    mock_stub.GetSystemStatus = AsyncMock(
                        side_effect=Exception('Connection refused')
                    )
                    mock_stub_cls.return_value = mock_stub

                    client = QueenAgentGRPCClient(mock_queen_agent_config)
                    await client.initialize()

                    result = await client.health_check()

                    assert result['status'] == 'NOT_SERVING'
                    assert 'error' in result

                    await client.close()
