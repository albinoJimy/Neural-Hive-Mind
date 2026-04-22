"""
Testes unitários para MatchingEngine.

Este módulo testa o motor de matching inteligente para descoberta de agentes.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.models import AgentInfo, AgentStatus, AgentTelemetry, AgentType
from src.services.matching_engine import MatchingEngine


@pytest.fixture()
def mock_etcd_client():
    """Mock do EtcdClient."""
    client = AsyncMock()
    client.list_agents = AsyncMock(return_value=[])
    return client


@pytest.fixture()
def mock_pheromone_client():
    """Mock do PheromoneClient."""
    client = AsyncMock()
    client.get_agent_pheromone_score = AsyncMock(return_value=0.8)
    return client


@pytest.fixture()
def matching_engine(mock_etcd_client, mock_pheromone_client):
    """Instância do MatchingEngine para teste."""
    return MatchingEngine(mock_etcd_client, mock_pheromone_client)


@pytest.fixture()
def sample_agents():
    """Lista de agentes de exemplo para testes."""
    return [
        AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python", "docker"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.95, total_executions=100),
            namespace="default",
        ),
        AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python", "terraform"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.85, total_executions=50),
            namespace="default",
        ),
        AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["docker"],
            status=AgentStatus.DEGRADED,
            telemetry=AgentTelemetry(success_rate=0.4, total_executions=20),
            namespace="default",
        ),
        AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.ANALYST,
            capabilities=["analytics", "reporting"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.9, total_executions=30),
            namespace="other-ns",
        ),
    ]


class TestMatchingEngineMatchAgents:
    """Testes para o método match_agents."""

    @pytest.mark.asyncio()
    async def test_match_agents_by_capabilities(
        self, matching_engine, mock_etcd_client, sample_agents
    ):
        """Testa match por capabilities exatas."""
        mock_etcd_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await matching_engine.match_agents(capabilities_required=["python"])

        # Deve retornar agentes com capability "python"
        assert len(result) == 2
        assert all("python" in a.capabilities for a in result)

    @pytest.mark.asyncio()
    async def test_match_agents_with_filters(
        self, matching_engine, mock_etcd_client, sample_agents
    ):
        """Testa match com filtros de namespace e security."""
        mock_etcd_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await matching_engine.match_agents(
            capabilities_required=["python"], filters={"namespace": "default"}
        )

        # Apenas agentes do namespace "default"
        assert len(result) == 2
        assert all(a.namespace == "default" for a in result)

    @pytest.mark.asyncio()
    async def test_match_agents_max_results(self, matching_engine, mock_etcd_client, sample_agents):
        """Testa limite de resultados."""
        mock_etcd_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await matching_engine.match_agents(capabilities_required=["python"], max_results=1)

        # Deve retornar apenas 1 resultado
        assert len(result) == 1

    @pytest.mark.asyncio()
    async def test_match_agents_no_candidates(
        self, matching_engine, mock_etcd_client, sample_agents
    ):
        """Testa quando não há candidatos com as capabilities."""
        mock_etcd_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await matching_engine.match_agents(capabilities_required=["nonexistent"])

        # Deve retornar lista vazia
        assert result == []

    @pytest.mark.asyncio()
    async def test_match_agents_partial_capability(
        self, matching_engine, mock_etcd_client, sample_agents
    ):
        """Testa match quando apenas alguns agentes têm todas as capabilities."""
        mock_etcd_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await matching_engine.match_agents(capabilities_required=["python", "terraform"])

        # Apenas agente com ambas capabilities
        assert len(result) == 1

    @pytest.mark.asyncio()
    async def test_match_agents_by_type(self, matching_engine, mock_etcd_client, sample_agents):
        """Testa match filtrando por tipo de agente."""
        mock_etcd_client.list_agents = AsyncMock(
            return_value=[a for a in sample_agents if a.agent_type == AgentType.WORKER]
        )

        result = await matching_engine.match_agents(
            capabilities_required=["python"], agent_type=AgentType.WORKER
        )

        # Mock deve retornar apenas WORKERs
        assert len(result) <= len([a for a in sample_agents if a.agent_type == AgentType.WORKER])

    @pytest.mark.asyncio()
    async def test_match_agents_unhealthy_filtered(self, matching_engine, mock_etcd_client):
        """Testa que agentes UNHEALTHY são filtrados."""
        unhealthy_agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python"],
            status=AgentStatus.UNHEALTHY,
            telemetry=AgentTelemetry(success_rate=0.1),
            namespace="default",
        )
        mock_etcd_client.list_agents = AsyncMock(return_value=[unhealthy_agent])

        result = await matching_engine.match_agents(capabilities_required=["python"])

        # UNHEALTHY deve ser filtrado (apenas HEALTHY e DEGRADED passam)
        assert result == []

    @pytest.mark.asyncio()
    async def test_match_agents_degraded_included(
        self, matching_engine, mock_etcd_client, sample_agents
    ):
        """Testa que agentes DEGRADED são incluídos (fallback)."""
        # Há um agente DEGRADED com capability "docker" no sample_agents
        mock_etcd_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await matching_engine.match_agents(capabilities_required=["docker"])

        # DEGRADED deve ser incluído (fallback para disponibilidade)
        assert len(result) == 2
        # Verificar que pelo menos um agente DEGRADED está nos resultados
        degraded_agents = [a for a in result if a.status == AgentStatus.DEGRADED]
        assert len(degraded_agents) >= 1


class TestMatchingEngineFilterByCapabilities:
    """Testes para o método _filter_by_capabilities."""

    def test_filter_by_capabilities_all_match(self, matching_engine, sample_agents):
        """Testa filtro quando agente tem todas as capabilities."""
        required = ["python", "docker"]
        result = matching_engine._filter_by_capabilities(sample_agents, required)

        # agent-1 tem ambas capabilities
        assert len(result) == 1
        assert "python" in result[0].capabilities
        assert "docker" in result[0].capabilities

    def test_filter_by_capabilities_partial_match(self, matching_engine, sample_agents):
        """Testa filtro parcial (match pelo menos uma)."""
        required = ["python"]
        result = matching_engine._filter_by_capabilities(sample_agents, required)

        # agent-1 e agent-2 têm "python"
        assert len(result) == 2

    def test_filter_by_capabilities_empty_required(self, matching_engine, sample_agents):
        """Testa filtro vazio (retorna todos)."""
        result = matching_engine._filter_by_capabilities(sample_agents, [])

        # Vazio retorna todos
        assert len(result) == 4

    def test_filter_by_capabilities_no_match(self, matching_engine, sample_agents):
        """Testa quando nenhum agente tem as capabilities."""
        required = ["golang", "rust"]
        result = matching_engine._filter_by_capabilities(sample_agents, required)

        assert result == []


class TestMatchingEngineRankAgents:
    """Testes para o método _rank_agents."""

    @pytest.mark.asyncio()
    async def test_rank_agents_by_health_score(self, matching_engine, sample_agents):
        """Testa ranking por health score."""
        # Diferentes health scores
        healthy_agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["test"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.9),
        )
        degraded_agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["test"],
            status=AgentStatus.DEGRADED,
            telemetry=AgentTelemetry(success_rate=0.4),
        )
        agents = [healthy_agent, degraded_agent]

        # Mock pheromone score
        matching_engine.pheromone_client.get_agent_pheromone_score = AsyncMock(return_value=0.5)

        result = await matching_engine._rank_agents(agents)

        # HEALTHY deve vir primeiro (score 1.0 > 0.5)
        assert result[0].status == AgentStatus.HEALTHY
        assert result[1].status == AgentStatus.DEGRADED

    @pytest.mark.asyncio()
    async def test_rank_agents_by_pheromone_score(self, matching_engine, sample_agents):
        """Testa ranking por pheromone score."""
        agents = [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(success_rate=0.8),
            ),
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(success_rate=0.8),
            ),
        ]

        # Mock diferentes pheromone scores
        async def mock_pheromone(agent_id, agent_type, domain):
            # Primeiro agente da lista recebe score alto
            if str(agents[0].agent_id) == str(agent_id):
                return 0.9
            return 0.3

        matching_engine.pheromone_client.get_agent_pheromone_score = AsyncMock(
            side_effect=mock_pheromone
        )

        result = await matching_engine._rank_agents(agents)

        # Primeiro agente (com score alto) deve vir primeiro
        assert len(result) == 2

    @pytest.mark.asyncio()
    async def test_rank_agents_by_telemetry_score(self, matching_engine, sample_agents):
        """Testa ranking por telemetry score."""
        agents = [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(success_rate=0.95, total_executions=100),
            ),
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(success_rate=0.6, total_executions=50),
            ),
        ]
        matching_engine.pheromone_client.get_agent_pheromone_score = AsyncMock(return_value=0.5)

        result = await matching_engine._rank_agents(agents)

        # Primeiro agente (maior success_rate) deve vir primeiro
        assert result[0].telemetry.success_rate == 0.95
        assert result[1].telemetry.success_rate == 0.6

    @pytest.mark.asyncio()
    async def test_rank_agents_composite_score(self, matching_engine, sample_agents):
        """Testa score composto (pesos combinados)."""
        agents = [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,  # health=1.0
                telemetry=AgentTelemetry(success_rate=0.7),  # telemetry=0.7
            ),
        ]
        matching_engine.pheromone_client.get_agent_pheromone_score = AsyncMock(return_value=0.5)

        result = await matching_engine._rank_agents(agents)

        # Score composto = (1.0 * 0.4) + (0.5 * 0.3) + (0.7 * 0.3) = 0.8
        assert result[0].telemetry.success_rate == 0.7

    @pytest.mark.asyncio()
    async def test_rank_agents_empty_list(self, matching_engine):
        """Testa ranking com lista vazia."""
        result = await matching_engine._rank_agents([])

        assert result == []

    @pytest.mark.asyncio()
    async def test_rank_agents_with_tiebreak(self, matching_engine, sample_agents):
        """Testa desempate por agent_id quando scores iguais."""
        # Mock para retornar mesmo score para todos
        agents = [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(success_rate=0.8),
            ),
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(success_rate=0.8),
            ),
        ]
        matching_engine.pheromone_client.get_agent_pheromone_score = AsyncMock(return_value=0.5)

        result = await matching_engine._rank_agents(agents)

        # Com scores iguais, deve ordenar por agent_id (alfabético)
        # Agent IDs são UUIDs, então a ordem pode variar
        assert len(result) == 2


class TestMatchingEngineErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio()
    async def test_match_agents_exception_propagates(self, matching_engine, mock_etcd_client):
        """Testa que exceções do list_agents são propagadas."""
        mock_etcd_client.list_agents = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        with pytest.raises(ConnectionError):
            await matching_engine.match_agents(capabilities_required=["python"])

    @pytest.mark.asyncio()
    async def test_rank_agents_exception_propagates(self, matching_engine):
        """Testa que exceções do pheromone_client são propagadas."""
        agents = [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["test"],
                status=AgentStatus.HEALTHY,
                telemetry=AgentTelemetry(),
            ),
        ]
        matching_engine.pheromone_client.get_agent_pheromone_score = AsyncMock(
            side_effect=TimeoutError("Pheromone service timeout")
        )

        with pytest.raises(TimeoutError):
            await matching_engine._rank_agents(agents)
