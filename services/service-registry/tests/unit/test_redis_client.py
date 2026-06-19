"""
Testes unitários para RedisRegistryClient.

Este módulo testa o cliente Redis para operações de registro.
"""

import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from src.clients.redis_registry_client import RedisRegistryClient
from src.models import AgentInfo, AgentStatus, AgentTelemetry, AgentType


@pytest.fixture()
def redis_client():
    """Instância do RedisRegistryClient para teste."""
    return RedisRegistryClient(
        cluster_nodes=["localhost:6379"], prefix="/neural-hive", password="testpass", timeout=5
    )


@pytest.fixture()
def mock_redis_connection():
    """Mock de conexão Redis."""
    connection = AsyncMock()
    connection.ping = AsyncMock(return_value=True)
    connection.setex = AsyncMock(return_value=True)
    connection.get = AsyncMock(return_value=None)
    connection.delete = AsyncMock(return_value=0)
    connection.sadd = AsyncMock(return_value=1)
    connection.srem = AsyncMock(return_value=1)
    connection.smembers = AsyncMock(return_value=set())
    connection.exists = AsyncMock(return_value=1)
    connection.expire = AsyncMock(return_value=True)
    connection.publish = AsyncMock(return_value=1)
    connection.close = AsyncMock(return_value=True)
    return connection


@pytest.fixture()
def sample_agent():
    """Agente de exemplo para testes."""
    return AgentInfo(
        agent_id=uuid4(),
        agent_type=AgentType.WORKER,
        capabilities=["python", "docker"],
        status=AgentStatus.HEALTHY,
        telemetry=AgentTelemetry(success_rate=0.9, total_executions=100),
        namespace="default",
        cluster="local",
        version="1.0.0",
    )


class TestRedisRegistryClientInitialization:
    """Testes para inicialização do RedisRegistryClient."""

    @pytest.mark.asyncio()
    async def test_initialize_success(self, redis_client, mock_redis_connection):
        """Testa inicialização bem-sucedida."""
        with patch("redis.asyncio.Redis", return_value=mock_redis_connection):
            await redis_client.initialize()

            assert redis_client.client is not None
            mock_redis_connection.ping.assert_called_once()

    @pytest.mark.asyncio()
    async def test_initialize_invalid_endpoint(self):
        """Testa erro com endpoint inválido."""
        client = RedisRegistryClient(cluster_nodes=["invalid_endpoint"], prefix="/test")

        with pytest.raises(ValueError) as exc_info:
            await client.initialize()

        assert "Formato de endpoint inválido" in str(exc_info.value)

    @pytest.mark.asyncio()
    async def test_initialize_empty_nodes(self):
        """Testa erro com cluster_nodes vazio."""
        client = RedisRegistryClient(cluster_nodes=[], prefix="/test")

        with pytest.raises(ValueError) as exc_info:
            await client.initialize()

        assert "não pode estar vazio" in str(exc_info.value)

    @pytest.mark.asyncio()
    async def test_initialize_invalid_port(self):
        """Testa erro com porta inválida."""
        client = RedisRegistryClient(cluster_nodes=["localhost:abc"], prefix="/test")

        with pytest.raises(ValueError) as exc_info:
            await client.initialize()

        assert "Porta inválida" in str(exc_info.value)

    @pytest.mark.asyncio()
    async def test_initialize_timeout_on_connection(self, redis_client):
        """Testa timeout de conexão."""
        mock_conn = AsyncMock()
        mock_conn.ping = AsyncMock(side_effect=TimeoutError("Connection timeout"))

        with patch("redis.asyncio.Redis", return_value=mock_conn):
            with pytest.raises(TimeoutError):
                await redis_client.initialize()

    @pytest.mark.asyncio()
    async def test_initialize_auth_failure(self, redis_client):
        """Testa falha de autenticação."""
        mock_conn = AsyncMock()
        mock_conn.ping = AsyncMock(side_effect=PermissionError("NOAUTH"))

        with patch("redis.asyncio.Redis", return_value=mock_conn):
            with pytest.raises(PermissionError):
                await redis_client.initialize()

    def test_get_agent_key(self, redis_client):
        """Testa geração de chave Redis para agente."""
        agent_type = AgentType.WORKER
        agent_id = "123e4567-e89b-12d3-a456-426614174000"

        key = redis_client._get_agent_key(agent_type, agent_id)

        assert key == "/neural-hive:worker:123e4567-e89b-12d3-a456-426614174000"


