"""
Testes end-to-end de descoberta com servidor gRPC real

Testa o fluxo completo usando canais de rede reais:
1. Worker Agent registra com capabilities ["python", "terraform"]
2. Guard Agent registra com capabilities ["security", "audit"]
3. Outro Worker Agent chama discover_agents(["python"])
4. Valida que primeiro Worker e retornado com ranking correto
"""

import pytest
import grpc
import json
import asyncio
import os
import sys
import socket
from uuid import uuid4
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

# Adicionar src ao path para importacao
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from grpc_server.registry_servicer import ServiceRegistryServicer
from models.agent import AgentType, AgentStatus, AgentInfo, AgentTelemetry
from services.matching_engine import MatchingEngine
from services.registry_service import RegistryService
from proto import service_registry_pb2, service_registry_pb2_grpc


def get_free_port() -> int:
    """Obter uma porta livre para o servidor de teste"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class MockPubSub:
    """Mock do Redis PubSub para testes"""

    def __init__(self, mock_client: 'MockRedisClient'):
        self._mock_client = mock_client
        self._subscribed_channel = None
        self._closed = False

    async def subscribe(self, channel: str):
        self._subscribed_channel = channel

    async def listen(self):
        """Gera mensagens do canal subscrito"""
        while not self._closed:
            if self._subscribed_channel and self._subscribed_channel in self._mock_client._pubsub_messages:
                messages = self._mock_client._pubsub_messages[self._subscribed_channel]
                while messages:
                    msg = messages.pop(0)
                    yield {"type": "message", "data": msg}
            await asyncio.sleep(0.01)

    async def unsubscribe(self):
        self._subscribed_channel = None

    async def close(self):
        self._closed = True


class MockRedisClient:
    """Mock do cliente Redis para testes"""

    def __init__(self):
        self._pubsub_messages: dict[str, list] = {}

    async def publish(self, channel: str, message: str):
        if channel not in self._pubsub_messages:
            self._pubsub_messages[channel] = []
        self._pubsub_messages[channel].append(message)

    def pubsub(self):
        return MockPubSub(self)

    async def setex(self, key: str, ttl: int, value: str):
        pass

    async def sadd(self, key: str, value: str):
        pass


class MockEtcdClient:
    """Mock do EtcdClient para testes E2E sem dependencias externas"""

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        self._pubsub_messages: dict[str, list] = {}
        self.prefix = "registry"
        self._mock_redis = MockRedisClient()

    @property
    def client(self):
        """Retorna mock do cliente Redis para pub/sub"""
        return self._mock_redis

    def _get_agent_key(self, agent_type: AgentType, agent_id: str) -> str:
        """Gera chave para o agente (compativel com RedisRegistryClient)"""
        return f"{self.prefix}:{agent_type.value.lower()}:{agent_id}"

    async def initialize(self):
        pass

    async def close(self):
        pass

    async def put_agent(self, agent_info: AgentInfo):
        key = str(agent_info.agent_id)
        self._agents[key] = agent_info
        # Publicar evento de registro
        await self._mock_redis.publish(
            f"{self.prefix}:events",
            json.dumps({"event": "registered", "agent_id": str(agent_info.agent_id)})
        )

    async def get_agent(self, agent_id):
        return self._agents.get(str(agent_id))

    async def delete_agent(self, agent_id) -> bool:
        key = str(agent_id)
        if key in self._agents:
            del self._agents[key]
            # Publicar evento de deregistro
            await self._mock_redis.publish(
                f"{self.prefix}:events",
                json.dumps({"event": "deregistered", "agent_id": str(agent_id)})
            )
            return True
        return False

    async def list_agents(self, agent_type=None, filters=None):
        agents = list(self._agents.values())

        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]

        if filters:
            if 'namespace' in filters:
                agents = [a for a in agents if a.namespace == filters['namespace']]
            if 'cluster' in filters:
                agents = [a for a in agents if a.cluster == filters['cluster']]

        return agents


class MockPheromoneClient:
    """Mock do PheromoneClient para testes E2E"""

    def __init__(self):
        self._scores: dict[str, float] = {}
        self.default_score = 0.8

    async def initialize(self):
        pass

    async def close(self):
        pass

    async def get_agent_pheromone_score(self, agent_id: str, agent_type=None, domain: str = "default") -> float:
        return self._scores.get(agent_id, self.default_score)

    def set_score(self, agent_id: str, score: float):
        self._scores[agent_id] = score


@asynccontextmanager
async def create_grpc_server(etcd_client: MockEtcdClient, pheromone_client: MockPheromoneClient):
    """
    Context manager para criar e gerenciar servidor gRPC real para testes.

    Yields:
        tuple[grpc.aio.Server, int]: Servidor e porta
    """
    port = get_free_port()

    # Criar servicos
    registry_service = RegistryService(etcd_client)
    matching_engine = MatchingEngine(etcd_client, pheromone_client)

    # Criar servicer
    servicer = ServiceRegistryServicer(registry_service, matching_engine)

    # Criar servidor gRPC async
    server = grpc.aio.server()
    service_registry_pb2_grpc.add_ServiceRegistryServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')

    await server.start()

    try:
        yield server, port
    finally:
        await server.stop(grace=0)


@asynccontextmanager
async def create_grpc_channel(port: int):
    """
    Context manager para criar canal gRPC cliente.

    Args:
        port: Porta do servidor

    Yields:
        service_registry_pb2_grpc.ServiceRegistryStub: Stub cliente
    """
    channel = grpc.aio.insecure_channel(f'localhost:{port}')
    stub = service_registry_pb2_grpc.ServiceRegistryStub(channel)

    try:
        yield stub
    finally:
        await channel.close()


class TestDiscoverE2EWithRealServer:
    """Testes end-to-end de descoberta com servidor gRPC real"""

    @pytest.fixture
    def etcd_client(self):
        """Mock do EtcdClient"""
        return MockEtcdClient()

    @pytest.fixture
    def pheromone_client(self):
        """Mock do PheromoneClient"""
        return MockPheromoneClient()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_discovery_flow_with_worker_and_guard(
        self, etcd_client, pheromone_client
    ):
        """
        Testa fluxo completo E2E:
        1. Worker registra com capabilities ["python", "terraform"]
        2. Guard registra com capabilities ["security", "audit"]
        3. Cliente descobre agentes com capability ["python"]
        4. Valida que apenas Worker e retornado
        """
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # 1. Registrar Worker Agent
                worker_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python", "terraform"],
                        metadata={"service": "worker-1"},
                        namespace="production",
                        cluster="us-east-1",
                        version="1.0.0"
                    )
                )
                worker_id = worker_response.agent_id
                assert worker_id is not None
                assert len(worker_id) > 0

                # 2. Registrar Guard Agent
                guard_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.GUARD,
                        capabilities=["security", "audit"],
                        metadata={"service": "guard-1"},
                        namespace="production",
                        cluster="us-east-1",
                        version="1.0.0"
                    )
                )
                guard_id = guard_response.agent_id
                assert guard_id is not None
                assert len(guard_id) > 0
                assert guard_id != worker_id

                # 3. Descobrir agentes com capability "python"
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=5
                    )
                )

                # 4. Validar resposta
                assert discover_response.ranked is True
                assert len(discover_response.agents) == 1

                # Verificar que e o Worker
                discovered_agent = discover_response.agents[0]
                assert discovered_agent.agent_id == worker_id
                assert "python" in discovered_agent.capabilities
                assert "terraform" in discovered_agent.capabilities
                assert discovered_agent.agent_type == service_registry_pb2.WORKER

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discover_multiple_workers_with_ranking(
        self, etcd_client, pheromone_client
    ):
        """Testa descoberta com multiplos workers e ranking por score"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar 3 workers com mesma capability
                worker_ids = []
                for i in range(3):
                    response = await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.WORKER,
                            capabilities=["python"],
                            metadata={"worker_num": str(i)},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )
                    worker_ids.append(response.agent_id)

                    # Enviar heartbeat com telemetria diferente para cada worker
                    success_rate = 0.99 - (i * 0.1)  # 0.99, 0.89, 0.79
                    await stub.Heartbeat(
                        service_registry_pb2.HeartbeatRequest(
                            agent_id=response.agent_id,
                            telemetry=service_registry_pb2.AgentTelemetry(
                                success_rate=success_rate,
                                avg_duration_ms=100,
                                total_executions=100,
                                failed_executions=int(100 * (1 - success_rate))
                            )
                        )
                    )

                # Descobrir agentes
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=10
                    )
                )

                # Validar que todos foram retornados e estao ranqueados
                assert discover_response.ranked is True
                assert len(discover_response.agents) == 3

                # Verificar ordenacao por telemetry score (descrescente)
                success_rates = [
                    agent.telemetry.success_rate
                    for agent in discover_response.agents
                ]
                assert success_rates == sorted(success_rates, reverse=True)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discover_with_namespace_filter(
        self, etcd_client, pheromone_client
    ):
        """Testa descoberta com filtro de namespace via servidor gRPC real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar workers em namespaces diferentes
                prod_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="production",
                        cluster="us-east-1",
                        version="1.0.0"
                    )
                )

                staging_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="staging",
                        cluster="us-east-1",
                        version="1.0.0"
                    )
                )

                # Descobrir apenas no namespace production
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={"namespace": "production"},
                        max_results=10
                    )
                )

                # Validar que apenas o agent do namespace production foi retornado
                assert len(discover_response.agents) == 1
                assert discover_response.agents[0].namespace == "production"
                assert discover_response.agents[0].agent_id == prod_response.agent_id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discover_multiple_capabilities_and_logic(
        self, etcd_client, pheromone_client
    ):
        """Testa que multiplas capabilities usam logica AND via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Worker com ambas capabilities
                both_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python", "terraform", "kubernetes"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Worker apenas com python
                python_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Worker apenas com terraform
                terraform_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["terraform"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Descobrir com ambas capabilities
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python", "terraform"],
                        filters={},
                        max_results=10
                    )
                )

                # Apenas o agent com ambas deve ser retornado
                assert len(discover_response.agents) == 1
                assert discover_response.agents[0].agent_id == both_response.agent_id
                assert "python" in discover_response.agents[0].capabilities
                assert "terraform" in discover_response.agents[0].capabilities

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discover_filters_unhealthy_agents(
        self, etcd_client, pheromone_client
    ):
        """Testa que agentes UNHEALTHY sao filtrados via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar agent saudavel
                healthy_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Enviar heartbeat com alta success_rate
                await stub.Heartbeat(
                    service_registry_pb2.HeartbeatRequest(
                        agent_id=healthy_response.agent_id,
                        telemetry=service_registry_pb2.AgentTelemetry(
                            success_rate=0.95,
                            avg_duration_ms=100,
                            total_executions=100,
                            failed_executions=5
                        )
                    )
                )

                # Registrar agent que vai ficar unhealthy
                unhealthy_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Enviar heartbeat com baixa success_rate (vai marcar como UNHEALTHY)
                await stub.Heartbeat(
                    service_registry_pb2.HeartbeatRequest(
                        agent_id=unhealthy_response.agent_id,
                        telemetry=service_registry_pb2.AgentTelemetry(
                            success_rate=0.1,  # Muito baixa -> UNHEALTHY
                            avg_duration_ms=500,
                            total_executions=100,
                            failed_executions=90
                        )
                    )
                )

                # Descobrir agentes
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=10
                    )
                )

                # Apenas o agent HEALTHY deve ser retornado
                assert len(discover_response.agents) == 1
                assert discover_response.agents[0].agent_id == healthy_response.agent_id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discover_respects_max_results(
        self, etcd_client, pheromone_client
    ):
        """Testa que max_results limita resultados via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar 10 workers
                for i in range(10):
                    await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.WORKER,
                            capabilities=["python"],
                            metadata={"worker": str(i)},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )

                # Descobrir com max_results=3
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=3
                    )
                )

                # Validar limite
                assert len(discover_response.agents) == 3

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_discover_no_matching_capabilities(
        self, etcd_client, pheromone_client
    ):
        """Testa retorno vazio quando nenhum agent tem a capability"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar worker com capabilities especificas
                await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python", "terraform"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )

                # Descobrir capabilities inexistentes
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["go", "rust"],
                        filters={},
                        max_results=10
                    )
                )

                # Nenhum agent deve ser retornado
                assert len(discover_response.agents) == 0
                assert discover_response.ranked is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_register_and_deregister_flow(
        self, etcd_client, pheromone_client
    ):
        """Testa fluxo completo de registro e deregistro via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar agent
                register_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )
                agent_id = register_response.agent_id

                # Verificar que agent pode ser descoberto
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=10
                    )
                )
                assert len(discover_response.agents) == 1

                # Deregistrar agent
                deregister_response = await stub.Deregister(
                    service_registry_pb2.DeregisterRequest(agent_id=agent_id)
                )
                assert deregister_response.success is True

                # Verificar que agent nao pode mais ser descoberto
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=10
                    )
                )
                assert len(discover_response.agents) == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_heartbeat_updates_telemetry(
        self, etcd_client, pheromone_client
    ):
        """Testa que heartbeat atualiza telemetria via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar agent
                register_response = await stub.Register(
                    service_registry_pb2.RegisterRequest(
                        agent_type=service_registry_pb2.WORKER,
                        capabilities=["python"],
                        metadata={},
                        namespace="default",
                        cluster="local",
                        version="1.0.0"
                    )
                )
                agent_id = register_response.agent_id

                # Enviar heartbeat com telemetria
                heartbeat_response = await stub.Heartbeat(
                    service_registry_pb2.HeartbeatRequest(
                        agent_id=agent_id,
                        telemetry=service_registry_pb2.AgentTelemetry(
                            success_rate=0.85,
                            avg_duration_ms=150,
                            total_executions=200,
                            failed_executions=30
                        )
                    )
                )

                # Verificar resposta do heartbeat
                assert heartbeat_response.status == service_registry_pb2.HEALTHY

                # Verificar telemetria foi atualizada via GetAgent
                get_response = await stub.GetAgent(
                    service_registry_pb2.GetAgentRequest(agent_id=agent_id)
                )
                assert get_response.agent.telemetry.success_rate == 0.85
                assert get_response.agent.telemetry.avg_duration_ms == 150
                assert get_response.agent.telemetry.total_executions == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_agents_by_type(
        self, etcd_client, pheromone_client
    ):
        """Testa listagem de agentes por tipo via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar workers e guards
                for _ in range(3):
                    await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.WORKER,
                            capabilities=["python"],
                            metadata={},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )

                for _ in range(2):
                    await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.GUARD,
                            capabilities=["security"],
                            metadata={},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )

                # Listar apenas workers
                list_response = await stub.ListAgents(
                    service_registry_pb2.ListAgentsRequest(
                        agent_type=service_registry_pb2.WORKER,
                        filters={}
                    )
                )
                assert len(list_response.agents) == 3
                for agent in list_response.agents:
                    assert agent.agent_type == service_registry_pb2.WORKER

                # Listar apenas guards
                list_response = await stub.ListAgents(
                    service_registry_pb2.ListAgentsRequest(
                        agent_type=service_registry_pb2.GUARD,
                        filters={}
                    )
                )
                assert len(list_response.agents) == 2
                for agent in list_response.agents:
                    assert agent.agent_type == service_registry_pb2.GUARD

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_registrations(
        self, etcd_client, pheromone_client
    ):
        """Testa registros concorrentes via servidor real"""
        async with create_grpc_server(etcd_client, pheromone_client) as (server, port):
            async with create_grpc_channel(port) as stub:
                # Registrar 20 agents concorrentemente
                async def register_agent(idx: int):
                    return await stub.Register(
                        service_registry_pb2.RegisterRequest(
                            agent_type=service_registry_pb2.WORKER,
                            capabilities=["python", f"cap-{idx}"],
                            metadata={"idx": str(idx)},
                            namespace="default",
                            cluster="local",
                            version="1.0.0"
                        )
                    )

                tasks = [register_agent(i) for i in range(20)]
                responses = await asyncio.gather(*tasks)

                # Verificar que todos foram registrados com IDs unicos
                agent_ids = [r.agent_id for r in responses]
                assert len(agent_ids) == 20
                assert len(set(agent_ids)) == 20  # Todos unicos

                # Verificar que todos podem ser descobertos
                discover_response = await stub.DiscoverAgents(
                    service_registry_pb2.DiscoverRequest(
                        capabilities=["python"],
                        filters={},
                        max_results=30
                    )
                )
                assert len(discover_response.agents) == 20
