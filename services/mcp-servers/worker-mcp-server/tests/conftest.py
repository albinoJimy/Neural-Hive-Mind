"""Worker MCP Server - Tests configuration."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import Response as HTTPXResponse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Add shared module path (do contexto pai services/mcp-servers/)
shared_path = str(Path(__file__).parent.parent.parent.parent / "shared")
if Path(shared_path).exists():
    sys.path.insert(0, shared_path)


@pytest.fixture
def mock_settings():
    """Fixture para configurações de teste."""
    from worker_mcp_server.config.settings import WorkerMCPServerSettings

    return WorkerMCPServerSettings(
        service_name="worker-mcp-server-test",
        service_version="1.0.0",
        log_level="DEBUG",
        port=3013,
        worker_agent_host="localhost",
        worker_agent_port=8005,
        orchestrator_host="localhost",
        orchestrator_port=8003,
        service_registry_host="localhost",
        service_registry_port=8007,
        execution_timeout=300,
    )


@pytest.fixture
def mcp():
    """Fixture para servidor MCP."""
    from worker_mcp_server.server import mcp

    return mcp


@pytest.fixture
def mock_httpx_response(data: dict | None = None, status_code: int = 200):
    """Factory para criar mock de resposta HTTPX."""
    response = Mock(spec=HTTPXResponse)
    response.status_code = status_code
    response.json = Mock(return_value=data or {})
    response.raise_for_status = Mock()
    response.text = str(data) if data else ""
    return response


@pytest.fixture
def mock_worker_agent_exec_response():
    """Mock de resposta de execução do Worker Agent."""
    return {
        "execution_id": "exec-mock-123",
        "status": "pending",
        "task_id": "task-mock-456",
        "workflow_id": "workflow-mock-789",
        "executor_type": "query",
        "parameters": {"query": "SELECT * FROM users"},
        "timestamp": 1713131400000,
    }


@pytest.fixture
def mock_worker_agent_progress_response():
    """Mock de resposta de progresso do Worker Agent."""
    return {
        "execution_id": "exec-mock-123",
        "status": "in_progress",
        "progress_percent": 45,
        "logs": ["Step 1: Query execution started", "Step 2: Fetching data"],
        "started_at": 1713131400000,
        "updated_at": 1713131460000,
    }


@pytest.fixture
def mock_compensation_response():
    """Mock de resposta de compensação."""
    return {
        "success": True,
        "compensation_id": "comp-mock-456",
        "execution_id": "exec-mock-123",
        "original_task_id": "task-mock-456",
        "compensation_type": "rollback",
        "status": "completed",
        "timestamp": 1713131500000,
    }


@pytest.fixture
def async_http_client():
    """Fixture para cliente HTTP async mockado."""
    client = AsyncMock()
    return client


# Autouse fixture para configurar logging estruturado nos testes
@pytest.fixture(autouse=True)
def configure_structlog():
    """Configura logging estruturado para todos os testes."""
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
