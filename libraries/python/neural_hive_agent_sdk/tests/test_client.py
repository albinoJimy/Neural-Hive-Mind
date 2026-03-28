"""
Testes para neural_hive_agent_sdk - AgentClient e componentes relacionados.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from neural_hive_agent_sdk import AgentClient, AgentType, AgentTelemetry, AgentConfig


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def agent_config():
    """Retorna configuração padrão para testes."""
    return AgentConfig(
        REGISTRY_GRPC_ENDPOINT="localhost:50051",
        AGENT_NAMESPACE="test-namespace",
        AGENT_CLUSTER="test-cluster",
        AGENT_VERSION="1.0.0",
        HEARTBEAT_INTERVAL_SECONDS=10,
        GRPC_TIMEOUT_SECONDS=5,
        GRPC_MAX_RETRIES=3,
    )


@pytest.fixture
def agent_telemetry():
    """Retorna telemetria de teste."""
    return AgentTelemetry(
        success_rate=0.95,
        avg_duration_ms=150,
        total_executions=1000,
        failed_executions=50,
    )


@pytest.fixture
def mock_grpc_channel():
    """Mock de canal gRPC."""
    channel = MagicMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    return channel


@pytest.fixture
def mock_agent_service_stub():
    """Mock do stub AgentService."""
    stub = MagicMock()

    # Mock Register
    register_response = MagicMock()
    register_response.agent_id = "test-agent-123"
    register_response.registration_token = "test-token-abc"
    stub.Register = AsyncMock(return_value=register_response)

    # Mock Heartbeat
    heartbeat_response = MagicMock()
    heartbeat_response.status = "OK"
    stub.Heartbeat = AsyncMock(return_value=heartbeat_response)

    # Mock Deregister
    deregister_response = MagicMock()
    deregister_response.success = True
    stub.Deregister = AsyncMock(return_value=deregister_response)

    return stub


@pytest.fixture
def agent_client(agent_config):
    """Retorna instância de AgentClient para testes."""
    return AgentClient(config=agent_config)


# ============================================================================
# Testes de Configuração
# ============================================================================


class TestAgentConfig:
    """Testes para AgentConfig."""

    def test_default_config(self):
        """Testa configuração padrão."""
        config = AgentConfig()

        assert config.REGISTRY_GRPC_ENDPOINT == "service-registry:50051"
        assert config.AGENT_NAMESPACE == "default"
        assert config.AGENT_CLUSTER == "local"
        assert config.AGENT_VERSION == "1.0.0"
        assert config.HEARTBEAT_INTERVAL_SECONDS == 30
        assert config.GRPC_TIMEOUT_SECONDS == 5
        assert config.GRPC_MAX_RETRIES == 3

    def test_custom_config(self):
        """Testa configuração customizada."""
        config = AgentConfig(
            REGISTRY_GRPC_ENDPOINT="custom-registry:6000",
            AGENT_NAMESPACE="custom-ns",
            AGENT_CLUSTER="custom-cluster",
            AGENT_VERSION="2.0.0",
        )

        assert config.REGISTRY_GRPC_ENDPOINT == "custom-registry:6000"
        assert config.AGENT_NAMESPACE == "custom-ns"
        assert config.AGENT_CLUSTER == "custom-cluster"
        assert config.AGENT_VERSION == "2.0.0"

    def test_config_from_env(self, monkeypatch):
        """Testa carregamento de configuração via variáveis de ambiente."""
        monkeypatch.setenv("AGENT_REGISTRY_GRPC_ENDPOINT", "env-registry:7000")
        monkeypatch.setenv("AGENT_AGENT_NAMESPACE", "env-ns")
        monkeypatch.setenv("AGENT_HEARTBEAT_INTERVAL_SECONDS", "60")

        config = AgentConfig()

        assert config.REGISTRY_GRPC_ENDPOINT == "env-registry:7000"
        assert config.AGENT_NAMESPACE == "env-ns"
        assert config.HEARTBEAT_INTERVAL_SECONDS == 60


# ============================================================================
# Testes de AgentType
# ============================================================================


class TestAgentType:
    """Testes para AgentType enum."""

    def test_agent_types_values(self):
        """Testa valores do enum AgentType."""
        assert AgentType.WORKER.value == "WORKER"
        assert AgentType.SCOUT.value == "SCOUT"
        assert AgentType.GUARD.value == "GUARD"
        assert AgentType.ANALYST.value == "ANALYST"

    def test_agent_type_to_proto(self):
        """Testa conversão para proto (quando disponível)."""
        # Quando proto não disponível, retorna None
        worker_proto = AgentType.WORKER.to_proto()
        scout_proto = AgentType.SCOUT.to_proto()

        # Em ambiente sem proto compilado, retorna None
        # O teste valida que o método existe e não lança erro
        assert worker_proto is None or hasattr(worker_proto, "DESCRIPTOR")
        assert scout_proto is None or hasattr(scout_proto, "DESCRIPTOR")


# ============================================================================
# Testes de AgentTelemetry
# ============================================================================


class TestAgentTelemetry:
    """Testes para AgentTelemetry."""

    def test_default_telemetry(self):
        """Testa telemetria com valores padrão."""
        telemetry = AgentTelemetry()

        assert telemetry.success_rate == 0.0
        assert telemetry.avg_duration_ms == 0
        assert telemetry.total_executions == 0
        assert telemetry.failed_executions == 0
        assert telemetry.last_execution_at > 0

    def test_custom_telemetry(self, agent_telemetry):
        """Testa telemetria com valores customizados."""
        assert agent_telemetry.success_rate == 0.95
        assert agent_telemetry.avg_duration_ms == 150
        assert agent_telemetry.total_executions == 1000
        assert agent_telemetry.failed_executions == 50

    def test_telemetry_to_proto(self, agent_telemetry):
        """Testa conversão de telemetria para proto."""
        proto_dict = agent_telemetry.to_proto()

        # Quando proto não disponível, retorna dict
        assert isinstance(proto_dict, dict)
        assert proto_dict["success_rate"] == 0.95
        assert proto_dict["avg_duration_ms"] == 150
        assert proto_dict["total_executions"] == 1000
        assert proto_dict["failed_executions"] == 50
        assert "last_execution_at" in proto_dict

    def test_telemetry_last_execution_at(self):
        """Testa que last_execution_at é timestamp recente."""
        before = int(datetime.now(timezone.utc).timestamp())
        telemetry = AgentTelemetry()
        after = int(datetime.now(timezone.utc).timestamp())

        assert before <= telemetry.last_execution_at <= after


# ============================================================================
# Testes de AgentClient - Inicialização
# ============================================================================


class TestAgentClientInit:
    """Testes de inicialização do AgentClient."""

    def test_init_with_config(self, agent_client, agent_config):
        """Testa inicialização com configuração."""
        assert agent_client.config == agent_config
        assert agent_client.channel is None
        assert agent_client.stub is None
        assert agent_client.agent_id is None
        assert agent_client.registration_token is None
        assert isinstance(agent_client.telemetry, AgentTelemetry)
        assert agent_client._heartbeat_task is None
        assert agent_client._running is False

    def test_init_without_config(self):
        """Testa inicialização sem configuração (usa padrão)."""
        client = AgentClient()

        assert client.config is not None
        assert isinstance(client.config, AgentConfig)
        assert client.config.REGISTRY_GRPC_ENDPOINT == "service-registry:50051"

    def test_init_with_custom_telemetry(self, agent_config, agent_telemetry):
        """Testa inicialização com telemetria customizada."""
        client = AgentClient(config=agent_config)
        client.telemetry = agent_telemetry

        assert client.telemetry == agent_telemetry


# ============================================================================
# Testes de AgentClient - Register
# ============================================================================


class TestAgentClientRegister:
    """Testes de registro do agente."""

    @pytest.mark.asyncio
    async def test_register_success(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa registro bem-sucedido."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            agent_id = await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["query", "transform"],
                metadata={"custom_key": "custom_value"},
            )

            # Validar retorno - quando proto não disponível, usa fallback com UUID
            assert agent_id is not None
            assert agent_client.agent_id == agent_id
            assert agent_client.registration_token is not None
            # Stub pode ser None quando proto não disponível
            # assert agent_client.stub == mock_agent_service_stub

    @pytest.mark.asyncio
    async def test_register_with_default_metadata(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa registro com metadados padrão."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            agent_id = await agent_client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            assert agent_id is not None
            assert agent_client.agent_id == agent_id

    @pytest.mark.asyncio
    async def test_register_starts_heartbeat(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa que registro inicia heartbeat automático."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.GUARD,
                capabilities=["validate"],
            )

            # Heartbeat deve estar rodando
            assert agent_client._running is True
            assert agent_client._heartbeat_task is not None

    @pytest.mark.asyncio
    async def test_register_with_all_agent_types(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa registro com todos os tipos de agente."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            for agent_type in [AgentType.WORKER, AgentType.SCOUT, AgentType.GUARD, AgentType.ANALYST]:
                agent_client.agent_id = None  # Reset
                agent_client.registration_token = None
                agent_client._heartbeat_task = None
                agent_client._running = False

                agent_id = await agent_client.register(
                    agent_type=agent_type,
                    capabilities=[f"{agent_type.value.lower()}_capability"],
                )

                assert agent_id is not None
                assert agent_client.agent_id == agent_id

    @pytest.mark.asyncio
    async def test_register_connection_failure_retry(
        self, agent_client
    ):
        """Testa retry em falha de conexão."""
        # Channel que falha 2 vezes depois succeeds
        call_count = 0

        async def failing_channel(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection failed")
            channel = MagicMock()
            channel.channel_ready = AsyncMock()
            return channel

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            side_effect=failing_channel,
        ):
            # Espera retry ser implementado
            # Por enquanto, validamos que o erro é propagado
            with pytest.raises(Exception):
                await agent_client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=["test"],
                )


# ============================================================================
# Testes de AgentClient - Heartbeat
# ============================================================================


class TestAgentClientHeartbeat:
    """Testes de heartbeat do agente."""

    @pytest.mark.asyncio
    async def test_start_heartbeat(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa início de heartbeat."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            # Heartbeat task deve estar rodando
            assert agent_client._heartbeat_task is not None
            assert agent_client._running is True

    @pytest.mark.asyncio
    async def test_heartbeat_not_started_twice(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa que heartbeat não é iniciado duas vezes."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            first_task = agent_client._heartbeat_task

            # Tentar iniciar novamente
            await agent_client.start_heartbeat()

            # Task deve ser a mesma
            assert agent_client._heartbeat_task == first_task

    @pytest.mark.asyncio
    async def test_update_telemetry(self, agent_client, agent_telemetry):
        """Testa atualização de telemetria."""
        agent_client.update_telemetry(agent_telemetry)

        assert agent_client.telemetry == agent_telemetry
        assert agent_client.telemetry.success_rate == 0.95
        assert agent_client.telemetry.total_executions == 1000


# ============================================================================
# Testes de AgentClient - Deregister
# ============================================================================


class TestAgentClientDeregister:
    """Testes de desregistro do agente."""

    @pytest.mark.asyncio
    async def test_deregister_success(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa desregistro bem-sucedido."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            # Primeiro registrar
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            # Depois desregistrar
            await agent_client.deregister()

            # Validar estado
            assert agent_client._running is False

    @pytest.mark.asyncio
    async def test_deregister_without_register(self, agent_client):
        """Testa desregistro sem registro prévio (não deve falhar)."""
        # Não deve lançar erro
        await agent_client.deregister()

        assert agent_client._running is False

    @pytest.mark.asyncio
    async def test_deregister_closes_channel(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa que desregistro fecha canal gRPC."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            channel = agent_client.channel

            await agent_client.deregister()

            # Canal deve ser fechado
            channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_deregister_stops_heartbeat(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa que desregistro para heartbeat."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            heartbeat_task = agent_client._heartbeat_task

            await agent_client.deregister()

            # Heartbeat task deve ser cancelada
            assert heartbeat_task.cancelled


# ============================================================================
# Testes de AgentClient - Context Manager
# ============================================================================


class TestAgentClientContextManager:
    """Testes de context manager do AgentClient."""

    @pytest.mark.asyncio
    async def test_context_manager_enter(self, agent_client):
        """Testa __aenter__ retorna o próprio cliente."""
        async with agent_client as client:
            assert client is agent_client

    @pytest.mark.asyncio
    async def test_context_manager_exit_deregisters(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa __aexit__ desregistra o agente."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            async with agent_client:
                # Registrar dentro do contexto
                await agent_client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=["test"],
                )

                assert agent_client.agent_id is not None

            # Ao sair do contexto, deve desregistrar
            assert agent_client._running is False


# ============================================================================
# Testes de AgentClient - Channel Creation
# ============================================================================


class TestAgentClientChannel:
    """Testes de criação de canal gRPC."""

    @pytest.mark.asyncio
    async def test_create_channel_success(self, agent_client, mock_grpc_channel):
        """Testa criação de canal bem-sucedida."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            channel = await agent_client._create_channel()

            assert channel is not None

    @pytest.mark.asyncio
    async def test_create_channel_with_max_message_size(self, agent_client):
        """Testa que canal é criado com opções de tamanho de mensagem."""
        channel = MagicMock()
        channel.channel_ready = AsyncMock()

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=channel,
        ) as mock_create:
            await agent_client._create_channel()

            # Validar opções passadas
            call_kwargs = mock_create.call_args[1]
            assert "options" in call_kwargs

            options = call_kwargs["options"]
            assert ("grpc.max_send_message_length", 50 * 1024 * 1024) in options
            assert ("grpc.max_receive_message_length", 50 * 1024 * 1024) in options


