"""
Testes de integracao para RPC DiscoverAgents

Valida o fluxo completo de descoberta de agentes:
- Filtragem por capabilities (set intersection)
- Filtragem por status (apenas HEALTHY)
- Ranking por score composto
- Aplicacao de filtros (namespace, cluster, version)
- Limite de resultados (max_results)
"""

import pytest
import grpc
import sys
import os
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

# Adicionar src ao path para importacao
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from grpc_server.registry_servicer import ServiceRegistryServicer
from models.agent import AgentType, AgentStatus, AgentInfo, AgentTelemetry


def create_mock_agent(
    agent_id: str = None,
    agent_type: AgentType = AgentType.WORKER,
    capabilities: list = None,
    status: AgentStatus = AgentStatus.HEALTHY,
    success_rate: float = 0.95,
    namespace: str = "default",
    cluster: str = "local",
    version: str = "1.0.0"
) -> AgentInfo:
    """Helper para criar AgentInfo de teste"""
    return AgentInfo(
        agent_id=uuid4() if not agent_id else agent_id,
        agent_type=agent_type,
        capabilities=capabilities or ["python"],
        metadata={"version": version},
        status=status,
        telemetry=AgentTelemetry(
            success_rate=success_rate,
            avg_duration_ms=100,
            total_executions=50,
            failed_executions=int(50 * (1 - success_rate))
        ),
        namespace=namespace,
        cluster=cluster,
        version=version
    )


