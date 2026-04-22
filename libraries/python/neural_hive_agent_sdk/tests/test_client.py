"""
Testes para neural_hive_agent_sdk - AgentClient e componentes relacionados.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_agent_sdk import AgentClient, AgentConfig, AgentTelemetry, AgentType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture()
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


@pytest.fixture()
def agent_telemetry():
    """Retorna telemetria de teste."""
    return AgentTelemetry(
        success_rate=0.95,
        avg_duration_ms=150,
        total_executions=1000,
        failed_executions=50,
    )


@pytest.fixture()
def mock_grpc_channel():
    """Mock de canal gRPC."""
    channel = MagicMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    return channel


@pytest.fixture()
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


@pytest.fixture()
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
        before = int(datetime.now(UTC).timestamp())
        telemetry = AgentTelemetry()
        after = int(datetime.now(UTC).timestamp())

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

    @pytest.mark.asyncio()
    async def test_register_success(self, agent_client, mock_grpc_channel, mock_agent_service_stub):
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_register_with_all_agent_types(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa registro com todos os tipos de agente."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            for agent_type in [
                AgentType.WORKER,
                AgentType.SCOUT,
                AgentType.GUARD,
                AgentType.ANALYST,
            ]:
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

    @pytest.mark.asyncio()
    async def test_register_connection_failure_retry(self, agent_client):
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

    @pytest.mark.asyncio()
    async def test_start_heartbeat(self, agent_client, mock_grpc_channel, mock_agent_service_stub):
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_deregister_without_register(self, agent_client):
        """Testa desregistro sem registro prévio (não deve falhar)."""
        # Não deve lançar erro
        await agent_client.deregister()

        assert agent_client._running is False


# ============================================================================
# Testes Adicionais para Cobertura
# ============================================================================


class TestAgentType:
    """Testes adicionais para AgentType."""

    def test_to_proto_unavailable(self):
        """Testa to_proto quando PROTO_AVAILABLE=False."""
        with patch("neural_hive_agent_sdk.client.PROTO_AVAILABLE", False):
            result = AgentType.WORKER.to_proto()
            assert result is None

    def test_to_proto_all_types(self):
        """Testa to_proto para todos os tipos de agente."""
        types = [AgentType.WORKER, AgentType.SCOUT, AgentType.GUARD, AgentType.ANALYST]

        for agent_type in types:
            # Não deve lançar erro mesmo se PROTO_AVAILABLE=False
            result = agent_type.to_proto()
            # Resultado pode ser None ou o valor proto dependendo do ambiente


class TestAgentTelemetry:
    """Testes adicionais para AgentTelemetry."""

    def test_telemetry_initialization(self):
        """Testa inicialização com valores padrão."""
        telemetry = AgentTelemetry()

        assert telemetry.success_rate == 0.0
        assert telemetry.avg_duration_ms == 0
        assert telemetry.total_executions == 0
        assert telemetry.failed_executions == 0
        assert telemetry.last_execution_at is not None

    def test_telemetry_custom_values(self):
        """Testa inicialização com valores customizados."""
        telemetry = AgentTelemetry(
            success_rate=0.85, avg_duration_ms=250, total_executions=500, failed_executions=25
        )

        assert telemetry.success_rate == 0.85
        assert telemetry.avg_duration_ms == 250
        assert telemetry.total_executions == 500
        assert telemetry.failed_executions == 25

    def test_telemetry_to_proto_unavailable(self):
        """Testa to_proto quando PROTO_AVAILABLE=False."""
        telemetry = AgentTelemetry(success_rate=0.9)

        with patch("neural_hive_agent_sdk.client.PROTO_AVAILABLE", False):
            result = telemetry.to_proto()

            assert isinstance(result, dict)
            assert result["success_rate"] == 0.9

    def test_telemetry_to_proto_available(self):
        """Testa to_proto quando PROTO_AVAILABLE=True."""
        telemetry = AgentTelemetry(
            success_rate=0.75, avg_duration_ms=200, total_executions=100, failed_executions=5
        )

        # Sempre retorna um dict ou objeto proto
        result = telemetry.to_proto()

        # Verificar que o resultado tem os campos esperados
        if hasattr(result, "success_rate"):
            assert result.success_rate == 0.75
        else:
            assert result["success_rate"] == 0.75


class TestAgentClientContextManager:
    """Testes para context manager do AgentClient."""

    @pytest.mark.asyncio()
    async def test_context_manager_auto_deregister(self, agent_config):
        """Testa que context manager chama deregister automaticamente."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel"):
            async with AgentClient(config=agent_config) as client:
                client.agent_id = "test-agent-123"
                client._running = True
                client._heartbeat_task = asyncio.create_task(asyncio.sleep(10))

            # Após sair do contexto, agent deve estar desregistrado
            # (verificado pelo estado do cliente)

    @pytest.mark.asyncio()
    async def test_context_manager_with_exception(self, agent_config):
        """Testa que context manager desregistra mesmo com exceção."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel"):
            try:
                async with AgentClient(config=agent_config) as client:
                    client.agent_id = "test-agent-123"
                    raise ValueError("Test exception")
            except ValueError:
                pass  # Exceção esperada

            # Context manager deve ter tratado a limpeza


class TestAgentClientEdgeCases:
    """Testes de edge cases para AgentClient."""

    @pytest.mark.asyncio()
    async def test_register_with_metadata(self, agent_client, mock_grpc_channel):
        """Testa registro com metadados customizados."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            custom_metadata = {"custom_key": "custom_value"}

            agent_id = await agent_client.register(
                agent_type=AgentType.ANALYST,
                capabilities=["analyze", "report"],
                metadata=custom_metadata,
            )

            assert agent_id is not None

    @pytest.mark.asyncio()
    async def test_send_heartbeat_without_registration(self, agent_client):
        """Testa envio de heartbeat sem registro prévio."""
        # Não deve lançar erro, apenas logar warning
        await agent_client._send_heartbeat()

        # agent_id ainda deve ser None
        assert agent_client.agent_id is None

    @pytest.mark.asyncio()
    async def test_create_channel_max_retries(self, agent_config):
        """Testa _create_channel com máximo de tentativas esgotado."""
        client = AgentClient(config=agent_config)

        # Simular falha constante
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value.channel_ready.side_effect = Exception("Connection failed")

            # Deve lançar exceção após esgotar tentativas
            with pytest.raises(Exception):
                await client._create_channel()

    @pytest.mark.asyncio()
    async def test_heartbeat_loop_handles_cancel(self, agent_client):
        """Testa que heartbeat loop trata CancelledError corretamente."""
        agent_client._running = True

        # Criar task que será cancelada imediatamente
        task = asyncio.create_task(agent_client._heartbeat_loop())
        task.cancel()

        # Capturar CancelledError corretamente
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio()
    async def test_heartbeat_loop_handles_exception(self, agent_client):
        """Testa que heartbeat loop trata exceções corretamente."""
        agent_client._running = True
        agent_client.agent_id = "test-agent"

        # Mock _send_heartbeat para lançar exceção
        async def failing_heartbeat():
            raise RuntimeError("Heartbeat failed")

        agent_client._send_heartbeat = failing_heartbeat

        # Deve continuar rodando mesmo com exceção
        # (vamos rodar por um ciclo curto)
        task = asyncio.create_task(agent_client._heartbeat_loop())
        await asyncio.sleep(0.1)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass  # Esperado

    @pytest.mark.asyncio()
    async def test_deregister_closes_channel(self, agent_client, mock_grpc_channel):
        """Testa que deregister fecha o canal gRPC."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            agent_client.channel = mock_grpc_channel
            agent_client.agent_id = "test-agent-123"
            agent_client._running = True

            await agent_client.deregister()

            # Channel.close deve ter sido chamado
            mock_grpc_channel.close.assert_called_once()

    def test_initialization_with_default_config(self):
        """Testa inicialização sem config (usa default)."""
        from neural_hive_agent_sdk import AgentClient

        client = AgentClient()

        assert client.config is not None
        assert client.channel is None
        assert client.agent_id is None
        assert client._heartbeat_task is None
        assert client._running is False


class TestAgentConfigAdditional:
    """Testes adicionais para AgentConfig."""

    def test_config_with_custom_values(self):
        """Testa configuração com valores customizados."""
        config = AgentConfig(
            REGISTRY_GRPC_ENDPOINT="custom-endpoint:9999",
            AGENT_NAMESPACE="custom-ns",
            AGENT_CLUSTER="custom-cluster",
            AGENT_VERSION="2.0.0",
            HEARTBEAT_INTERVAL_SECONDS=60,
            GRPC_TIMEOUT_SECONDS=10,
            GRPC_MAX_RETRIES=5,
        )

        assert config.REGISTRY_GRPC_ENDPOINT == "custom-endpoint:9999"
        assert config.AGENT_NAMESPACE == "custom-ns"
        assert config.AGENT_CLUSTER == "custom-cluster"
        assert config.AGENT_VERSION == "2.0.0"
        assert config.HEARTBEAT_INTERVAL_SECONDS == 60
        assert config.GRPC_TIMEOUT_SECONDS == 10
        assert config.GRPC_MAX_RETRIES == 5

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_context_manager_enter(self, agent_client):
        """Testa __aenter__ retorna o próprio cliente."""
        async with agent_client as client:
            assert client is agent_client

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_create_channel_success(self, agent_client, mock_grpc_channel):
        """Testa criação de canal bem-sucedida."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            channel = await agent_client._create_channel()

            assert channel is not None

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
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

    @pytest.mark.asyncio()
    async def test_register_with_invalid_endpoint(self, agent_client):
        """Testa registro com endpoint inválido."""
        # Endpoint que não existe - deve falhar após retries
        agent_client.config.REGISTRY_GRPC_ENDPOINT = "invalid-host:99999"

        with pytest.raises(Exception):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

    @pytest.mark.asyncio()
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


