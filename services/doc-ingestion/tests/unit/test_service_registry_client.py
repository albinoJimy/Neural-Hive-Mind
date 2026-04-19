"""Testes unitários para o cliente do Service Registry."""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest


@pytest.mark.asyncio
class TestDocIngestionServiceRegistryClient:
    """Testes para DocIngestionServiceRegistryClient."""

    async def test_init_default_values(self):
        """Testa inicialização com valores padrão."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()

        assert client.service_name == "doc-ingestion"
        assert client.agent_type == 10  # DOC_INGESTION
        assert client._registered is False
        assert client._running is False
        assert client.agent_id is None

    async def test_init_custom_values(self):
        """Testa inicialização com valores customizados."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient(
            service_name="custom-doc-ingestion", agent_type=5
        )

        assert client.service_name == "custom-doc-ingestion"
        assert client.agent_type == 5

    async def test_initialize_success(self):
        """Testa inicialização bem-sucedida do canal gRPC."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()

        # Mock channel e stub
        mock_channel = MagicMock()
        mock_channel.channel_ready = AsyncMock()
        mock_stub = MagicMock()

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "neural_hive_integration.proto_stubs.service_registry_pb2_grpc.ServiceRegistryStub",
                return_value=mock_stub,
            ):
                result = await client.initialize()

        assert result is True
        assert client.channel is not None
        assert client.stub is not None

    async def test_initialize_without_proto_stubs(self):
        """Testa inicialização quando proto stubs não estão disponíveis."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()

        # Simular import falhando
        with patch(
            "src.clients.service_registry_client.service_registry_pb2", None
        ):
            result = await client.initialize()

        assert result is False

    async def test_register_success(self):
        """Testa registro bem-sucedido no Service Registry."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client.stub = AsyncMock()
        client.channel = MagicMock()

        # Mock resposta
        mock_response = MagicMock()
        mock_response.agent_id = "agent-123"

        client.stub.Register = AsyncMock(return_value=mock_response)

        result = await client.register()

        assert result == "agent-123"
        assert client._registered is True
        assert client.agent_id == "agent-123"

    async def test_register_with_custom_capabilities(self):
        """Testa registro com capabilities customizadas."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client.stub = AsyncMock()
        client.channel = MagicMock()

        mock_response = MagicMock()
        mock_response.agent_id = "agent-456"

        client.stub.Register = AsyncMock(return_value=mock_response)

        custom_capabilities = ["pdf_parsing", "custom_capability"]
        result = await client.register(capabilities=custom_capabilities)

        assert result == "agent-456"

        # Verificar que Register foi chamado com as capabilities corretas
        call_args = client.stub.Register.call_args
        assert "custom_capability" in call_args[0][0].capabilities

    async def test_register_without_stub(self):
        """Testa registro sem stub inicializado."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client.stub = None

        result = await client.register()

        assert result is None

    async def test_register_grpc_error(self):
        """Testa registro com erro gRPC."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client.stub = AsyncMock()
        client.channel = MagicMock()

        # Simular erro gRPC
        error = grpc.RpcError("Service unavailable")
        error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        client.stub.Register = AsyncMock(side_effect=error)

        result = await client.register()

        assert result is None
        assert client._registered is False

    async def test_deregister_success(self):
        """Testa deregistro bem-sucedido."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._registered = True
        client.agent_id = "agent-123"
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.success = True

        client.stub.Deregister = AsyncMock(return_value=mock_response)

        result = await client.deregister()

        assert result is True
        assert client._registered is False

    async def test_deregister_not_registered(self):
        """Testa deregistro quando não está registrado."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._registered = False
        client.stub = None

        result = await client.deregister()

        assert result is True  # Retorna True se não estava registrado

    async def test_send_heartbeat_success(self):
        """Testa envio de heartbeat bem-sucedido."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._registered = True
        client.agent_id = "agent-123"
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.status = 1  # HEALTHY

        client.stub.Heartbeat = AsyncMock(return_value=mock_response)

        result = await client.send_heartbeat()

        assert result is True

    async def test_send_heartbeat_with_metrics(self):
        """Testa envio de heartbeat com métricas customizadas."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._registered = True
        client.agent_id = "agent-123"
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.status = 1

        client.stub.Heartbeat = AsyncMock(return_value=mock_response)

        custom_metrics = {
            "success_rate": 0.95,
            "total_executions": 1000,
            "failed_executions": 50,
        }

        result = await client.send_heartbeat(metrics=custom_metrics)

        assert result is True
        assert client._metrics["success_rate"] == 0.95
        assert client._metrics["total_executions"] == 1000

    async def test_start_heartbeat(self):
        """Testa início do loop de heartbeat."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._registered = True
        client.agent_id = "agent-123"
        client.stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.status = 1

        client.stub.Heartbeat = AsyncMock(return_value=mock_response)

        await client.start_heartbeat(interval_seconds=1)

        assert client._running is True
        assert client._heartbeat_task is not None

        # Parar o heartbeat
        await client.stop_heartbeat()
        assert client._running is False

    async def test_stop_heartbeat(self):
        """Testa parada do loop de heartbeat."""
        import asyncio

        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._running = True

        # Criar uma task real que pode ser cancelada
        async def dummy_loop():
            while True:
                await asyncio.sleep(1)

        client._heartbeat_task = asyncio.create_task(dummy_loop())

        # Verificar que a task está rodando
        assert not client._heartbeat_task.done()

        await client.stop_heartbeat()

        assert client._running is False
        assert client._heartbeat_task is None

    async def test_discover_agents_success(self):
        """Testa descoberta de agentes bem-sucedida."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client.stub = AsyncMock()

        # Mock agentes descobertos
        mock_agent = MagicMock()
        mock_agent.agent_id = "other-agent-123"
        mock_agent.agent_type = 5
        mock_agent.capabilities = ["pdf_parsing", "entity_extraction"]
        mock_agent.namespace = "default"
        mock_agent.cluster = "neural-hive"
        mock_agent.version = "1.0.0"
        mock_agent.metadata = {}
        mock_agent.status = 1
        mock_agent.registered_at = 1234567890
        mock_agent.last_seen = 1234567890
        mock_agent.telemetry = MagicMock()
        mock_agent.telemetry.success_rate = 1.0
        mock_agent.telemetry.avg_duration_ms = 100
        mock_agent.telemetry.total_executions = 100
        mock_agent.telemetry.failed_executions = 0
        mock_agent.telemetry.last_execution_at = 1234567890

        mock_response = MagicMock()
        mock_response.agents = [mock_agent]

        client.stub.DiscoverAgents = AsyncMock(return_value=mock_response)

        result = await client.discover_agents(capabilities=["pdf_parsing"])

        assert len(result) == 1
        assert result[0]["agent_id"] == "other-agent-123"
        assert "pdf_parsing" in result[0]["capabilities"]

    async def test_discover_agents_without_stub(self):
        """Testa descoberta de agentes sem stub inicializado."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client.stub = None

        result = await client.discover_agents()

        assert result == []

    async def test_close(self):
        """Testa fechamento do cliente."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()
        client._registered = True
        client.agent_id = "agent-123"
        client._running = True
        client.stub = AsyncMock()

        mock_channel = MagicMock()
        mock_channel.close = AsyncMock()
        client.channel = mock_channel

        mock_response = MagicMock()
        mock_response.success = True
        client.stub.Deregister = AsyncMock(return_value=mock_response)

        await client.close()

        assert client._running is False
        assert client._registered is False
        mock_channel.close.assert_called_once()

    async def test_convert_agent_info(self):
        """Testa conversão de AgentInfo protobuf para dict."""
        from src.clients.service_registry_client import DocIngestionServiceRegistryClient

        client = DocIngestionServiceRegistryClient()

        # Criar mock AgentInfo
        mock_agent = MagicMock()
        mock_agent.agent_id = "test-agent"
        mock_agent.agent_type = 10
        mock_agent.capabilities = ["pdf_parsing", "word_parsing"]
        mock_agent.namespace = "default"
        mock_agent.cluster = "neural-hive"
        mock_agent.version = "1.0.0"
        mock_agent.metadata = {"key": "value"}
        mock_agent.status = 1  # HEALTHY
        mock_agent.registered_at = 1234567890
        mock_agent.last_seen = 1234567890

        # Telemetria
        mock_telemetry = MagicMock()
        mock_telemetry.success_rate = 0.95
        mock_telemetry.avg_duration_ms = 150
        mock_telemetry.total_executions = 500
        mock_telemetry.failed_executions = 25
        mock_telemetry.last_execution_at = 1234567890
        mock_agent.telemetry = mock_telemetry

        result = client._convert_agent_info(mock_agent)

        assert result["agent_id"] == "test-agent"
        assert result["agent_type"] == 10
        assert "pdf_parsing" in result["capabilities"]
        assert result["namespace"] == "default"
        assert result["status"] == "HEALTHY"
        assert result["telemetry"]["success_rate"] == 0.95
        assert result["metadata"]["key"] == "value"