class TestRedisRegistryClientCRUD:
    """Testes para operações CRUD do RedisRegistryClient."""

    @pytest.mark.asyncio()
    async def test_put_agent(self, redis_client, mock_redis_connection, sample_agent):
        """Testa salvar agente no Redis."""
        redis_client.client = mock_redis_connection

        result = await redis_client.put_agent(sample_agent)

        assert result is True
        mock_redis_connection.setex.assert_called_once()
        mock_redis_connection.sadd.assert_called_once()
        mock_redis_connection.publish.assert_called_once()

    @pytest.mark.asyncio()
    async def test_get_agent(self, redis_client, mock_redis_connection, sample_agent):
        """Testa buscar agente existente."""
        agent_data = json.dumps(sample_agent.to_proto_dict())
        mock_redis_connection.get = AsyncMock(return_value=agent_data)
        redis_client.client = mock_redis_connection

        result = await redis_client.get_agent(sample_agent.agent_id)

        assert result is not None
        assert result.agent_id == sample_agent.agent_id
        assert result.agent_type == sample_agent.agent_type

    @pytest.mark.asyncio()
    async def test_get_agent_not_found(self, redis_client, mock_redis_connection):
        """Testa buscar agente inexistente."""
        mock_redis_connection.get = AsyncMock(return_value=None)
        redis_client.client = mock_redis_connection

        result = await redis_client.get_agent(uuid4())

        assert result is None

    @pytest.mark.asyncio()
    async def test_delete_agent(self, redis_client, mock_redis_connection, sample_agent):
        """Testa remover agente do Redis."""
        mock_redis_connection.delete = AsyncMock(return_value=1)
        redis_client.client = mock_redis_connection

        result = await redis_client.delete_agent(sample_agent.agent_id)

        assert result is True
        mock_redis_connection.delete.assert_called()
        mock_redis_connection.srem.assert_called()

    @pytest.mark.asyncio()
    async def test_delete_agent_not_found(self, redis_client, mock_redis_connection):
        """Testa remover agente inexistente."""
        mock_redis_connection.delete = AsyncMock(return_value=0)
        redis_client.client = mock_redis_connection

        result = await redis_client.delete_agent(uuid4())

        assert result is False


