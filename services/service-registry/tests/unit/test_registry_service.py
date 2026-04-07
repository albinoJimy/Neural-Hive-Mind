"""
Testes unitários para RegistryService.

Este módulo testa o serviço principal de registro de agentes.
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from src.models import AgentInfo, AgentStatus, AgentTelemetry, AgentType
from src.services.registry_service import RegistryService


@pytest.fixture
def mock_redis_client():
    """Mock do RedisRegistryClient com métodos básicos."""
    client = AsyncMock()
    client.put_agent = AsyncMock(return_value=True)
    client.get_agent = AsyncMock(return_value=None)
    client.delete_agent = AsyncMock(return_value=True)
    client.list_agents = AsyncMock(return_value=[])
    client._get_agent_key = Mock(side_effect=lambda t, i: f"/agents/{t.value}/{i}")
    client.prefix = "/neural-hive"
    client.client = AsyncMock()
    client.client.setex = AsyncMock(return_value=True)
    client.client.sadd = AsyncMock(return_value=True)
    client.client.publish = AsyncMock(return_value=True)
    return client


@pytest.fixture
def registry_service(mock_redis_client):
    """Instância do RegistryService para teste."""
    return RegistryService(etcd_client=mock_redis_client)


class TestRegistryServiceRegisterAgent:
    """Testes para o método register_agent."""

    @pytest.mark.asyncio
    async def test_register_agent_success(self, registry_service, mock_redis_client):
        """Testa registro de agente com dados válidos."""
        agent_type = AgentType.WORKER
        capabilities = ["python", "docker"]
        metadata = {"version": "1.0.0"}

        agent_id, token = await registry_service.register_agent(
            agent_type=agent_type, capabilities=capabilities, metadata=metadata, namespace="test-ns"
        )

        assert isinstance(agent_id, type(uuid4()))
        assert isinstance(token, str)
        assert token.startswith("token-")
        mock_redis_client.put_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_agent_empty_capabilities(self, registry_service):
        """Testa que registro com capabilities vazias levanta ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await registry_service.register_agent(
                agent_type=AgentType.WORKER, capabilities=[], metadata={"version": "1.0.0"}
            )
        assert "Capabilities não podem estar vazias" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_register_agent_none_capabilities(self, registry_service):
        """Testa que registro com capabilities None levanta ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await registry_service.register_agent(
                agent_type=AgentType.WORKER, capabilities=None, metadata={"version": "1.0.0"}
            )
        assert "Capabilities não podem estar vazias" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_register_agent_missing_namespace(self, registry_service):
        """Testa que registro sem namespace levanta ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await registry_service.register_agent(
                agent_type=AgentType.WORKER,
                capabilities=["python"],
                metadata={},  # metadata sem namespace
                namespace="",  # namespace vazio
            )
        assert "Namespace é obrigatório" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_register_agent_with_metadata_namespace(
        self, registry_service, mock_redis_client
    ):
        """Testa registro com namespace no metadata (deve funcionar)."""
        agent_type = AgentType.WORKER
        capabilities = ["python"]
        metadata = {"namespace": "custom-ns"}  # namespace no metadata

        agent_id, token = await registry_service.register_agent(
            agent_type=agent_type, capabilities=capabilities, metadata=metadata
        )

        assert isinstance(agent_id, type(uuid4()))
        mock_redis_client.put_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_agent_default_values(self, registry_service, mock_redis_client):
        """Testa que registro usa valores default corretos."""
        agent_type = AgentType.SCOUT
        capabilities = ["exploration"]

        agent_id, token = await registry_service.register_agent(
            agent_type=agent_type, capabilities=capabilities, metadata={"version": "1.0.0"}
        )

        # Verificar que put_agent foi chamado com valores default
        call_args = mock_redis_client.put_agent.call_args
        agent_info = call_args[0][0]

        assert agent_info.namespace == "default"
        assert agent_info.cluster == "local"
        assert agent_info.version == "1.0.0"
        assert agent_info.status == AgentStatus.HEALTHY