@pytest.mark.asyncio
class TestRegisterDocIngestionService:
    """Testes para a função register_doc_ingestion_service."""

    async def test_register_success(self):
        """Testa registro bem-sucedido do serviço."""
        from src.clients.service_registry_client import register_doc_ingestion_service

        # Mock do cliente
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock(return_value=True)
        mock_client.register = AsyncMock(return_value="agent-123")
        mock_client.close = AsyncMock()

        with patch(
            "src.clients.service_registry_client.DocIngestionServiceRegistryClient",
            return_value=mock_client,
        ):
            result = await register_doc_ingestion_service()

        assert result is not None
        assert result == mock_client
        mock_client.initialize.assert_called_once()
        mock_client.register.assert_called_once()

    async def test_register_init_fails(self):
        """Testa registro quando inicialização falha."""
        from src.clients.service_registry_client import register_doc_ingestion_service

        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock(return_value=False)
        mock_client.close = AsyncMock()

        with patch(
            "src.clients.service_registry_client.DocIngestionServiceRegistryClient",
            return_value=mock_client,
        ):
            result = await register_doc_ingestion_service()

        assert result is None
        mock_client.register.assert_not_called()

    async def test_register_registration_fails(self):
        """Testa registro quando registro falha."""
        from src.clients.service_registry_client import register_doc_ingestion_service

        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock(return_value=True)
        mock_client.register = AsyncMock(return_value=None)
        mock_client.close = AsyncMock()

        with patch(
            "src.clients.service_registry_client.DocIngestionServiceRegistryClient",
            return_value=mock_client,
        ):
            result = await register_doc_ingestion_service()

        assert result is None
        mock_client.close.assert_called_once()
