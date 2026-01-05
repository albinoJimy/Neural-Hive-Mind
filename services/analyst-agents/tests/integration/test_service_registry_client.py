"""Integration tests for Analyst Agent Service Registry client."""
import pytest

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
async def analyst_client(service_registry_host, service_registry_port):
    """Create an Analyst Agent Service Registry client for testing."""
    client = ServiceRegistryClient(host=service_registry_host, port=service_registry_port)
    await client.initialize()
    yield client
    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_analyst_agent(analyst_client):
    """Test Analyst Agent registration."""
    agent_info = {
        'version': '1.2.0',
        'host': 'localhost',
        'port': 8000
    }

    agent_id = await analyst_client.register_agent(agent_info)

    assert agent_id is not None
    assert analyst_client.agent_id == agent_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_heartbeat_updates_health(analyst_client):
    """Test that heartbeat updates health status."""
    agent_info = {'version': '1.0.0'}

    agent_id = await analyst_client.register_agent(agent_info)
    assert agent_id is not None

    # Send heartbeat
    success = await analyst_client.heartbeat()
    assert success is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_health_status(analyst_client):
    """Test health status update."""
    agent_info = {'version': '1.0.0'}

    await analyst_client.register_agent(agent_info)

    # Update health status
    success = await analyst_client.update_health_status('healthy')
    assert success is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_deregister_agent(analyst_client):
    """Test agent deregistration."""
    agent_info = {'version': '1.0.0'}

    await analyst_client.register_agent(agent_info)

    # Deregister
    success = await analyst_client.deregister_agent()
    assert success is True
    assert analyst_client.agent_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_discover_agents(analyst_client):
    """Test agent discovery by capabilities."""
    agent_info = {'version': '1.0.0'}

    # Register agent first
    await analyst_client.register_agent(agent_info)

    # Discover agents with 'analyst' type
    agents = await analyst_client.get_available_agents("analyst")

    # Result may be empty if no matching agents, but should not fail
    assert isinstance(agents, list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_without_initialization():
    """Test that registration fails if client not initialized."""
    client = ServiceRegistryClient(host="localhost", port=50051)
    # Don't call initialize()

    agent_info = {'version': '1.0.0'}
    result = await client.register_agent(agent_info)

    # Should return None since client is not initialized
    assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_heartbeat_without_registration(analyst_client):
    """Test that heartbeat fails if not registered."""
    # Don't register, try heartbeat directly
    success = await analyst_client.heartbeat()

    # Should return False since not registered
    assert success is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_available_agents_without_registration(analyst_client):
    """Test agent discovery works without registration."""
    # Discovery should work even without registration
    agents = await analyst_client.get_available_agents("worker")

    assert isinstance(agents, list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_lifecycle(analyst_client):
    """Test complete agent lifecycle."""
    agent_info = {
        'version': '1.0.0',
        'host': 'localhost',
        'port': 8000,
        'namespace': 'test',
        'cluster': 'neural-hive'
    }

    # Register
    agent_id = await analyst_client.register_agent(agent_info)
    assert agent_id is not None

    # Heartbeat
    success = await analyst_client.heartbeat()
    assert success is True

    # Update health
    success = await analyst_client.update_health_status('healthy')
    assert success is True

    # Discover
    agents = await analyst_client.get_available_agents("analyst")
    assert isinstance(agents, list)

    # Deregister
    success = await analyst_client.deregister_agent()
    assert success is True