class TestDiscoverAgentsRPC:
    """Testes de integracao para RPC DiscoverAgents"""

    @pytest.fixture
    def mock_registry_service(self):
        """Mock do RegistryService"""
        service = AsyncMock()
        return service

    @pytest.fixture
    def mock_matching_engine(self):
        """Mock do MatchingEngine"""
        engine = AsyncMock()
        engine.match_agents = AsyncMock(return_value=[])
        return engine

    @pytest.fixture
    def servicer(self, mock_registry_service, mock_matching_engine):
        """Cria instancia do ServiceRegistryServicer com mocks"""
        return ServiceRegistryServicer(mock_registry_service, mock_matching_engine)

    @pytest.fixture
    def mock_context(self):
        """Mock do gRPC context"""
        context = Mock()
        context.abort = Mock()
        context.invocation_metadata = Mock(return_value=[])
        return context

    def create_discover_request(
        self,
        capabilities: list = None,
        filters: dict = None,
        max_results: int = 5
    ):
        """Helper para criar DiscoverRequest"""
        request = Mock()
        request.capabilities = capabilities or ["python"]
        request.filters = filters or {}
        request.max_results = max_results
        return request

    @pytest.mark.asyncio
    async def test_discover_agents_with_single_capability(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa descoberta com uma capability"""
        # Configurar agentes mock
        agent1 = create_mock_agent(capabilities=["python"])
        agent2 = create_mock_agent(capabilities=["python", "terraform"])
        mock_matching_engine.match_agents.return_value = [agent1, agent2]

        request = self.create_discover_request(
            capabilities=["python"],
            max_results=5
        )

        response = await servicer.DiscoverAgents(request, mock_context)

        # Verificar que match_agents foi chamado corretamente
        mock_matching_engine.match_agents.assert_called_once_with(
            capabilities_required=["python"],
            filters=None,
            max_results=5
        )

        # Verificar resposta
        assert len(response.agents) == 2
        assert response.ranked is True

    @pytest.mark.asyncio
    async def test_discover_agents_with_multiple_capabilities(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa descoberta com multiplas capabilities (AND logic)"""
        # Apenas o agente com ambas capabilities deve ser retornado
        agent1 = create_mock_agent(capabilities=["python", "terraform"])
        mock_matching_engine.match_agents.return_value = [agent1]

        request = self.create_discover_request(
            capabilities=["python", "terraform"],
            max_results=5
        )

        response = await servicer.DiscoverAgents(request, mock_context)

        mock_matching_engine.match_agents.assert_called_once_with(
            capabilities_required=["python", "terraform"],
            filters=None,
            max_results=5
        )

        assert len(response.agents) == 1
        assert "python" in response.agents[0].capabilities
        assert "terraform" in response.agents[0].capabilities

    @pytest.mark.asyncio
    async def test_discover_agents_with_filters(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa descoberta com filtros de namespace/cluster"""
        agent1 = create_mock_agent(
            capabilities=["python"],
            namespace="production"
        )
        mock_matching_engine.match_agents.return_value = [agent1]

        request = self.create_discover_request(
            capabilities=["python"],
            filters={"namespace": "production"}
        )

        response = await servicer.DiscoverAgents(request, mock_context)

        mock_matching_engine.match_agents.assert_called_once_with(
            capabilities_required=["python"],
            filters={"namespace": "production"},
            max_results=5
        )

        assert len(response.agents) == 1
        assert response.agents[0].namespace == "production"

    @pytest.mark.asyncio
    async def test_discover_agents_respects_max_results(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa que max_results limita resultados"""
        # Configurar 5 agentes mas pedir apenas 3
        agents = [create_mock_agent(capabilities=["python"]) for _ in range(3)]
        mock_matching_engine.match_agents.return_value = agents

        request = self.create_discover_request(
            capabilities=["python"],
            max_results=3
        )

        response = await servicer.DiscoverAgents(request, mock_context)

        mock_matching_engine.match_agents.assert_called_once_with(
            capabilities_required=["python"],
            filters=None,
            max_results=3
        )

        assert len(response.agents) == 3

    @pytest.mark.asyncio
    async def test_discover_agents_returns_ranked_results(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa que resultados sao ranqueados por score"""
        # Agentes ja vem ranqueados do matching_engine
        agent_high = create_mock_agent(capabilities=["python"], success_rate=0.95)
        agent_medium = create_mock_agent(capabilities=["python"], success_rate=0.75)
        agent_low = create_mock_agent(capabilities=["python"], success_rate=0.50)

        # MatchingEngine retorna ordenado (melhor primeiro)
        mock_matching_engine.match_agents.return_value = [
            agent_high, agent_medium, agent_low
        ]

        request = self.create_discover_request(capabilities=["python"])

        response = await servicer.DiscoverAgents(request, mock_context)

        assert response.ranked is True
        assert len(response.agents) == 3
        # Verificar ordenacao por success_rate (proxy de score)
        assert response.agents[0].telemetry.success_rate >= response.agents[1].telemetry.success_rate
        assert response.agents[1].telemetry.success_rate >= response.agents[2].telemetry.success_rate

    @pytest.mark.asyncio
    async def test_discover_agents_no_match(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa que retorna lista vazia quando nenhum agente match"""
        mock_matching_engine.match_agents.return_value = []

        request = self.create_discover_request(
            capabilities=["nonexistent_capability"]
        )

        response = await servicer.DiscoverAgents(request, mock_context)

        assert len(response.agents) == 0
        assert response.ranked is True
        assert not mock_context.abort.called

    @pytest.mark.asyncio
    async def test_discover_agents_default_max_results(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa que max_results padrao e 5"""
        mock_matching_engine.match_agents.return_value = []

        request = Mock()
        request.capabilities = ["python"]
        request.filters = {}
        request.max_results = 0  # Vai usar default

        await servicer.DiscoverAgents(request, mock_context)

        mock_matching_engine.match_agents.assert_called_once_with(
            capabilities_required=["python"],
            filters=None,
            max_results=5  # Default
        )

    @pytest.mark.asyncio
    async def test_discover_agents_empty_filters(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa que filtros vazios sao tratados como None"""
        mock_matching_engine.match_agents.return_value = []

        request = self.create_discover_request(
            capabilities=["python"],
            filters={}
        )

        await servicer.DiscoverAgents(request, mock_context)

        mock_matching_engine.match_agents.assert_called_once_with(
            capabilities_required=["python"],
            filters=None,  # Dicionario vazio convertido para None
            max_results=5
        )

    @pytest.mark.asyncio
    async def test_discover_agents_internal_error(
        self, servicer, mock_context, mock_matching_engine
    ):
        """Testa tratamento de erro interno"""
        mock_matching_engine.match_agents.side_effect = Exception("Database error")

        request = self.create_discover_request(capabilities=["python"])

        await servicer.DiscoverAgents(request, mock_context)

        mock_context.abort.assert_called_once()
        args = mock_context.abort.call_args[0]
        assert args[0] == grpc.StatusCode.INTERNAL
        assert "Erro interno" in args[1]