class TestRedisRegistryClientListing:
    """Testes para listagem de agentes."""

    @pytest.mark.asyncio()
    async def test_list_agents_empty(self, redis_client, mock_redis_connection):
        """Testa listagem quando não há agentes."""
        mock_redis_connection.smembers = AsyncMock(return_value=set())
        redis_client.client = mock_redis_connection

        result = await redis_client.list_agents()

        assert result == []

    @pytest.mark.asyncio()
    async def test_list_agents_all(self, redis_client, mock_redis_connection, sample_agent):
        """Testa listar todos os agentes."""
        agent_data = json.dumps(sample_agent.to_proto_dict())

        # Mock que retorna vazio para tipos que não são WORKER
        async def mock_smembers(key):
            if "worker" in key.lower():
                return {str(sample_agent.agent_id)}
            return set()

        mock_redis_connection.smembers = AsyncMock(side_effect=mock_smembers)
        mock_redis_connection.get = AsyncMock(return_value=agent_data)
        redis_client.client = mock_redis_connection

        result = await redis_client.list_agents()

        assert len(result) == 1
        assert result[0].agent_id == sample_agent.agent_id

    @pytest.mark.asyncio()
    async def test_list_agents_by_type(self, redis_client, mock_redis_connection, sample_agent):
        """Testa listar agentes por tipo."""
        agent_data = json.dumps(sample_agent.to_proto_dict())
        mock_redis_connection.smembers = AsyncMock(return_value={str(sample_agent.agent_id)})
        mock_redis_connection.get = AsyncMock(return_value=agent_data)
        redis_client.client = mock_redis_connection

        result = await redis_client.list_agents(agent_type=AgentType.WORKER)

        assert len(result) == 1
        assert result[0].agent_type == AgentType.WORKER

    @pytest.mark.asyncio()
    async def test_list_agents_with_filters(
        self, redis_client, mock_redis_connection, sample_agent
    ):
        """Testa listar agentes com filtros."""
        agent_data = json.dumps(sample_agent.to_proto_dict())

        # Mock que retorna vazio para tipos que não são WORKER
        async def mock_smembers(key):
            if "worker" in key.lower():
                return {str(sample_agent.agent_id)}
            return set()

        mock_redis_connection.smembers = AsyncMock(side_effect=mock_smembers)
        mock_redis_connection.get = AsyncMock(return_value=agent_data)
        redis_client.client = mock_redis_connection

        result = await redis_client.list_agents(filters={"namespace": "default"})

        assert len(result) == 1
        assert result[0].namespace == "default"

    @pytest.mark.asyncio()
    async def test_list_agents_filter_no_match(
        self, redis_client, mock_redis_connection, sample_agent
    ):
        """Testa filtro que não retorna match."""
        agent_data = json.dumps(sample_agent.to_proto_dict())
        mock_redis_connection.smembers = AsyncMock(return_value={str(sample_agent.agent_id)})
        mock_redis_connection.get = AsyncMock(return_value=agent_data)
        redis_client.client = mock_redis_connection

        result = await redis_client.list_agents(filters={"namespace": "other-ns"})

        assert len(result) == 0

    @pytest.mark.asyncio()
    async def test_list_agents_with_expired_index_entry(
        self, redis_client, mock_redis_connection, sample_agent
    ):
        """Testa que entradas de índice expiradas são removidas."""
        # smembers retorna ID, mas get retorna None (expirou)
        mock_redis_connection.smembers = AsyncMock(return_value={str(sample_agent.agent_id)})
        mock_redis_connection.get = AsyncMock(return_value=None)
        redis_client.client = mock_redis_connection

        result = await redis_client.list_agents()

        assert len(result) == 0
        # Entrada expirada deve ser removida do índice
        mock_redis_connection.srem.assert_called()


class TestRedisRegistryClientFiltering:
    """Testes para filtragem de agentes."""

    def test_matches_filters_namespace(self, redis_client, sample_agent):
        """Testa filtro por namespace."""
        assert redis_client._matches_filters(sample_agent, {"namespace": "default"}) is True
        assert redis_client._matches_filters(sample_agent, {"namespace": "other"}) is False

    def test_matches_filters_cluster(self, redis_client, sample_agent):
        """Testa filtro por cluster."""
        assert redis_client._matches_filters(sample_agent, {"cluster": "local"}) is True
        assert redis_client._matches_filters(sample_agent, {"cluster": "remote"}) is False

    def test_matches_filters_version(self, redis_client, sample_agent):
        """Testa filtro por version."""
        assert redis_client._matches_filters(sample_agent, {"version": "1.0.0"}) is True
        assert redis_client._matches_filters(sample_agent, {"version": "2.0.0"}) is False

    def test_matches_filters_status_case_insensitive(self, redis_client, sample_agent):
        """Filtro de status deve ser case-insensitive (cliente envia 'healthy' minúsculo)."""
        # sample_agent tem status HEALTHY
        assert redis_client._matches_filters(sample_agent, {"status": "healthy"}) is True
        assert redis_client._matches_filters(sample_agent, {"status": "HEALTHY"}) is True
        assert redis_client._matches_filters(sample_agent, {"status": "Healthy"}) is True
        assert redis_client._matches_filters(sample_agent, {"status": "unhealthy"}) is False

    def test_matches_filters_status_healthy_accepts_degraded(self, redis_client):
        """Testa que filtro HEALTHY aceita DEGRADED."""
        degraded_agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["test"],
            status=AgentStatus.DEGRADED,
            telemetry=AgentTelemetry(success_rate=0.4),
            namespace="default",
        )

        assert redis_client._matches_filters(degraded_agent, {"status": "HEALTHY"}) is True

    def test_matches_filters_status_unhealthy_rejected(self, redis_client):
        """Testa que filtro HEALTHY rejeita UNHEALTHY."""
        unhealthy_agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["test"],
            status=AgentStatus.UNHEALTHY,
            telemetry=AgentTelemetry(success_rate=0.1),
            namespace="default",
        )

        assert redis_client._matches_filters(unhealthy_agent, {"status": "HEALTHY"}) is False

    def test_matches_filters_security_level(self, redis_client):
        """Testa filtro por security_level no metadata."""
        agent = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["test"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.9),
            namespace="default",
            metadata={"security_level": "PUBLIC"},
        )

        assert redis_client._matches_filters(agent, {"security_level": "PUBLIC"}) is True
        assert redis_client._matches_filters(agent, {"security_level": "INTERNAL"}) is False


