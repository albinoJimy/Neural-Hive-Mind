"""
Configuracao de fixtures pytest para testes do MCP Tool Catalog.

Fixtures compartilhadas para:
- Event loop asyncio
- Mock settings
- Mock tools e descriptors
- Mock adapters
- Mock MCP client
- Mock Prometheus metrics
"""

import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType
from src.adapters.base_adapter import ExecutionResult


# ============================================================================
# Event Loop
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assincronos."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Settings Fixtures
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock de configuracoes basicas."""
    settings = MagicMock()
    # GA Settings
    settings.GA_POPULATION_SIZE = 10
    settings.GA_MAX_GENERATIONS = 5
    settings.GA_CROSSOVER_PROB = 0.7
    settings.GA_MUTATION_PROB = 0.2
    settings.GA_TOURNAMENT_SIZE = 3
    settings.GA_CONVERGENCE_THRESHOLD = 0.01
    settings.GA_TIMEOUT_SECONDS = 5
    settings.CACHE_TTL_SECONDS = 60

    # Tool Execution Settings
    settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
    settings.TOOL_RETRY_MAX_ATTEMPTS = 3
    settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10

    # MCP Settings (disabled by default)
    settings.MCP_SERVERS = {}
    settings.MCP_SERVER_TIMEOUT_SECONDS = 30
    settings.MCP_SERVER_MAX_RETRIES = 3
    settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
    settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60

    # MongoDB Settings
    settings.MONGODB_URI = "mongodb://localhost:27017"
    settings.MONGODB_DATABASE = "mcp_tool_catalog_test"

    return settings


@pytest.fixture
def mock_settings_with_mcp(mock_settings):
    """Mock de configuracoes com MCP servers habilitados."""
    mock_settings.MCP_SERVERS = {
        "trivy-001": {
            "url": "http://trivy-mcp:3000",
            "timeout": 30,
            "circuit_breaker_threshold": 5
        },
        "sonarqube-001": {
            "url": "http://sonarqube-mcp:3000",
            "timeout": 30,
            "circuit_breaker_threshold": 5
        },
        "snyk-001": {
            "url": "http://snyk-mcp:3000",
            "timeout": 30,
            "circuit_breaker_threshold": 5
        }
    }
    return mock_settings


# ============================================================================
# Tool Descriptor Fixtures
# ============================================================================

@pytest.fixture
def cli_tool():
    """Ferramenta CLI para testes."""
    return ToolDescriptor(
        tool_id="pytest-001",
        tool_name="pytest",
        category=ToolCategory.VALIDATION,
        version="7.4.0",
        capabilities=["unit-testing", "integration-testing"],
        reputation_score=0.95,
        cost_score=0.0,
        average_execution_time_ms=5000,
        integration_type=IntegrationType.CLI,
        authentication_method="NONE",
        output_format="text"
    )


@pytest.fixture
def rest_tool():
    """Ferramenta REST para testes."""
    return ToolDescriptor(
        tool_id="sonarqube-001",
        tool_name="sonarqube",
        category=ToolCategory.ANALYSIS,
        version="9.9.0",
        capabilities=["code-quality", "security-analysis"],
        reputation_score=0.9,
        cost_score=0.1,
        average_execution_time_ms=30000,
        integration_type=IntegrationType.REST_API,
        authentication_method="BEARER",
        endpoint_url="http://sonarqube:9000/api/analyze",
        output_format="json"
    )


@pytest.fixture
def container_tool():
    """Ferramenta Container para testes."""
    return ToolDescriptor(
        tool_id="trivy-001",
        tool_name="trivy",
        category=ToolCategory.SECURITY,
        version="0.45.0",
        capabilities=["vulnerability-scanning", "sbom"],
        reputation_score=0.92,
        cost_score=0.05,
        average_execution_time_ms=60000,
        integration_type=IntegrationType.CONTAINER,
        authentication_method="NONE",
        output_format="json",
        metadata={"docker_image": "aquasec/trivy:0.45.0"}
    )


@pytest.fixture
def mcp_enabled_tool():
    """Ferramenta com MCP Server habilitado."""
    return ToolDescriptor(
        tool_id="trivy-mcp-001",
        tool_name="trivy-mcp",
        category=ToolCategory.SECURITY,
        version="0.45.0",
        capabilities=["vulnerability-scanning", "container-scanning"],
        reputation_score=0.95,
        cost_score=0.02,
        average_execution_time_ms=45000,
        integration_type=IntegrationType.CONTAINER,
        authentication_method="NONE",
        output_format="json",
        metadata={
            "docker_image": "aquasec/trivy:0.45.0",
            "mcp_server_url": "http://trivy-mcp:3000"
        }
    )


@pytest.fixture
def unhealthy_tool():
    """Ferramenta nao saudavel para testes."""
    return ToolDescriptor(
        tool_id="broken-001",
        tool_name="broken-tool",
        category=ToolCategory.ANALYSIS,
        version="1.0.0",
        capabilities=["test"],
        reputation_score=0.3,
        cost_score=0.5,
        average_execution_time_ms=100000,
        integration_type=IntegrationType.CLI,
        authentication_method="NONE",
        output_format="text",
        metadata={"is_healthy": False}
    )


@pytest.fixture
def benchmark_tools() -> List[ToolDescriptor]:
    """Lista de 10 ferramentas para benchmark."""
    tools = []
    for i in range(10):
        tools.append(ToolDescriptor(
            tool_id=f"bench-tool-{i:03d}",
            tool_name=f"benchmark-tool-{i}",
            category=ToolCategory.ANALYSIS,
            version="1.0.0",
            capabilities=["benchmark", "testing"],
            reputation_score=0.8,
            cost_score=0.1,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.CLI,
            authentication_method="NONE",
            output_format="json"
        ))
    return tools


# ============================================================================
# Execution Result Fixtures
# ============================================================================

@pytest.fixture
def success_result():
    """ExecutionResult de sucesso."""
    return ExecutionResult(
        success=True,
        output="Test passed successfully",
        execution_time_ms=1500.0,
        exit_code=0,
        metadata={"tests_run": 10, "tests_passed": 10}
    )


@pytest.fixture
def failure_result():
    """ExecutionResult de falha."""
    return ExecutionResult(
        success=False,
        output="",
        error="Command failed with exit code 1",
        execution_time_ms=500.0,
        exit_code=1,
        metadata={}
    )


@pytest.fixture
def timeout_result():
    """ExecutionResult de timeout."""
    return ExecutionResult(
        success=False,
        output="",
        error="Execution timed out after 300 seconds",
        execution_time_ms=300000.0,
        exit_code=-1,
        metadata={"timed_out": True}
    )


@pytest.fixture
def fast_result():
    """ExecutionResult rapido para testes de performance."""
    return ExecutionResult(
        success=True,
        output="Quick execution",
        execution_time_ms=10.0,
        exit_code=0
    )


# ============================================================================
# Mock Adapter Fixtures
# ============================================================================

@pytest.fixture
def mock_cli_adapter(success_result):
    """Mock de CLIAdapter."""
    adapter = AsyncMock()
    adapter.execute = AsyncMock(return_value=success_result)
    adapter.validate_tool_availability = AsyncMock(return_value=True)
    adapter.supports_tool = MagicMock(return_value=True)
    adapter.cleanup = AsyncMock()
    return adapter


@pytest.fixture
def mock_rest_adapter(success_result):
    """Mock de RESTAdapter."""
    adapter = AsyncMock()
    adapter.execute = AsyncMock(return_value=success_result)
    adapter.validate_tool_availability = AsyncMock(return_value=True)
    adapter.supports_tool = MagicMock(return_value=True)
    adapter.cleanup = AsyncMock()
    return adapter


@pytest.fixture
def mock_container_adapter(success_result):
    """Mock de ContainerAdapter."""
    adapter = AsyncMock()
    adapter.execute = AsyncMock(return_value=success_result)
    adapter.validate_tool_availability = AsyncMock(return_value=True)
    adapter.supports_tool = MagicMock(return_value=True)
    adapter.cleanup = AsyncMock()
    return adapter


# ============================================================================
# Mock MCP Client Fixtures
# ============================================================================

@pytest.fixture
def mock_mcp_client():
    """Mock de MCPServerClient."""
    client = AsyncMock()
    client.initialize = AsyncMock(return_value={
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "mock-mcp", "version": "1.0.0"},
        "capabilities": {"tools": {"listChanged": True}}
    })
    client.list_tools = AsyncMock(return_value={
        "tools": [
            {
                "name": "trivy-scan",
                "description": "Scan for vulnerabilities",
                "inputSchema": {
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"]
                }
            }
        ]
    })
    client.call_tool = AsyncMock(return_value={
        "content": [{"type": "text", "text": '{"vulnerabilities": []}'}],
        "isError": False
    })
    client.is_connected = True
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_mcp_client_failing():
    """Mock de MCPServerClient que falha."""
    client = AsyncMock()
    client.initialize = AsyncMock(side_effect=Exception("Connection refused"))
    client.list_tools = AsyncMock(side_effect=Exception("Connection refused"))
    client.call_tool = AsyncMock(side_effect=Exception("Connection refused"))
    client.is_connected = False
    client.close = AsyncMock()
    return client


# ============================================================================
# Mock Metrics Fixtures
# ============================================================================

@pytest.fixture
def mock_metrics():
    """Mock de MCPToolCatalogMetrics."""
    metrics = MagicMock()
    metrics.record_selection = MagicMock()
    metrics.record_tool_execution = MagicMock()
    metrics.record_feedback = MagicMock()
    metrics.record_mcp_fallback = MagicMock()
    metrics.record_genetic_algorithm = MagicMock()
    metrics.update_tool_registry = MagicMock()
    metrics.update_mcp_clients_status = MagicMock()

    # Gauges
    metrics.active_tool_selections = MagicMock()
    metrics.active_tool_selections.inc = MagicMock()
    metrics.active_tool_selections.dec = MagicMock()

    return metrics


# ============================================================================
# Mock Tool Registry Fixtures
# ============================================================================

@pytest.fixture
def mock_tool_registry(cli_tool, rest_tool, container_tool):
    """Mock de ToolRegistry com ferramentas pre-carregadas."""
    registry = AsyncMock()
    registry.get_tool = AsyncMock(side_effect=lambda tool_id: {
        "pytest-001": cli_tool,
        "sonarqube-001": rest_tool,
        "trivy-001": container_tool
    }.get(tool_id))
    registry.get_tools_by_category = AsyncMock(return_value=[cli_tool, rest_tool])
    registry.get_all_tools = AsyncMock(return_value=[cli_tool, rest_tool, container_tool])
    registry.update_tool = AsyncMock()
    registry.update_tool_health = AsyncMock()
    registry.update_tool_reputation = AsyncMock()
    return registry


# ============================================================================
# MongoDB Fixtures
# ============================================================================

@pytest.fixture
def mock_mongodb_client():
    """Mock de cliente MongoDB."""
    client = MagicMock()
    db = MagicMock()
    collection = MagicMock()

    # Configure find_one to return None (not found)
    collection.find_one = AsyncMock(return_value=None)
    collection.insert_one = AsyncMock()
    collection.update_one = AsyncMock()
    collection.delete_one = AsyncMock()
    collection.find = MagicMock(return_value=AsyncMock())

    db.__getitem__ = MagicMock(return_value=collection)
    client.__getitem__ = MagicMock(return_value=db)

    return client


# ============================================================================
# Kafka Fixtures
# ============================================================================

@pytest.fixture
def mock_kafka_producer():
    """Mock de produtor Kafka."""
    producer = AsyncMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock()
    return producer


@pytest.fixture
def mock_kafka_consumer():
    """Mock de consumidor Kafka."""
    consumer = AsyncMock()
    consumer.start = AsyncMock()
    consumer.stop = AsyncMock()
    consumer.getmany = AsyncMock(return_value={})
    return consumer


# ============================================================================
# HTTP/AIOHTTP Fixtures
# ============================================================================

@pytest.fixture
def mock_aiohttp_session():
    """Mock de sessao aiohttp."""
    session = AsyncMock()

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"success": True})
    mock_response.text = AsyncMock(return_value='{"success": true}')
    mock_response.headers = {"Content-Type": "application/json"}

    # Context manager
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    session.get = MagicMock(return_value=mock_response)
    session.post = MagicMock(return_value=mock_response)
    session.put = MagicMock(return_value=mock_response)
    session.delete = MagicMock(return_value=mock_response)

    return session


# ============================================================================
# Cache Fixtures
# ============================================================================

@pytest.fixture
def mock_cache():
    """Mock de cache em memoria."""
    cache = {}

    class MockCache:
        async def get(self, key: str) -> Any:
            return cache.get(key)

        async def set(self, key: str, value: Any, ttl: int = 60) -> None:
            cache[key] = value

        async def delete(self, key: str) -> None:
            cache.pop(key, None)

        async def clear(self) -> None:
            cache.clear()

        def __contains__(self, key: str) -> bool:
            return key in cache

    return MockCache()


# ============================================================================
# Context Fixtures
# ============================================================================

@pytest.fixture
def execution_context() -> Dict[str, Any]:
    """Contexto de execucao padrao."""
    return {
        "request_id": "test-request-001",
        "user_id": "test-user",
        "correlation_id": "test-correlation-001",
        "timestamp": "2024-01-15T10:00:00Z",
        "environment": "test"
    }


@pytest.fixture
def execution_params() -> Dict[str, Any]:
    """Parametros de execucao padrao."""
    return {
        "target": ".",
        "output_format": "json",
        "verbose": True,
        "timeout": 300
    }