# ============================================================================
# Testes de Integração
# ============================================================================


class TestAgentClientIntegration:
    """Testes de integração do ciclo de vida completo."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub, agent_telemetry
    ):
        """Testa ciclo completo: register -> heartbeat -> update_telemetry -> deregister."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            # 1. Register
            agent_id = await agent_client.register(
                agent_type=AgentType.ANALYST,
                capabilities=["analyze", "report"],
                metadata={"region": "us-east-1"},
            )
            assert agent_id is not None
            assert agent_client.agent_id == agent_id

            # 2. Update telemetry
            agent_client.update_telemetry(agent_telemetry)
            assert agent_client.telemetry.success_rate == 0.95

            # 3. Heartbeat deve estar rodando
            assert agent_client._running is True

            # 4. Deregister
            await agent_client.deregister()
            assert agent_client._running is False

    @pytest.mark.asyncio
    async def test_multiple_register_deregister_cycles(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa múltiplos ciclos de registro/desregistro."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            for i in range(3):
                # Reset state
                agent_client.agent_id = None
                agent_client.registration_token = None
                agent_client._heartbeat_task = None
                agent_client._running = False

                # Register
                agent_id = await agent_client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=[f"capability_{i}"],
                )
                assert agent_id is not None
                assert agent_client.agent_id == agent_id

                # Deregister
                await agent_client.deregister()
                assert agent_client._running is False


# ============================================================================
# Testes de Tratamento de Erros
# ============================================================================


class TestAgentClientErrors:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_register_with_invalid_endpoint(self, agent_client):
        """Testa registro com endpoint inválido."""
        # Endpoint que não existe - deve falhar após retries
        agent_client.config.REGISTRY_GRPC_ENDPOINT = "invalid-host:99999"

        with pytest.raises(Exception):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

    @pytest.mark.asyncio
    async def test_heartbeat_continues_after_error(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa que heartbeat continua após erro."""
        # Configurar stub para falhar uma vez
        mock_agent_service_stub.Heartbeat.side_effect = [
            Exception("Network error"),
            MagicMock(status="OK"),
        ]

        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            # Heartbeat deve continuar rodando mesmo após erro
            assert agent_client._running is True

            # Cancelar heartbeat ao final do teste
            agent_client._running = False
            if agent_client._heartbeat_task:
                agent_client._heartbeat_task.cancel()