class TestRedisRegistryClientConnection:
    """Testes para gestão de conexão."""

    @pytest.mark.asyncio()
    async def test_close(self, redis_client, mock_redis_connection):
        """Testa fechar conexão."""
        redis_client.client = mock_redis_connection

        await redis_client.close()

        mock_redis_connection.close.assert_called_once()

    @pytest.mark.asyncio()
    async def test_close_without_client(self, redis_client):
        """Testa fechar sem cliente inicializado."""
        # Não deve levantar exceção
        await redis_client.close()

    @pytest.mark.asyncio()
    async def test_connection_failure_during_operation(
        self, redis_client, mock_redis_connection, sample_agent
    ):
        """Testa falha de conexão durante operação."""
        mock_redis_connection.setex = AsyncMock(side_effect=ConnectionError("Connection lost"))
        redis_client.client = mock_redis_connection

        with pytest.raises(ConnectionError):
            await redis_client.put_agent(sample_agent)

    @pytest.mark.asyncio()
    async def test_health_check_success(self, redis_client, mock_redis_connection):
        """Testa verificação de saúde com sucesso."""
        mock_redis_connection.ping = AsyncMock(return_value=True)
        redis_client.client = mock_redis_connection

        result = await redis_client.health_check()

        assert result is True

    @pytest.mark.asyncio()
    async def test_health_check_failure(self, redis_client, mock_redis_connection):
        """Testa verificação de saúde com falha."""
        mock_redis_connection.ping = AsyncMock(side_effect=ConnectionError("Redis down"))
        redis_client.client = mock_redis_connection

        result = await redis_client.health_check()

        assert result is False


class TestRedisRegistryClientHeartbeat:
    """Testes para operações de heartbeat."""

    @pytest.mark.asyncio()
    async def test_heartbeat_success(self, redis_client, mock_redis_connection, sample_agent):
        """Testa renovação de TTL com sucesso."""
        redis_client.client = mock_redis_connection

        result = await redis_client.heartbeat(sample_agent.agent_id, sample_agent.agent_type)

        assert result is True
        mock_redis_connection.expire.assert_called_once()

    @pytest.mark.asyncio()
    async def test_heartbeat_agent_not_found(self, redis_client, mock_redis_connection):
        """Testa heartbeat para agente não encontrado."""
        mock_redis_connection.exists = AsyncMock(return_value=0)
        redis_client.client = mock_redis_connection

        result = await redis_client.heartbeat(uuid4(), AgentType.WORKER)

        assert result is False

    @pytest.mark.asyncio()
    async def test_heartbeat_failure(self, redis_client, mock_redis_connection):
        """Testa falha no heartbeat."""
        mock_redis_connection.expire = AsyncMock(side_effect=Exception("Redis error"))
        redis_client.client = mock_redis_connection

        result = await redis_client.heartbeat(uuid4(), AgentType.WORKER)

        assert result is False


class TestRedisRegistryClientWatch:
    """Testes para funcionalidade de watch."""

    @pytest.mark.asyncio()
    async def test_watch_agents(self, redis_client, mock_redis_connection):
        """Testa observar mudanças em agentes."""

        # Criar um pubsub mock com listen async generator vazio
        async def empty_listen():
            return
            yield  # Empty generator para evitar iteração

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = empty_listen
        mock_redis_connection.pubsub = Mock(return_value=mock_pubsub)
        redis_client.client = mock_redis_connection

        callback = Mock()

        await redis_client.watch_agents(callback)

        assert redis_client._watch_task is not None
        mock_pubsub.subscribe.assert_called_once()
