"""
Pytest configuration and shared fixtures for service-registry tests.
"""

import pytest
import sys
import os
from uuid import uuid4
from unittest.mock import Mock, AsyncMock

# Adicionar src ao path para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))


@pytest.fixture
def mock_grpc_context():
    """Mock basico para gRPC context"""
    context = Mock()
    context.abort = Mock()
    context.invocation_metadata = Mock(return_value=[])
    return context


@pytest.fixture
def mock_agent_info():
    """Cria AgentInfo de teste"""
    from models.agent import AgentInfo, AgentType, AgentStatus, AgentTelemetry

    return AgentInfo(
        agent_id=uuid4(),
        agent_type=AgentType.WORKER,
        capabilities=["python", "terraform"],
        metadata={"version": "1.0.0"},
        status=AgentStatus.HEALTHY,
        telemetry=AgentTelemetry(
            success_rate=0.95,
            avg_duration_ms=100,
            total_executions=50,
            failed_executions=2
        ),
        namespace="default",
        cluster="local",
        version="1.0.0"
    )


@pytest.fixture
def mock_registry_service():
    """Mock do RegistryService"""
    service = AsyncMock()
    service.register_agent = AsyncMock(return_value=("agent-123", "token-456"))
    service.list_agents = AsyncMock(return_value=[])
    service.get_agent = AsyncMock(return_value=None)
    service.deregister_agent = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_matching_engine():
    """Mock do MatchingEngine"""
    engine = AsyncMock()
    engine.match_agents = AsyncMock(return_value=[])
    return engine


@pytest.fixture
def mock_etcd_client():
    """Mock do EtcdClient"""
    client = AsyncMock()
    client.list_agents = AsyncMock(return_value=[])
    client.get_agent = AsyncMock(return_value=None)
    client.save_agent = AsyncMock()
    client.delete_agent = AsyncMock()
    return client


@pytest.fixture
def mock_pheromone_client():
    """Mock do PheromoneClient"""
    client = AsyncMock()
    client.get_agent_pheromone_score = AsyncMock(return_value=0.8)
    return client