class TestRegistryServiceUpdateHeartbeat:
    """Testes para o método update_heartbeat."""

    @pytest.fixture
    def sample_agent(self):
        """Agente de exemplo para heartbeat."""
        return AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python"],
            metadata={},
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.9, total_executions=100),
        )

    @pytest.mark.asyncio
    async def test_update_heartbeat_success(
        self, registry_service, mock_redis_client, sample_agent
    ):
        """Testa update de heartbeat com sucesso."""
        mock_redis_client.get_agent = AsyncMock(return_value=sample_agent)

        status = await registry_service.update_heartbeat(sample_agent.agent_id)

        assert status == AgentStatus.HEALTHY
        mock_redis_client.get_agent.assert_called_once_with(sample_agent.agent_id)

    @pytest.mark.asyncio
    async def test_update_heartbeat_with_telemetry(
        self, registry_service, mock_redis_client, sample_agent
    ):
        """Testa update de heartbeat com nova telemetria."""
        mock_redis_client.get_agent = AsyncMock(return_value=sample_agent)
        new_telemetry = AgentTelemetry(success_rate=0.95, total_executions=150)

        status = await registry_service.update_heartbeat(
            sample_agent.agent_id, telemetry=new_telemetry
        )

        assert status == AgentStatus.HEALTHY
        # Verificar que a telemetria foi atualizada
        call_args = mock_redis_client.client.setex.call_args_list
        # Pode ser chamado múltiplas vezes (setex, sadd, publish)
        assert len(call_args) > 0

    @pytest.mark.asyncio
    async def test_update_heartbeat_status_change_to_degraded(
        self, registry_service, mock_redis_client
    ):
        """Testa mudança de status para DEGRADED."""
        agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python"],
            metadata={},
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.4),  # Baixo success rate
        )
        mock_redis_client.get_agent = AsyncMock(return_value=agent)

        status = await registry_service.update_heartbeat(agent.agent_id)

        assert status == AgentStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_update_heartbeat_status_change_to_unhealthy(
        self, registry_service, mock_redis_client
    ):
        """Testa mudança de status para UNHEALTHY."""
        agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python"],
            metadata={},
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.2),  # Muito baixo
        )
        mock_redis_client.get_agent = AsyncMock(return_value=agent)

        status = await registry_service.update_heartbeat(agent.agent_id)

        assert status == AgentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_update_heartbeat_status_recovery_to_healthy(
        self, registry_service, mock_redis_client
    ):
        """Testa recuperação de status para HEALTHY."""
        agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python"],
            metadata={},
            status=AgentStatus.DEGRADED,
            telemetry=AgentTelemetry(success_rate=0.8),  # Bom success rate
        )
        mock_redis_client.get_agent = AsyncMock(return_value=agent)

        status = await registry_service.update_heartbeat(agent.agent_id)

        assert status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_update_heartbeat_not_found(self, registry_service, mock_redis_client):
        """Testa update de agente que não existe."""
        mock_redis_client.get_agent = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as exc_info:
            await registry_service.update_heartbeat(uuid4())
        assert "não encontrado" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_heartbeat_without_telemetry_uses_default(
        self, registry_service, mock_redis_client, sample_agent
    ):
        """Testa update sem telemetria (usa existente)."""
        mock_redis_client.get_agent = AsyncMock(return_value=sample_agent)

        status = await registry_service.update_heartbeat(sample_agent.agent_id)

        assert status == AgentStatus.HEALTHY
        # last_seen deve ser atualizado mesmo sem nova telemetria


class TestRegistryServiceDeregisterAgent:
    """Testes para o método deregister_agent."""

    @pytest.mark.asyncio
    async def test_deregister_agent_success(self, registry_service, mock_redis_client):
        """Testa desregistro de agente com sucesso."""
        agent = AgentInfo(
            agent_id=uuid4(), agent_type=AgentType.WORKER, capabilities=["python"], metadata={}
        )
        mock_redis_client.get_agent = AsyncMock(return_value=agent)
        mock_redis_client.delete_agent = AsyncMock(return_value=True)

        result = await registry_service.deregister_agent(agent.agent_id)

        assert result is True
        mock_redis_client.delete_agent.assert_called_once_with(agent.agent_id)

    @pytest.mark.asyncio
    async def test_deregister_agent_not_found(self, registry_service, mock_redis_client):
        """Testa desregistro de agente que não existe."""
        mock_redis_client.get_agent = AsyncMock(return_value=None)
        mock_redis_client.delete_agent = AsyncMock(return_value=False)

        result = await registry_service.deregister_agent(uuid4())

        # Se o agente não existe, delete_agent pode retornar False
        # ou o método pode levantar exceção - aqui assumimos retorno False
        assert result is False

    @pytest.mark.asyncio
    async def test_deregister_agent_already_deregistered(self, registry_service, mock_redis_client):
        """Testa desregistro de agente já desregistrado."""
        agent_id = uuid4()
        mock_redis_client.get_agent = AsyncMock(return_value=None)
        mock_redis_client.delete_agent = AsyncMock(return_value=False)

        result = await registry_service.deregister_agent(agent_id)

        assert result is False


class TestRegistryServiceGetAgent:
    """Testes para o método get_agent."""

    @pytest.mark.asyncio
    async def test_get_agent_success(self, registry_service, mock_redis_client):
        """Testa obter agente existente."""
        agent = AgentInfo(
            agent_id=uuid4(), agent_type=AgentType.ANALYST, capabilities=["analytics"], metadata={}
        )
        mock_redis_client.get_agent = AsyncMock(return_value=agent)

        result = await registry_service.get_agent(agent.agent_id)

        assert result == agent
        assert result.agent_id == agent.agent_id
        assert result.agent_type == AgentType.ANALYST

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, registry_service, mock_redis_client):
        """Testa obter agente inexistente."""
        mock_redis_client.get_agent = AsyncMock(return_value=None)

        result = await registry_service.get_agent(uuid4())

        assert result is None


