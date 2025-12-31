"""
Testes de integração para RPC Register

Este módulo testa o fluxo completo de registro de agentes via gRPC,
incluindo a conversão de protobuf enum (int) para AgentType Python.
"""

import pytest
import grpc
import sys
import os
from unittest.mock import Mock, AsyncMock, MagicMock

# Adicionar src ao path para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from grpc_server.registry_servicer import ServiceRegistryServicer
from models.agent import AgentType


class TestRegisterRPC:
    """Testes de integração para RPC Register"""

    @pytest.fixture
    def mock_registry_service(self):
        """Mock do RegistryService"""
        service = AsyncMock()
        service.register_agent = AsyncMock(return_value=("agent-123", "token-456"))
        return service

    @pytest.fixture
    def mock_matching_engine(self):
        """Mock do MatchingEngine"""
        return Mock()

    @pytest.fixture
    def servicer(self, mock_registry_service, mock_matching_engine):
        """Cria instância do ServiceRegistryServicer com mocks"""
        return ServiceRegistryServicer(mock_registry_service, mock_matching_engine)

    @pytest.fixture
    def mock_context(self):
        """Mock do gRPC context"""
        context = Mock()
        context.abort = Mock()
        context.invocation_metadata = Mock(return_value=[])
        return context

    def create_register_request(
        self,
        agent_type: int,
        capabilities: list = None,
        metadata: dict = None,
        namespace: str = "default",
        cluster: str = "local",
        version: str = "1.0.0"
    ):
        """Helper para criar requests de registro"""
        request = Mock()
        request.agent_type = agent_type
        request.capabilities = capabilities or ["python", "terraform"]
        request.metadata = metadata or {"version": "1.0.0"}
        request.namespace = namespace
        request.cluster = cluster
        request.version = version
        request.agent_id = ""
        return request

    @pytest.mark.asyncio
    async def test_register_with_int_agent_type_worker(self, servicer, mock_context, mock_registry_service):
        """Testa registro com agent_type=1 (WORKER)"""
        request = self.create_register_request(
            agent_type=1,  # WORKER
            capabilities=["python", "terraform"],
            metadata={"version": "1.0.0"}
        )

        response = await servicer.Register(request, mock_context)

        assert response.agent_id == "agent-123"
        assert response.registration_token == "token-456"
        assert not mock_context.abort.called

        # Verificar que register_agent foi chamado com AgentType.WORKER
        mock_registry_service.register_agent.assert_called_once()
        call_kwargs = mock_registry_service.register_agent.call_args[1]
        assert call_kwargs["agent_type"] == AgentType.WORKER

    @pytest.mark.asyncio
    async def test_register_with_int_agent_type_scout(self, servicer, mock_context, mock_registry_service):
        """Testa registro com agent_type=2 (SCOUT)"""
        request = self.create_register_request(
            agent_type=2,  # SCOUT
            capabilities=["discovery"]
        )

        response = await servicer.Register(request, mock_context)

        assert response.agent_id == "agent-123"
        assert not mock_context.abort.called

        # Verificar que register_agent foi chamado com AgentType.SCOUT
        mock_registry_service.register_agent.assert_called_once()
        call_kwargs = mock_registry_service.register_agent.call_args[1]
        assert call_kwargs["agent_type"] == AgentType.SCOUT

    @pytest.mark.asyncio
    async def test_register_with_int_agent_type_guard(self, servicer, mock_context, mock_registry_service):
        """Testa registro com agent_type=3 (GUARD)"""
        request = self.create_register_request(
            agent_type=3,  # GUARD
            capabilities=["security", "audit"]
        )

        response = await servicer.Register(request, mock_context)

        assert response.agent_id == "agent-123"
        assert not mock_context.abort.called

        # Verificar que register_agent foi chamado com AgentType.GUARD
        mock_registry_service.register_agent.assert_called_once()
        call_kwargs = mock_registry_service.register_agent.call_args[1]
        assert call_kwargs["agent_type"] == AgentType.GUARD

    @pytest.mark.asyncio
    async def test_register_with_invalid_agent_type_0(self, servicer, mock_context, mock_registry_service):
        """Testa que agent_type=0 (UNSPECIFIED) retorna erro e não chama register_agent"""
        request = self.create_register_request(
            agent_type=0,  # UNSPECIFIED - inválido
            capabilities=["test"]
        )

        await servicer.Register(request, mock_context)

        # Verificar que context.abort foi chamado com INVALID_ARGUMENT
        mock_context.abort.assert_called_once()
        args = mock_context.abort.call_args[0]
        assert args[0] == grpc.StatusCode.INVALID_ARGUMENT
        assert "Invalid AgentType" in args[1]

        # Verificar que register_agent NÃO foi chamado após abort
        mock_registry_service.register_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_with_invalid_agent_type_99(self, servicer, mock_context, mock_registry_service):
        """Testa que agent_type=99 retorna erro apropriado e não chama register_agent"""
        request = self.create_register_request(
            agent_type=99,  # Inválido
            capabilities=["test"]
        )

        await servicer.Register(request, mock_context)

        # Verificar que context.abort foi chamado com INVALID_ARGUMENT
        mock_context.abort.assert_called_once()
        args = mock_context.abort.call_args[0]
        assert args[0] == grpc.StatusCode.INVALID_ARGUMENT
        assert "Invalid AgentType" in args[1]

        # Verificar que register_agent NÃO foi chamado após abort
        mock_registry_service.register_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_with_empty_capabilities(self, servicer, mock_context, mock_registry_service):
        """Testa que capabilities vazias retornam erro e não chama register_agent"""
        request = self.create_register_request(
            agent_type=1,
            capabilities=[]  # Vazio
        )

        await servicer.Register(request, mock_context)

        mock_context.abort.assert_called_once()
        args = mock_context.abort.call_args[0]
        assert args[0] == grpc.StatusCode.INVALID_ARGUMENT
        assert "Capabilities não podem estar vazias" in args[1]

        # Verificar que register_agent NÃO foi chamado após abort
        mock_registry_service.register_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_preserves_metadata(self, servicer, mock_context, mock_registry_service):
        """Testa que metadata é preservado no registro"""
        custom_metadata = {"app": "test-app", "env": "development"}
        request = self.create_register_request(
            agent_type=1,
            capabilities=["python"],
            metadata=custom_metadata
        )

        await servicer.Register(request, mock_context)

        call_kwargs = mock_registry_service.register_agent.call_args[1]
        assert call_kwargs["metadata"] == custom_metadata

    @pytest.mark.asyncio
    async def test_register_uses_default_namespace(self, servicer, mock_context, mock_registry_service):
        """Testa que namespace padrão é 'default'"""
        request = self.create_register_request(
            agent_type=1,
            capabilities=["python"],
            namespace=""
        )

        await servicer.Register(request, mock_context)

        call_kwargs = mock_registry_service.register_agent.call_args[1]
        assert call_kwargs["namespace"] == "default"

    @pytest.mark.asyncio
    async def test_register_uses_custom_namespace(self, servicer, mock_context, mock_registry_service):
        """Testa que namespace customizado é respeitado"""
        request = self.create_register_request(
            agent_type=1,
            capabilities=["python"],
            namespace="production"
        )

        await servicer.Register(request, mock_context)

        call_kwargs = mock_registry_service.register_agent.call_args[1]
        assert call_kwargs["namespace"] == "production"


