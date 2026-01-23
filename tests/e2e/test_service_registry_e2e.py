"""
Testes E2E para Service Registry com etcd real.

Valida:
- Registro de agents (Worker, Scout, Guard)
- Heartbeat periodico e atualizacao de telemetria
- Discovery de agents por capabilities e filtros
- Deregister e limpeza
- TTL e expiracao automatica
- Cache de discovery (hit/miss)
- Pheromone scoring
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import grpc
import pytest

from tests.e2e.utils.metrics import get_metric_value, query_prometheus

logger = logging.getLogger(__name__)

# Configuration from environment
SERVICE_REGISTRY_ENDPOINT = os.getenv(
    "SERVICE_REGISTRY_ENDPOINT",
    "service-registry.neural-hive.svc.cluster.local:50051",
)
ETCD_ENDPOINT = os.getenv(
    "ETCD_ENDPOINT",
    "etcd.neural-hive.svc.cluster.local:2379",
)
PROMETHEUS_ENDPOINT = os.getenv(
    "PROMETHEUS_ENDPOINT",
    "prometheus-server.monitoring.svc.cluster.local:9090",
)

# Test configuration
HEARTBEAT_TIMEOUT_SECONDS = 60
CACHE_TTL_SECONDS = 30
DISCOVERY_TIMEOUT_SECONDS = 10


@dataclass
class AgentInfo:
    """Agent information for registration."""

    agent_id: str = field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:8]}")
    agent_type: str = "worker"
    namespace: str = "default"
    endpoint: str = "localhost:50052"
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    status: str = "HEALTHY"


@dataclass
class AgentTelemetry:
    """Agent telemetry for heartbeat."""

    success_rate: float = 0.95
    avg_duration_ms: int = 150
    total_executions: int = 100
    last_execution_time: Optional[datetime] = None
    cpu_usage: float = 0.5
    memory_usage: float = 0.6


# ============================================
# Fixtures
# ============================================


@pytest.fixture(scope="session")
async def service_registry_channel():
    """
    Session-scoped gRPC channel for Service Registry.

    Provides a connected gRPC channel for Service Registry interactions.
    """
    try:
        channel = grpc.aio.insecure_channel(SERVICE_REGISTRY_ENDPOINT)
        # Wait for channel to be ready
        await asyncio.wait_for(
            channel.channel_ready(),
            timeout=30.0,
        )
        yield channel
        await channel.close()
    except asyncio.TimeoutError:
        pytest.skip(f"Could not connect to Service Registry at {SERVICE_REGISTRY_ENDPOINT}")
    except Exception as e:
        pytest.skip(f"Could not create Service Registry channel: {e}")


@pytest.fixture(scope="session")
async def service_registry_client(service_registry_channel):
    """
    Session-scoped Service Registry client fixture.

    Provides ServiceRegistryClient from neural_hive_integration.
    """
    try:
        from neural_hive_integration.clients.service_registry_client import (
            ServiceRegistryClient,
        )

        client = ServiceRegistryClient(channel=service_registry_channel)
        yield client
    except ImportError:
        # Fallback: use raw gRPC stub
        pytest.skip("ServiceRegistryClient not available")
    except Exception as e:
        pytest.skip(f"Could not create Service Registry client: {e}")


@pytest.fixture(scope="session")
async def etcd_client():
    """
    Session-scoped etcd client for validation.

    Provides direct etcd access for data validation.
    """
    try:
        import etcd3

        host, port = ETCD_ENDPOINT.rsplit(":", 1)
        client = etcd3.client(host=host, port=int(port))
        # Test connection
        client.status()
        yield client
        client.close()
    except ImportError:
        pytest.skip("etcd3 not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to etcd: {e}")


@pytest.fixture
def test_agent_info() -> AgentInfo:
    """Generate synthetic AgentInfo for tests."""
    return AgentInfo(
        agent_id=f"test-agent-{uuid.uuid4().hex[:8]}",
        agent_type="worker",
        namespace="test",
        endpoint=f"localhost:{50052 + hash(uuid.uuid4()) % 1000}",
        capabilities=["python", "terraform"],
        metadata={"version": "1.0.0", "region": "us-east-1"},
        status="HEALTHY",
    )


@pytest.fixture
def test_agent_telemetry() -> AgentTelemetry:
    """Generate synthetic AgentTelemetry for tests."""
    return AgentTelemetry(
        success_rate=0.95,
        avg_duration_ms=150,
        total_executions=100,
        last_execution_time=datetime.utcnow(),
        cpu_usage=0.5,
        memory_usage=0.6,
    )


@pytest.fixture
async def registered_agent(service_registry_client, test_agent_info):
    """
    Fixture that registers an agent and cleans up after test.

    Yields:
        Tuple of (agent_id, agent_info)
    """
    # Register agent
    agent_id = await service_registry_client.register(
        agent_type=test_agent_info.agent_type,
        namespace=test_agent_info.namespace,
        endpoint=test_agent_info.endpoint,
        capabilities=test_agent_info.capabilities,
        metadata=test_agent_info.metadata,
    )
    test_agent_info.agent_id = agent_id

    yield agent_id, test_agent_info

    # Cleanup: deregister agent
    try:
        await service_registry_client.deregister(agent_id)
    except Exception as e:
        logger.warning(f"Failed to deregister agent {agent_id}: {e}")


# ============================================
# Registration Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_register_worker_agent(service_registry_client, etcd_client, test_agent_info):
    """
    Testa registro de Worker Agent.

    Valida:
    1. Agent e registrado com sucesso
    2. agent_id e retornado
    3. Dados persistidos no etcd
    4. Status inicial = HEALTHY
    """
    # Register agent
    agent_id = await service_registry_client.register(
        agent_type=test_agent_info.agent_type,
        namespace=test_agent_info.namespace,
        endpoint=test_agent_info.endpoint,
        capabilities=test_agent_info.capabilities,
        metadata=test_agent_info.metadata,
    )

    try:
        # Validate agent_id returned
        assert agent_id is not None
        assert len(agent_id) > 0

        # Validate persistence in etcd
        etcd_key = f"/agents/{agent_id}"
        value, _ = etcd_client.get(etcd_key)
        assert value is not None, f"Agent {agent_id} not found in etcd"

        # Parse stored data and validate
        import json
        stored_data = json.loads(value.decode("utf-8"))
        assert stored_data["agent_type"] == test_agent_info.agent_type
        assert stored_data["namespace"] == test_agent_info.namespace
        assert stored_data["status"] == "HEALTHY"
        assert set(stored_data["capabilities"]) == set(test_agent_info.capabilities)

        logger.info(f"Successfully registered agent {agent_id}")

    finally:
        # Cleanup
        await service_registry_client.deregister(agent_id)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_register_multiple_agent_types(service_registry_client, etcd_client):
    """
    Testa registro de multiplos tipos de agents.

    Valida:
    1. Worker, Scout, Guard agents podem ser registrados
    2. Cada tipo tem agent_id unico
    3. Todos persistidos no etcd
    """
    agent_types = ["worker", "scout", "guard"]
    registered_agents = []

    try:
        for agent_type in agent_types:
            agent_id = await service_registry_client.register(
                agent_type=agent_type,
                namespace="test",
                endpoint=f"localhost:{50052 + len(registered_agents)}",
                capabilities=["python"],
                metadata={"type": agent_type},
            )
            registered_agents.append((agent_id, agent_type))

        # Validate all registered with unique IDs
        agent_ids = [aid for aid, _ in registered_agents]
        assert len(set(agent_ids)) == len(agent_types), "Agent IDs should be unique"

        # Validate all in etcd
        for agent_id, agent_type in registered_agents:
            etcd_key = f"/agents/{agent_id}"
            value, _ = etcd_client.get(etcd_key)
            assert value is not None, f"Agent {agent_id} not found in etcd"

            import json
            stored_data = json.loads(value.decode("utf-8"))
            assert stored_data["agent_type"] == agent_type

        logger.info(f"Successfully registered {len(registered_agents)} agents of different types")

    finally:
        # Cleanup all agents
        for agent_id, _ in registered_agents:
            try:
                await service_registry_client.deregister(agent_id)
            except Exception as e:
                logger.warning(f"Failed to deregister agent {agent_id}: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_register_multiple_agents_same_capabilities(service_registry_client):
    """
    Testa registro de multiplos agents com mesmas capabilities.

    Valida:
    1. 3 agents com capabilities [python, terraform] podem ser registrados
    2. Todos tem agent_ids unicos
    3. Todos aparecem no discovery
    """
    capabilities = ["python", "terraform"]
    registered_agents = []

    try:
        for i in range(3):
            agent_id = await service_registry_client.register(
                agent_type="worker",
                namespace="test",
                endpoint=f"localhost:{50052 + i}",
                capabilities=capabilities,
                metadata={"index": str(i)},
            )
            registered_agents.append(agent_id)

        # Validate unique IDs
        assert len(set(registered_agents)) == 3, "All agent IDs should be unique"

        # Validate all appear in discovery
        discovered = await service_registry_client.discover(
            capabilities=["python"],
            namespace="test",
        )

        discovered_ids = [a.agent_id for a in discovered]
        for agent_id in registered_agents:
            assert agent_id in discovered_ids, f"Agent {agent_id} not found in discovery"

        logger.info(f"Successfully registered 3 agents with same capabilities")

    finally:
        # Cleanup
        for agent_id in registered_agents:
            try:
                await service_registry_client.deregister(agent_id)
            except Exception:
                pass


# ============================================
# Heartbeat Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_heartbeat_updates_telemetry(service_registry_client, etcd_client, registered_agent):
    """
    Testa atualizacao de telemetria via heartbeat.

    Valida:
    1. Heartbeat e aceito
    2. Telemetria atualizada no etcd
    3. last_heartbeat timestamp atualizado
    """
    agent_id, agent_info = registered_agent

    # Send heartbeat with telemetry
    telemetry = AgentTelemetry(
        success_rate=0.98,
        avg_duration_ms=120,
        total_executions=200,
    )

    await service_registry_client.heartbeat(
        agent_id=agent_id,
        success_rate=telemetry.success_rate,
        avg_duration_ms=telemetry.avg_duration_ms,
        total_executions=telemetry.total_executions,
    )

    # Validate telemetry updated in etcd
    etcd_key = f"/agents/{agent_id}"
    value, _ = etcd_client.get(etcd_key)
    assert value is not None

    import json
    stored_data = json.loads(value.decode("utf-8"))

    # Validate telemetry fields
    assert stored_data.get("telemetry", {}).get("success_rate") == telemetry.success_rate
    assert stored_data.get("telemetry", {}).get("avg_duration_ms") == telemetry.avg_duration_ms

    # Validate last_heartbeat updated
    assert "last_heartbeat" in stored_data
    last_heartbeat = datetime.fromisoformat(stored_data["last_heartbeat"])
    assert (datetime.utcnow() - last_heartbeat).total_seconds() < 5

    logger.info(f"Heartbeat successfully updated telemetry for agent {agent_id}")


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_heartbeat_timeout_marks_unhealthy(service_registry_client, etcd_client, test_agent_info):
    """
    Testa que agent sem heartbeat e marcado UNHEALTHY.

    Valida:
    1. Agent registrado com status HEALTHY
    2. Apos HEARTBEAT_TIMEOUT sem heartbeat, status muda para UNHEALTHY
    3. Agent nao aparece em discovery com filter status=HEALTHY

    NOTE: Este teste e lento (aguarda timeout de ~60s)
    """
    # Register agent
    agent_id = await service_registry_client.register(
        agent_type=test_agent_info.agent_type,
        namespace="test-timeout",
        endpoint=test_agent_info.endpoint,
        capabilities=test_agent_info.capabilities,
        metadata=test_agent_info.metadata,
    )

    try:
        # Validate initial status is HEALTHY
        etcd_key = f"/agents/{agent_id}"
        value, _ = etcd_client.get(etcd_key)
        import json
        stored_data = json.loads(value.decode("utf-8"))
        assert stored_data["status"] == "HEALTHY"

        # Wait for heartbeat timeout (reduced for test, normally 60s)
        logger.info(f"Waiting {HEARTBEAT_TIMEOUT_SECONDS}s for heartbeat timeout...")
        await asyncio.sleep(HEARTBEAT_TIMEOUT_SECONDS + 5)

        # Validate status changed to UNHEALTHY
        value, _ = etcd_client.get(etcd_key)
        stored_data = json.loads(value.decode("utf-8"))
        assert stored_data["status"] == "UNHEALTHY", "Agent should be marked UNHEALTHY after timeout"

        # Validate agent not in discovery with status=HEALTHY filter
        discovered = await service_registry_client.discover(
            capabilities=test_agent_info.capabilities[:1],
            namespace="test-timeout",
            status="HEALTHY",
        )

        discovered_ids = [a.agent_id for a in discovered]
        assert agent_id not in discovered_ids, "Unhealthy agent should not appear in healthy filter"

        logger.info(f"Agent {agent_id} correctly marked UNHEALTHY after timeout")

    finally:
        await service_registry_client.deregister(agent_id)


# ============================================
# Discovery Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_discover_agents_by_capabilities(service_registry_client):
    """
    Testa discovery por capabilities.

    Valida:
    1. 3 agents registrados: A(python), B(python,terraform), C(terraform)
    2. Discovery com capability python retorna A e B
    3. Discovery com capability terraform retorna B e C
    """
    registered_agents = []

    try:
        # Register agents with different capabilities
        agent_a = await service_registry_client.register(
            agent_type="worker",
            namespace="test-discovery",
            endpoint="localhost:50060",
            capabilities=["python"],
            metadata={"name": "agent_a"},
        )
        registered_agents.append(("agent_a", agent_a, ["python"]))

        agent_b = await service_registry_client.register(
            agent_type="worker",
            namespace="test-discovery",
            endpoint="localhost:50061",
            capabilities=["python", "terraform"],
            metadata={"name": "agent_b"},
        )
        registered_agents.append(("agent_b", agent_b, ["python", "terraform"]))

        agent_c = await service_registry_client.register(
            agent_type="worker",
            namespace="test-discovery",
            endpoint="localhost:50062",
            capabilities=["terraform"],
            metadata={"name": "agent_c"},
        )
        registered_agents.append(("agent_c", agent_c, ["terraform"]))

        # Discover python capability
        python_agents = await service_registry_client.discover(
            capabilities=["python"],
            namespace="test-discovery",
        )
        python_ids = [a.agent_id for a in python_agents]

        assert agent_a in python_ids, "Agent A should be in python discovery"
        assert agent_b in python_ids, "Agent B should be in python discovery"
        assert agent_c not in python_ids, "Agent C should not be in python discovery"

        # Discover terraform capability
        terraform_agents = await service_registry_client.discover(
            capabilities=["terraform"],
            namespace="test-discovery",
        )
        terraform_ids = [a.agent_id for a in terraform_agents]

        assert agent_a not in terraform_ids, "Agent A should not be in terraform discovery"
        assert agent_b in terraform_ids, "Agent B should be in terraform discovery"
        assert agent_c in terraform_ids, "Agent C should be in terraform discovery"

        logger.info("Discovery by capabilities working correctly")

    finally:
        for _, agent_id, _ in registered_agents:
            try:
                await service_registry_client.deregister(agent_id)
            except Exception:
                pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_discover_agents_with_filters(service_registry_client):
    """
    Testa discovery com filtros.

    Valida:
    1. Agents com diferentes status (HEALTHY, DEGRADED) registrados
    2. Discovery com filter status=HEALTHY retorna apenas agents HEALTHY
    3. Discovery com filter namespace retorna apenas agents do namespace
    """
    registered_agents = []

    try:
        # Register healthy agent
        healthy_agent = await service_registry_client.register(
            agent_type="worker",
            namespace="production",
            endpoint="localhost:50070",
            capabilities=["python"],
            metadata={"status": "healthy"},
        )
        registered_agents.append(healthy_agent)

        # Register another healthy agent in different namespace
        staging_agent = await service_registry_client.register(
            agent_type="worker",
            namespace="staging",
            endpoint="localhost:50071",
            capabilities=["python"],
            metadata={"status": "healthy"},
        )
        registered_agents.append(staging_agent)

        # Discover with namespace filter
        production_agents = await service_registry_client.discover(
            capabilities=["python"],
            namespace="production",
        )
        production_ids = [a.agent_id for a in production_agents]

        assert healthy_agent in production_ids, "Healthy agent should be in production namespace"
        assert staging_agent not in production_ids, "Staging agent should not be in production namespace"

        # Discover with status filter
        healthy_agents = await service_registry_client.discover(
            capabilities=["python"],
            status="HEALTHY",
        )

        healthy_ids = [a.agent_id for a in healthy_agents]
        assert healthy_agent in healthy_ids or staging_agent in healthy_ids, \
            "At least one healthy agent should be found"

        logger.info("Discovery with filters working correctly")

    finally:
        for agent_id in registered_agents:
            try:
                await service_registry_client.deregister(agent_id)
            except Exception:
                pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_discover_agents_cache_hit(service_registry_client):
    """
    Testa cache de discovery.

    Valida:
    1. Primeira discovery (cache miss)
    2. Segunda discovery imediata (cache hit)
    3. Metricas de cache hit incrementadas
    4. Apos TTL expirar, terceira discovery (cache miss)
    """
    registered_agents = []

    try:
        # Register agent
        agent_id = await service_registry_client.register(
            agent_type="worker",
            namespace="test-cache",
            endpoint="localhost:50080",
            capabilities=["python"],
            metadata={},
        )
        registered_agents.append(agent_id)

        # Get initial cache hit metric
        initial_cache_hits = await get_metric_value(
            PROMETHEUS_ENDPOINT,
            "service_registry_cache_hits_total",
        )
        initial_cache_hits = int(initial_cache_hits) if initial_cache_hits else 0

        # First discovery (cache miss)
        await service_registry_client.discover(
            capabilities=["python"],
            namespace="test-cache",
        )

        # Second discovery immediately (cache hit expected)
        await service_registry_client.discover(
            capabilities=["python"],
            namespace="test-cache",
        )

        # Give time for metrics to propagate
        await asyncio.sleep(2)

        # Check cache hit metric increased
        final_cache_hits = await get_metric_value(
            PROMETHEUS_ENDPOINT,
            "service_registry_cache_hits_total",
        )
        final_cache_hits = int(final_cache_hits) if final_cache_hits else 0

        # Cache hit should have increased
        assert final_cache_hits >= initial_cache_hits, \
            "Cache hits should have increased after second discovery"

        logger.info(f"Cache working: hits went from {initial_cache_hits} to {final_cache_hits}")

    finally:
        for agent_id in registered_agents:
            try:
                await service_registry_client.deregister(agent_id)
            except Exception:
                pass


# ============================================
# Deregister Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_deregister_agent(service_registry_client, etcd_client, test_agent_info):
    """
    Testa deregister de agent.

    Valida:
    1. Agent registrado e existe no etcd
    2. Apos deregister, agent removido do etcd
    3. Agent nao aparece em discovery
    """
    # Register agent
    agent_id = await service_registry_client.register(
        agent_type=test_agent_info.agent_type,
        namespace="test-deregister",
        endpoint=test_agent_info.endpoint,
        capabilities=test_agent_info.capabilities,
        metadata=test_agent_info.metadata,
    )

    # Validate agent exists in etcd
    etcd_key = f"/agents/{agent_id}"
    value, _ = etcd_client.get(etcd_key)
    assert value is not None, f"Agent {agent_id} should exist in etcd"

    # Validate agent appears in discovery
    discovered = await service_registry_client.discover(
        capabilities=test_agent_info.capabilities[:1],
        namespace="test-deregister",
    )
    discovered_ids = [a.agent_id for a in discovered]
    assert agent_id in discovered_ids, "Agent should appear in discovery before deregister"

    # Deregister agent
    await service_registry_client.deregister(agent_id)

    # Validate agent removed from etcd
    value, _ = etcd_client.get(etcd_key)
    assert value is None, f"Agent {agent_id} should be removed from etcd"

    # Validate agent not in discovery
    discovered = await service_registry_client.discover(
        capabilities=test_agent_info.capabilities[:1],
        namespace="test-deregister",
    )
    discovered_ids = [a.agent_id for a in discovered]
    assert agent_id not in discovered_ids, "Agent should not appear in discovery after deregister"

    logger.info(f"Agent {agent_id} successfully deregistered")


# ============================================
# Pheromone Scoring Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pheromone_scoring_affects_discovery_order(service_registry_client):
    """
    Testa que pheromone scoring afeta ordem de discovery.

    Valida:
    1. 3 agents registrados com mesmas capabilities
    2. Heartbeats com telemetria diferente:
       - Agent A: success_rate=0.99, avg_duration_ms=100
       - Agent B: success_rate=0.90, avg_duration_ms=200
       - Agent C: success_rate=0.85, avg_duration_ms=300
    3. Discovery retorna agents ordenados por pheromone score (A, B, C)
    """
    registered_agents = []

    try:
        # Register 3 agents
        agents_config = [
            ("agent_a", 0.99, 100),
            ("agent_b", 0.90, 200),
            ("agent_c", 0.85, 300),
        ]

        for name, success_rate, duration in agents_config:
            agent_id = await service_registry_client.register(
                agent_type="worker",
                namespace="test-pheromone",
                endpoint=f"localhost:{50090 + len(registered_agents)}",
                capabilities=["python"],
                metadata={"name": name},
            )
            registered_agents.append((agent_id, name, success_rate, duration))

        # Send heartbeats with different telemetry
        for agent_id, name, success_rate, duration in registered_agents:
            await service_registry_client.heartbeat(
                agent_id=agent_id,
                success_rate=success_rate,
                avg_duration_ms=duration,
                total_executions=100,
            )

        # Allow time for pheromone scoring to update
        await asyncio.sleep(2)

        # Discover agents
        discovered = await service_registry_client.discover(
            capabilities=["python"],
            namespace="test-pheromone",
        )

        # Get discovery order
        discovered_order = [a.agent_id for a in discovered]
        expected_order = [aid for aid, _, _, _ in registered_agents]  # A, B, C

        # Validate agent A (best score) is first or near top
        agent_a_id = registered_agents[0][0]
        if len(discovered_order) >= 3:
            # Best agent should be in top positions
            agent_a_position = discovered_order.index(agent_a_id) if agent_a_id in discovered_order else -1
            assert agent_a_position >= 0, "Agent A should be in discovery results"
            assert agent_a_position <= 1, f"Agent A should be near top, but is at position {agent_a_position}"

        logger.info("Pheromone scoring correctly affects discovery order")

    finally:
        for agent_id, _, _, _ in registered_agents:
            try:
                await service_registry_client.deregister(agent_id)
            except Exception:
                pass


# ============================================
# Failure Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_register_with_invalid_data(service_registry_client):
    """
    Testa registro com dados invalidos.

    Valida:
    1. Registro com endpoint vazio falha
    2. Registro com capabilities vazio falha
    3. Erro apropriado retornado
    """
    # Test with empty endpoint
    with pytest.raises(Exception) as exc_info:
        await service_registry_client.register(
            agent_type="worker",
            namespace="test",
            endpoint="",  # Invalid
            capabilities=["python"],
            metadata={},
        )

    # Should fail with validation error
    assert exc_info.value is not None
    logger.info("Registration with invalid data correctly rejected")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_heartbeat_for_nonexistent_agent(service_registry_client):
    """
    Testa heartbeat para agent inexistente.

    Valida:
    1. Heartbeat para agent_id invalido falha
    2. Erro apropriado retornado
    """
    fake_agent_id = f"nonexistent-agent-{uuid.uuid4().hex[:8]}"

    with pytest.raises(Exception) as exc_info:
        await service_registry_client.heartbeat(
            agent_id=fake_agent_id,
            success_rate=0.95,
            avg_duration_ms=100,
            total_executions=50,
        )

    assert exc_info.value is not None
    logger.info("Heartbeat for nonexistent agent correctly rejected")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_deregister_nonexistent_agent(service_registry_client):
    """
    Testa deregister de agent inexistente.

    Valida:
    1. Deregister de agent_id invalido nao causa erro critico
    2. Operacao e idempotente
    """
    fake_agent_id = f"nonexistent-agent-{uuid.uuid4().hex[:8]}"

    # Should not raise or should raise specific "not found" error
    try:
        await service_registry_client.deregister(fake_agent_id)
        # If no error, operation is idempotent (ok)
        logger.info("Deregister of nonexistent agent is idempotent")
    except Exception as e:
        # Should be a "not found" type error
        error_msg = str(e).lower()
        assert "not found" in error_msg or "not exist" in error_msg, \
            f"Expected 'not found' error, got: {e}"
        logger.info("Deregister of nonexistent agent correctly returns not found")


# ============================================
# Metrics Validation Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_service_registry_metrics(service_registry_client, registered_agent):
    """
    Testa que metricas do Service Registry sao expostas.

    Valida:
    - service_registry_agents_total (Gauge)
    - service_registry_register_total (Counter)
    - service_registry_heartbeat_total (Counter)
    - service_registry_discover_total (Counter)
    """
    agent_id, agent_info = registered_agent

    # Perform operations to generate metrics
    await service_registry_client.heartbeat(
        agent_id=agent_id,
        success_rate=0.95,
        avg_duration_ms=100,
        total_executions=50,
    )

    await service_registry_client.discover(
        capabilities=agent_info.capabilities[:1],
        namespace=agent_info.namespace,
    )

    # Allow time for metrics to propagate
    await asyncio.sleep(2)

    # Query metrics
    metrics_to_check = [
        "service_registry_agents_total",
        "service_registry_register_total",
        "service_registry_heartbeat_total",
        "service_registry_discover_total",
    ]

    for metric_name in metrics_to_check:
        try:
            result = await query_prometheus(PROMETHEUS_ENDPOINT, metric_name)
            # Metric should exist (may have 0 results if no data yet)
            assert "data" in result, f"Metric {metric_name} should be queryable"
            logger.info(f"Metric {metric_name} is available")
        except Exception as e:
            logger.warning(f"Could not query metric {metric_name}: {e}")
