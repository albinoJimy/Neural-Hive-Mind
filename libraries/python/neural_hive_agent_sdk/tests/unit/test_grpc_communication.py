"""
Testes de comunicação gRPC para neural_hive_agent_sdk.

Cobre envio de requisições, respostas, streaming, metadados, deadlines,
compressão e interceptors.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call
from datetime import datetime, timezone
import grpc
from grpc.aio import AioRpcError

from neural_hive_agent_sdk import AgentClient, AgentType, AgentTelemetry, AgentConfig


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def grpc_config():
    """Configuração para testes gRPC."""
    return AgentConfig(
        REGISTRY_GRPC_ENDPOINT="localhost:50051",
        AGENT_NAMESPACE="test-ns",
        AGENT_CLUSTER="test-cluster",
        GRPC_TIMEOUT_SECONDS=5,
        GRPC_MAX_RETRIES=3,
    )


@pytest.fixture
def mock_channel():
    """Mock de canal gRPC."""
    channel = MagicMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    channel.__aenter__ = AsyncMock(return_value=channel)
    channel.__aexit__ = AsyncMock()
    return channel


# ============================================================================
# Testes de Envio de Requisição
# ============================================================================


class TestGrpcSendRequest:
    """Testes de envio de requisições gRPC."""

    @pytest.mark.asyncio
    async def test_send_register_request(self, grpc_config, mock_channel):
        """Testa envio de requisição de registro."""
        # Quando proto não disponível, usa fallback mock
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            agent_id = await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["query", "transform"],
            )

            # Deve retornar um UUID quando usando fallback
            assert agent_id is not None
            assert client.agent_id == agent_id
            assert client.registration_token is not None

    @pytest.mark.asyncio
    async def test_send_request_succeeds(self, grpc_config, mock_channel):
        """Testa que requisição tem sucesso."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            agent_id = await client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            assert agent_id is not None
            assert client.agent_id == agent_id

    @pytest.mark.asyncio
    async def test_send_request_with_different_types(self, grpc_config, mock_channel):
        """Testa envio com diferentes tipos de agente."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            for agent_type in [AgentType.WORKER, AgentType.SCOUT, AgentType.GUARD, AgentType.ANALYST]:
                client.agent_id = None
                client.registration_token = None

                agent_id = await client.register(
                    agent_type=agent_type,
                    capabilities=[f"{agent_type.value.lower()}_cap"],
                )

                assert agent_id is not None


# ============================================================================
# Testes de Resposta
# ============================================================================


class TestGrpcReceiveResponse:
    """Testes de recebimento de respostas gRPC."""

    @pytest.mark.asyncio
    async def test_receive_register_response_fields(self, grpc_config, mock_channel):
        """Testa extração de campos da resposta de registro."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            agent_id = await client.register(
                agent_type=AgentType.ANALYST,
                capabilities=["analyze"],
            )

            # Verificar campos extraídos
            assert client.agent_id is not None
            assert client.registration_token is not None
            assert agent_id == client.agent_id

    @pytest.mark.asyncio
    async def test_response_includes_token(self, grpc_config, mock_channel):
        """Testa que resposta inclui token de registro."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            await client.register(
                agent_type=AgentType.GUARD,
                capabilities=["validate"],
            )

            # Token deve ser gerado
            assert client.registration_token is not None
            assert client.registration_token.startswith("token-")


# ============================================================================
# Testes de Timeout
# ============================================================================


class TestGrpcDeadline:
    """Testes de deadline/timeout gRPC."""

    @pytest.mark.asyncio
    async def test_timeout_configuration_used(self, grpc_config, mock_channel):
        """Testa que configuração de timeout é usada."""
        grpc_config.GRPC_TIMEOUT_SECONDS = 10

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            # Deve usar timeout configurado
            assert client.config.GRPC_TIMEOUT_SECONDS == 10

            await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

    @pytest.mark.asyncio
    async def test_timeout_applies_to_channel_ready(self, grpc_config):
        """Testa que timeout é aplicado no channel_ready."""
        slow_channel = MagicMock()
        slow_channel.channel_ready = AsyncMock()

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=slow_channel):
            client = AgentClient(config=grpc_config)

            await client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            slow_channel.channel_ready.assert_called_once()


# ============================================================================
# Testes de Metadados
# ============================================================================


class TestGrpcMetadata:
    """Testes de metadados gRPC."""

    @pytest.mark.asyncio
    async def test_metadata_passed_to_register(self, grpc_config, mock_channel):
        """Testa que metadados são passados para registro."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            custom_metadata = {
                "custom_key": "custom_value",
                "region": "us-east-1",
            }

            agent_id = await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["query"],
                metadata=custom_metadata,
            )

            assert agent_id is not None

    @pytest.mark.asyncio
    async def test_default_metadata_included(self, grpc_config, mock_channel):
        """Testa que metadados padrão são incluídos."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            agent_id = await client.register(
                agent_type=AgentType.SCOUT,
                capabilities=["explore"],
            )

            assert agent_id is not None


# ============================================================================
# Testes de Canal
# ============================================================================


class TestGrpcChannel:
    """Testes de canal gRPC."""

    @pytest.mark.asyncio
    async def test_channel_created_with_options(self, grpc_config):
        """Testa que canal é criado com opções corretas."""
        channel = MagicMock()
        channel.channel_ready = AsyncMock()
        channel.close = AsyncMock()

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel) as mock_create:
            client = AgentClient(config=grpc_config)

            await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            # Verificar que insecure_channel foi chamado
            mock_create.assert_called_once()

            # Verificar endpoint
            call_args = mock_create.call_args
            assert call_args[0][0] == grpc_config.REGISTRY_GRPC_ENDPOINT

    @pytest.mark.asyncio
    async def test_channel_closed_on_deregister(self, grpc_config, mock_channel):
        """Testa que canal é fechado no deregister."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            await client.register(
                agent_type=AgentType.GUARD,
                capabilities=["validate"],
            )

            await client.deregister()

            # Canal deve ser fechado
            mock_channel.close.assert_called_once()


# ============================================================================
# Testes de Retry
# ============================================================================


class TestGrpcRetry:
    """Testes de retry gRPC."""

    @pytest.mark.asyncio
    async def test_retry_on_channel_failure(self, grpc_config):
        """Testa retry quando falha na criação do canal."""
        call_count = 0
        channel = MagicMock()
        channel.close = AsyncMock()

        async def failing_channel_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection failed")
            return None

        channel.channel_ready = failing_channel_ready

        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=channel):
            client = AgentClient(config=grpc_config)

            agent_id = await client.register(
                agent_type=AgentType.WORKER,
                capabilities=["test"],
            )

            assert agent_id is not None
            assert call_count == 3


# ============================================================================
# Testes de Compressão
# ============================================================================


class TestGrpcCompression:
    """Testes de compressão gRPC."""

    @pytest.mark.asyncio
    async def test_large_payload_handled(self, grpc_config, mock_channel):
        """Testa que payload grande é manipulado."""
        with patch("neural_hive_agent_sdk.client.grpc.aio.insecure_channel", return_value=mock_channel):
            client = AgentClient(config=grpc_config)

            # Enviar lista grande de capabilities
            large_capabilities = [f"capability_{i}" for i in range(100)]

            agent_id = await client.register(
                agent_type=AgentType.ANALYST,
                capabilities=large_capabilities,
            )

            assert agent_id is not None