class TestListAgentsRPC:
    """Testes de integração para RPC ListAgents"""

    @pytest.fixture
    def mock_registry_service(self):
        """Mock do RegistryService"""
        service = AsyncMock()
        service.list_agents = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def mock_matching_engine(self):
        """Mock do MatchingEngine"""
        return Mock()

    @pytest.fixture
    def servicer(self, mock_registry_service, mock_matching_engine):
        """Cria instância do ServiceRegistryServicer com mocks"""
        return ServiceRegistryServicer(mock_registry_service, mock_matching_engine)

    @pytest.fixture
    def mock_context(self):
        """Mock do gRPC context"""
        context = Mock()
        context.abort = Mock()
        context.invocation_metadata = Mock(return_value=[])
        return context

    @pytest.mark.asyncio
    async def test_list_agents_with_int_filter(self, servicer, mock_context, mock_registry_service):
        """Testa ListAgents com agent_type=1 (WORKER) como filtro"""
        request = Mock()
        request.agent_type = 1  # WORKER
        request.filters = {}

        await servicer.ListAgents(request, mock_context)

        # Verificar que list_agents foi chamado com AgentType.WORKER
        mock_registry_service.list_agents.assert_called_once()
        call_kwargs = mock_registry_service.list_agents.call_args[1]
        assert call_kwargs["agent_type"] == AgentType.WORKER

    @pytest.mark.asyncio
    async def test_list_agents_without_filter(self, servicer, mock_context, mock_registry_service):
        """Testa ListAgents sem filtro de tipo"""
        request = Mock()
        request.agent_type = 0  # Nenhum filtro (0 = falsy)
        request.filters = {}

        await servicer.ListAgents(request, mock_context)

        call_kwargs = mock_registry_service.list_agents.call_args[1]
        assert call_kwargs["agent_type"] is None
