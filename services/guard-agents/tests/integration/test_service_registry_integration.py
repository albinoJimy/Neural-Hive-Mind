"""Integration tests for Guard Agent Service Registry client."""
import pytest
import asyncio
import grpc

from src.clients.service_registry_client import ServiceRegistryClient


@pytest.fixture
def service_registry_host():
    """Service Registry host for integration tests."""
    import os
    return os.environ.get("SERVICE_REGISTRY_HOST", "localhost")


@pytest.fixture
def service_registry_port():
    """Service Registry port for integration tests."""
    import os
    return int(os.environ.get("SERVICE_REGISTRY_PORT", "50051"))


@pytest.fixture
async def guard_client(service_registry_host, service_registry_port):
    """Create a Guard Agent Service Registry client for testing."""
    client = ServiceRegistryClient(
        host=service_registry_host,
        port=service_registry_port,
        agent_type="GUARD",
        capabilities=["security", "audit", "policy_enforcement"],
        metadata={"version": "1.0.0", "namespace": "test"}
    )
    yield client
    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_guard_agent(guard_client):
    """Test Guard Agent registration in Service Registry."""
    await guard_client.connect()
    agent_id = await guard_client.register()

    assert agent_id is not None
    assert len(agent_id) > 0
    assert guard_client.agent_id == agent_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_heartbeat_lifecycle(guard_client):
    """Test complete lifecycle: register -> heartbeat -> deregister."""
    await guard_client.connect()
    agent_id = await guard_client.register()
    assert agent_id is not None

    # Start heartbeat
    await guard_client.start_heartbeat()
    # Wait for at least one heartbeat cycle
    await asyncio.sleep(2)

    # Verify client is healthy
    assert guard_client.is_healthy()

    # Close and deregister
    await guard_client.close()
    assert guard_client.channel is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_deregister_guard_agent(guard_client):
    """Test Guard Agent deregistration."""
    await guard_client.connect()
    agent_id = await guard_client.register()
    assert agent_id is not None

    # Deregister
    await guard_client.deregister()

    # Agent ID should still be set but deregistered on server
    # (client doesn't clear agent_id on deregister for logging purposes)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_connect_to_unavailable_registry():
    """Test connection to unavailable Service Registry handles gracefully."""
    client = ServiceRegistryClient(
        host="invalid-host",
        port=99999,
        agent_type="GUARD",
        capabilities=["test"]
    )

    # Connection should be created (lazy connection)
    await client.connect()

    # Registration should fail with gRPC error
    with pytest.raises(Exception):
        await client.register()

    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_capabilities_registration(service_registry_host, service_registry_port):
    """Test registration with multiple capabilities."""
    client = ServiceRegistryClient(
        host=service_registry_host,
        port=service_registry_port,
        agent_type="GUARD",
        capabilities=[
            "security",
            "audit",
            "policy_enforcement",
            "threat_detection",
            "access_control"
        ],
        metadata={
            "version": "2.0.0",
            "namespace": "production",
            "cluster": "neural-hive"
        }
    )

    await client.connect()
    agent_id = await client.register()

    assert agent_id is not None
    assert client.capabilities == [
        "security",
        "audit",
        "policy_enforcement",
        "threat_detection",
        "access_control"
    ]

    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_is_healthy_before_registration(service_registry_host, service_registry_port):
    """Test is_healthy returns False before registration."""
    client = ServiceRegistryClient(
        host=service_registry_host,
        port=service_registry_port,
        agent_type="GUARD",
        capabilities=["test"]
    )

    # Not connected yet
    assert not client.is_healthy()

    await client.connect()
    # Connected but not registered
    assert not client.is_healthy()

    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_is_healthy_after_registration(guard_client):
    """Test is_healthy returns True after successful registration."""
    await guard_client.connect()

    # Not registered yet
    assert not guard_client.is_healthy()

    await guard_client.register()

    # Now should be healthy
    assert guard_client.is_healthy()

    await guard_client.close()