class TestRegistryServiceListAgents:
    """Testes para o método list_agents."""

    @pytest.fixture
    def sample_agents(self):
        """Lista de agentes de exemplo."""
        return [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["python"],
                status=AgentStatus.HEALTHY,
                namespace="default",
            ),
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.SCOUT,
                capabilities=["exploration"],
                status=AgentStatus.DEGRADED,
                namespace="default",
            ),
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=["docker"],
                status=AgentStatus.UNHEALTHY,
                namespace="other-ns",
            ),
        ]

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, registry_service, mock_redis_client):
        """Testa listagem quando não há agentes."""
        mock_redis_client.list_agents = AsyncMock(return_value=[])

        result = await registry_service.list_agents()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_agents_returns_all(
        self, registry_service, mock_redis_client, sample_agents
    ):
        """Testa listagem de todos os agentes."""
        mock_redis_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await registry_service.list_agents()

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_agents_filtering_by_status(
        self, registry_service, mock_redis_client, sample_agents
    ):
        """Testa filtro por status via filters parameter."""

        # O etcd_client.list_agents deve aplicar o filtro
        def mock_list_filter(agent_type, filters):
            if filters and filters.get("status") == "HEALTHY":
                return [a for a in sample_agents if a.status == AgentStatus.HEALTHY]
            return sample_agents

        mock_redis_client.list_agents = AsyncMock(side_effect=mock_list_filter)

        result = await registry_service.list_agents(filters={"status": "HEALTHY"})

        assert len(result) == 1
        assert result[0].status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_list_agents_filtering_by_namespace(
        self, registry_service, mock_redis_client, sample_agents
    ):
        """Testa filtro por namespace."""

        def mock_list_filter(agent_type, filters):
            if filters and filters.get("namespace") == "default":
                return [a for a in sample_agents if a.namespace == "default"]
            return sample_agents

        mock_redis_client.list_agents = AsyncMock(side_effect=mock_list_filter)

        result = await registry_service.list_agents(filters={"namespace": "default"})

        assert len(result) == 2
        assert all(a.namespace == "default" for a in result)

    @pytest.mark.asyncio
    async def test_list_agents_by_type(self, registry_service, mock_redis_client, sample_agents):
        """Testa listagem por tipo de agente."""

        def mock_list_by_type(agent_type, filters):
            if agent_type:
                return [a for a in sample_agents if a.agent_type == agent_type]
            return sample_agents

        mock_redis_client.list_agents = AsyncMock(side_effect=mock_list_by_type)

        result = await registry_service.list_agents(agent_type=AgentType.WORKER)

        assert len(result) == 2
        assert all(a.agent_type == AgentType.WORKER for a in result)

    @pytest.mark.asyncio
    async def test_list_agents_by_capability(
        self, registry_service, mock_redis_client, sample_agents
    ):
        """Testa filtro por capability (necessita capability no filtro)."""
        # Nota: A implementação atual não filtra por capability no list_agents
        # Isso é feito pelo MatchingEngine após obter todos
        mock_redis_client.list_agents = AsyncMock(return_value=sample_agents)

        result = await registry_service.list_agents()

        # list_agents retorna todos, o filtro por capability é no MatchingEngine
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_agents_pagination_not_implemented(
        self, registry_service, mock_redis_client
    ):
        """Testa paginação (feature ainda não implementada no proto)."""
        # O proto atual não tem paginação no ListAgents
        # Este teste documenta o comportamento atual
        agents = [
            AgentInfo(
                agent_id=uuid4(),
                agent_type=AgentType.WORKER,
                capabilities=[f"cap{i}" for i in range(10)],
                metadata={},
            )
            for _ in range(100)
        ]

        mock_redis_client.list_agents = AsyncMock(return_value=agents)

        result = await registry_service.list_agents()

        # Retorna todos sem paginação
        assert len(result) == 100


class TestRegistryServiceErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_register_agent_exception_propagates(self, registry_service, mock_redis_client):
        """Testa que exceções do etcd_client são propagadas."""
        mock_redis_client.put_agent = AsyncMock(side_effect=ConnectionError("Etcd unavailable"))

        with pytest.raises(ConnectionError):
            await registry_service.register_agent(
                agent_type=AgentType.WORKER, capabilities=["python"], metadata={"version": "1.0.0"}
            )

    @pytest.mark.asyncio
    async def test_update_heartbeat_exception_propagates(self, registry_service, mock_redis_client):
        """Testa que exceções no update são propagadas."""
        mock_redis_client.get_agent = AsyncMock(side_effect=TimeoutError("Timeout"))

        with pytest.raises(TimeoutError):
            await registry_service.update_heartbeat(uuid4())