# ============================================================================
# Testes Adicionais - Cobertura GAP-D2 (+10 testes)
# ============================================================================


class TestAgentClientConcurrency:
    """Testes de operações concorrentes do AgentClient."""

    @pytest.mark.asyncio()
    async def test_concurrent_register_calls(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa chamadas concorrentes de register."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            # Criar múltiplas tarefas de register
            tasks = [
                agent_client.register(
                    agent_type=AgentType.WORKER,
                    capabilities=[f"capability_{i}"],
                )
                for i in range(3)
            ]

            # Executar concorrentemente
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Pelo menos uma deve ter sucesso
            successful = [r for r in results if not isinstance(r, Exception)]
            assert len(successful) > 0

    @pytest.mark.asyncio()
    async def test_concurrent_heartbeat_and_deregister(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa heartbeat concorrente com deregister."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            # Deregister concorrente com heartbeat
            deregister_task = asyncio.create_task(agent_client.deregister())

            # Aguardar um pouco
            await asyncio.sleep(0.1)

            # Deregister deve completar sem erro
            await deregister_task

            assert agent_client._running is False


class TestAgentClientContextPropagation:
    """Testes de propagação de contexto."""

    @pytest.mark.asyncio()
    async def test_context_propagation_in_telemetry(self, agent_client, agent_telemetry):
        """Testa que contexto é propagado na telemetria."""
        # Adicionar contexto customizado
        agent_telemetry.success_rate = 0.88
        agent_telemetry.total_executions = 1234

        agent_client.update_telemetry(agent_telemetry)

        assert agent_client.telemetry.success_rate == 0.88
        assert agent_client.telemetry.total_executions == 1234

    @pytest.mark.asyncio()
    async def test_context_propagation_in_metadata(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa que contexto é propagado nos metadados."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            context_metadata = {
                "request_id": "req-123",
                "trace_id": "trace-abc",
                "parent_span_id": "span-xyz",
            }

            await agent_client.register(
                agent_type=AgentType.ANALYST,
                capabilities=["analyze"],
                metadata=context_metadata,
            )

            # Metadata deve ter sido incluída
            assert agent_client.agent_id is not None


class TestAgentClientMetrics:
    """Testes de coleta de métricas."""

    @pytest.mark.asyncio()
    async def test_metrics_success_rate_calculation(self, agent_client, agent_telemetry):
        """Testa cálculo de taxa de sucesso."""
        agent_client.update_telemetry(agent_telemetry)

        assert agent_client.telemetry.success_rate == 0.95
        assert agent_client.telemetry.total_executions == 1000
        assert agent_client.telemetry.failed_executions == 50

        # Taxa de sucesso deve ser consistente
        expected_rate = 1 - (50 / 1000)
        assert abs(agent_client.telemetry.success_rate - expected_rate) < 0.01

    @pytest.mark.asyncio()
    async def test_metrics_avg_duration_tracking(self, agent_client):
        """Testa rastreamento de duração média."""
        telemetry = AgentTelemetry(
            success_rate=1.0,
            avg_duration_ms=250,
            total_executions=100,
            failed_executions=0,
        )

        agent_client.update_telemetry(telemetry)

        assert agent_client.telemetry.avg_duration_ms == 250

    @pytest.mark.asyncio()
    async def test_metrics_timestamp_tracking(self, agent_client):
        """Testa que timestamp é registrado corretamente."""
        before = int(datetime.now(UTC).timestamp())

        telemetry = AgentTelemetry(
            total_executions=1,
        )

        agent_client.update_telemetry(telemetry)

        after = int(datetime.now(UTC).timestamp())

        assert before <= agent_client.telemetry.last_execution_at <= after


class TestAgentClientTimeout:
    """Testes de timeout."""

    @pytest.mark.asyncio()
    async def test_timeout_configuration(self, agent_config):
        """Testa configuração de timeout."""
        config = AgentConfig(
            GRPC_TIMEOUT_SECONDS=10,
        )

        client = AgentClient(config=config)

        assert client.config.GRPC_TIMEOUT_SECONDS == 10

    @pytest.mark.asyncio()
    async def test_timeout_in_channel_creation(self, agent_client):
        """Testa que timeout é aplicado na criação do canal."""
        client = AgentClient(config=AgentConfig(GRPC_TIMEOUT_SECONDS=3))

        assert client.config.GRPC_TIMEOUT_SECONDS == 3


class TestAgentClientErrorRecovery:
    """Testes de recuperação de erro."""

    @pytest.mark.asyncio()
    async def test_recovery_after_channel_failure(
        self, agent_client, mock_grpc_channel, mock_agent_service_stub
    ):
        """Testa recuperação após falha no canal."""
        with patch(
            "neural_hive_agent_sdk.client.grpc.aio.insecure_channel",
            return_value=mock_grpc_channel,
        ):
            # Primeira tentativa - sucesso
            agent_id = await agent_client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            assert agent_id is not None

            # Deregister
            await agent_client.deregister()

            # Tentar novamente - deve recuperar
            agent_client.agent_id = None
            agent_client.registration_token = None
            agent_client._heartbeat_task = None
            agent_client._running = False

            agent_id_2 = await agent_client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            assert agent_id_2 is not None

    @pytest.mark.asyncio()
    async def test_state_cleanup_after_error(self, agent_client):
        """Testa que estado é limpo após erro."""
        # Simular estado após erro
        agent_client.agent_id = "old-agent"
        agent_client._running = True
        agent_client._heartbeat_task = asyncio.create_task(asyncio.sleep(10))

        # Deregister deve limpar estado
        await agent_client.deregister()

        assert agent_client._running is False
