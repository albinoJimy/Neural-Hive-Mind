"""Testes para EngineeringServiceRegistryClient."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import grpc
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
    register_engineering_service,
)
from src.proto import service_registry_pb2, service_registry_pb2_grpc


@pytest.fixture
def mock_grpc_channel():
    """Fixture para canal gRPC mock."""
    channel = AsyncMock(spec=grpc.aio.Channel)
    channel.channel_ready = AsyncMock(return_value=None)
    return channel


@pytest.fixture
def mock_stub():
    """Fixture para stub ServiceRegistry mock."""
    stub = MagicMock()
    stub.Register = AsyncMock()
    stub.Deregister = AsyncMock()
    stub.Heartbeat = AsyncMock()
    return stub


@pytest.fixture
def mock_settings(monkeypatch):
    """Fixture para configurações mock."""
    monkeypatch.setenv("SERVICE_REGISTRY_HOST", "localhost")
    monkeypatch.setenv("SERVICE_REGISTRY_PORT", "8007")
    monkeypatch.setenv("SERVICE_REGISTRY_NAMESPACE", "test")
    monkeypatch.setenv("SERVICE_REGISTRY_CLUSTER", "test-cluster")
    monkeypatch.setenv("SERVICE_VERSION", "2.0.0")
    monkeypatch.setenv("ENVIRONMENT", "development")


class TestEngineeringServiceRegistryClient:
    """Testes para EngineeringServiceRegistryClient."""

    def test_initialization_requirements_engineering(self):
        """Testa inicialização para requirements-engineering."""
        client = EngineeringServiceRegistryClient(
            "requirements-engineering",
            service_registry_pb2.REQUIREMENTS_ENGINEERING,
        )
        assert client.service_name == "requirements-engineering"
        assert client.agent_type == service_registry_pb2.REQUIREMENTS_ENGINEERING
        assert client.namespace == "default"
        assert client.cluster == "neural-hive"

    def test_initialization_documentation_generation(self):
        """Testa inicialização para documentation-generation."""
        client = EngineeringServiceRegistryClient(
            "documentation-generation",
            service_registry_pb2.DOCUMENTATION_GENERATION,
        )
        assert client.service_name == "documentation-generation"
        assert client.agent_type == service_registry_pb2.DOCUMENTATION_GENERATION

    def test_initialization_knowledge_graph_rag(self):
        """Testa inicialização para knowledge-graph-rag."""
        client = EngineeringServiceRegistryClient(
            "knowledge-graph-rag",
            service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
        )
        assert client.service_name == "knowledge-graph-rag"
        assert client.agent_type == service_registry_pb2.KNOWLEDGE_GRAPH_RAG

    def test_initialization_approval_gateway(self):
        """Testa inicialização para approval-gateway."""
        client = EngineeringServiceRegistryClient(
            "approval-gateway",
            service_registry_pb2.APPROVAL_GATEWAY,
        )
        assert client.service_name == "approval-gateway"
        assert client.agent_type == service_registry_pb2.APPROVAL_GATEWAY

    def test_initialization_architect_agent(self):
        """Testa inicialização para architect-agent."""
        client = EngineeringServiceRegistryClient(
            "architect-agent",
            service_registry_pb2.ARCHITECT_AGENT,
        )
        assert client.service_name == "architect-agent"
        assert client.agent_type == service_registry_pb2.ARCHITECT_AGENT

    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_settings):
        """Testa inicialização bem-sucedida."""
        client = EngineeringServiceRegistryClient(
            "test-service",
            service_registry_pb2.REQUIREMENTS_ENGINEERING,
        )

        with patch("grpc.aio.insecure_channel") as mock_channel_func:
            mock_channel = AsyncMock(spec=grpc.aio.Channel)
            mock_channel.channel_ready = AsyncMock(return_value=None)
            mock_channel_func.return_value = mock_channel

            result = await client.initialize()

            assert result is True
            assert client.channel is not None
            assert client.stub is not None

    @pytest.mark.asyncio
    async def test_register_success(self, mock_settings):
        """Testa registro bem-sucedido."""
        client = EngineeringServiceRegistryClient(
            "requirements-engineering",
            service_registry_pb2.REQUIREMENTS_ENGINEERING,
        )

        # Mock channel e stub
        client.channel = AsyncMock(spec=grpc.aio.Channel)
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.agent_id = "test-agent-123"
        mock_stub.Register = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        capabilities = ["requirements_generation", "user_stories"]
        metadata = {"extra": "info"}

        agent_id = await client.register(capabilities, metadata)

        assert agent_id == "test-agent-123"
        assert client.agent_id == "test-agent-123"
        assert client._registered is True
        mock_stub.Register.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_without_metadata(self, mock_settings):
        """Testa registro sem metadados adicionais."""
        client = EngineeringServiceRegistryClient(
            "documentation-generation",
            service_registry_pb2.DOCUMENTATION_GENERATION,
        )

        # Mock channel e stub
        client.channel = AsyncMock(spec=grpc.aio.Channel)
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.agent_id = "test-agent-456"
        mock_stub.Register = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        capabilities = ["readme_generation", "api_docs"]

        agent_id = await client.register(capabilities)

        assert agent_id == "test-agent-456"
        assert client._registered is True

        # Verificar que metadados padrão foram incluídos
        call_args = mock_stub.Register.call_args
        request = call_args[0][0]
        assert "service_name" in request.metadata
        assert request.metadata["service_name"] == "documentation-generation"
        assert request.metadata["service_type"] == "engineering"

    @pytest.mark.asyncio
    async def test_deregister_success(self, mock_settings):
        """Testa deregistro bem-sucedido."""
        client = EngineeringServiceRegistryClient(
            "knowledge-graph-rag",
            service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
        )
        client._registered = True
        client.agent_id = "test-agent-789"

        # Mock stub
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_stub.Deregister = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        result = await client.deregister()

        assert result is True
        assert client._registered is False

    @pytest.mark.asyncio
    async def test_deregister_not_registered(self, mock_settings):
        """Testa deregistro quando não está registrado."""
        client = EngineeringServiceRegistryClient(
            "approval-gateway",
            service_registry_pb2.APPROVAL_GATEWAY,
        )
        client._registered = False

        result = await client.deregister()

        assert result is True  # Retorna True se não estava registrado

    @pytest.mark.asyncio
    async def test_send_heartbeat_success(self, mock_settings):
        """Testa envio de heartbeat bem-sucedido."""
        client = EngineeringServiceRegistryClient(
            "architect-agent",
            service_registry_pb2.ARCHITECT_AGENT,
        )
        client._registered = True
        client.agent_id = "test-agent-heartbeat"

        # Mock stub
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.status = service_registry_pb2.HEALTHY
        mock_stub.Heartbeat = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        metrics = {
            "success_rate": 0.95,
            "total_executions": 100,
            "failed_executions": 5,
        }

        result = await client.send_heartbeat(metrics)

        assert result is True
        mock_stub.Heartbeat.assert_called_once()

        # Verificar telemetry
        call_args = mock_stub.Heartbeat.call_args
        request = call_args[0][0]
        assert request.telemetry.success_rate == 0.95
        assert request.telemetry.total_executions == 100
        assert request.telemetry.failed_executions == 5

    @pytest.mark.asyncio
    async def test_send_heartbeat_without_metrics(self, mock_settings):
        """Testa envio de heartbeat sem métricas."""
        client = EngineeringServiceRegistryClient(
            "requirements-engineering",
            service_registry_pb2.REQUIREMENTS_ENGINEERING,
        )
        client._registered = True
        client.agent_id = "test-agent-heartbeat"

        # Mock stub
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.status = service_registry_pb2.HEALTHY
        mock_stub.Heartbeat = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        result = await client.send_heartbeat()

        assert result is True

        # Verificar telemetry padrão
        call_args = mock_stub.Heartbeat.call_args
        request = call_args[0][0]
        assert request.telemetry.success_rate == 1.0
        assert request.telemetry.avg_duration_ms == 0

    @pytest.mark.asyncio
    async def test_heartbeat_not_registered(self, mock_settings):
        """Testa heartbeat quando não está registrado."""
        client = EngineeringServiceRegistryClient(
            "documentation-generation",
            service_registry_pb2.DOCUMENTATION_GENERATION,
        )
        client._registered = False

        result = await client.send_heartbeat()

        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, mock_settings):
        """Testa fechamento do cliente."""
        client = EngineeringServiceRegistryClient(
            "knowledge-graph-rag",
            service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
        )
        client._registered = True
        client.agent_id = "test-agent-close"

        # Mock channel e stub
        mock_channel = AsyncMock(spec=grpc.aio.Channel)
        mock_channel.close = AsyncMock(return_value=None)
        client.channel = mock_channel
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_stub.Deregister = AsyncMock(return_value=mock_response)
        client.stub = mock_stub

        await client.close()

        assert client._registered is False
        mock_channel.close.assert_called_once()


class TestRegisterEngineeringService:
    """Testes para função register_engineering_service."""

    @pytest.mark.asyncio
    async def test_register_success(self, monkeypatch):
        """Testa registro bem-sucedido."""
        # Mock settings
        monkeypatch.setenv("SERVICE_REGISTRY_HOST", "localhost")
        monkeypatch.setenv("SERVICE_REGISTRY_PORT", "8007")
        monkeypatch.setenv("ENVIRONMENT", "development")

        with patch("grpc.aio.insecure_channel") as mock_channel_func:
            mock_channel = AsyncMock(spec=grpc.aio.Channel)
            mock_channel.channel_ready = AsyncMock(return_value=None)
            mock_channel_func.return_value = mock_channel

            # Criar mock stub
            mock_stub = MagicMock()
            mock_response = MagicMock()
            mock_response.agent_id = "registered-agent-123"
            mock_stub.Register = AsyncMock(return_value=mock_response)

            # Patch ServiceRegistryStub
            with patch(
                "src.clients.engineering_service_registry_client.service_registry_pb2_grpc.ServiceRegistryStub",
                return_value=mock_stub,
            ):
                client = await register_engineering_service(
                    service_name="test-service",
                    agent_type=service_registry_pb2.REQUIREMENTS_ENGINEERING,
                    capabilities=["test_capability"],
                    metadata={"test": "metadata"},
                )

                assert client is not None
                assert client.agent_id == "registered-agent-123"

    @pytest.mark.asyncio
    async def test_register_init_fails(self, monkeypatch):
        """Testa falha na inicialização do cliente."""
        # Mock settings
        monkeypatch.setenv("SERVICE_REGISTRY_HOST", "localhost")
        monkeypatch.setenv("SERVICE_REGISTRY_PORT", "8007")
        monkeypatch.setenv("ENVIRONMENT", "development")

        with patch("grpc.aio.insecure_channel") as mock_channel_func:
            # Falhar na inicialização
            mock_channel_func.side_effect = Exception("Connection failed")

            client = await register_engineering_service(
                service_name="test-service",
                agent_type=service_registry_pb2.DOCUMENTATION_GENERATION,
                capabilities=["test_capability"],
            )

            assert client is None

    @pytest.mark.asyncio
    async def test_register_registration_fails(self, monkeypatch):
        """Testa falha no registro."""
        # Mock settings
        monkeypatch.setenv("SERVICE_REGISTRY_HOST", "localhost")
        monkeypatch.setenv("SERVICE_REGISTRY_PORT", "8007")
        monkeypatch.setenv("ENVIRONMENT", "development")

        with patch("grpc.aio.insecure_channel") as mock_channel_func:
            mock_channel = AsyncMock(spec=grpc.aio.Channel)
            mock_channel.channel_ready = AsyncMock(return_value=None)
            mock_channel_func.return_value = mock_channel

            # Criar mock stub que falha
            mock_stub = MagicMock()
            mock_stub.Register = AsyncMock(side_effect=Exception("Registration failed"))

            # Patch ServiceRegistryStub
            with patch(
                "src.clients.engineering_service_registry_client.service_registry_pb2_grpc.ServiceRegistryStub",
                return_value=mock_stub,
            ):
                client = await register_engineering_service(
                    service_name="test-service",
                    agent_type=service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
                    capabilities=["test_capability"],
                )

                assert client is None
