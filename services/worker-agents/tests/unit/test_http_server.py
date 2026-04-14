"""
Testes unitários para HTTP Server - health endpoints.

Testa os endpoints /health, /ready e /health/startup para Kubernetes probes.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Mock neural_hive_observability antes de importar o módulo
mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock()
sys.modules["neural_hive_observability"] = mock_tracer_module

from api.http_server import create_http_server  # noqa: E402


class MockConfig:
    """Config mock para testes."""

    def __init__(self):
        self.agent_id = "test-worker-agent-001"
        self.http_port = 8000
        self.supported_task_types = ["query", "transform", "execute"]
        self.max_concurrent_tasks = 10
        self.namespace = "test"
        self.cluster = "test-cluster"
        self.service_version = "1.0.0-test"
        self.vault_enabled = False
        self.vault_fail_open = False
        self.spiffe_enabled = False
        self.spiffe_fallback_allowed = False
        self.spiffe_trust_domain = "neural-hive.local"
        self.scheduler_enable_preemption = False


class MockRegistryClient:
    """Registry client mock para testes."""

    def __init__(self, registered=True):
        self._registered = registered

    def is_registered(self):
        return self._registered


class MockExecutionEngine:
    """Execution engine mock para testes."""

    def __init__(self, active_tasks_count=0):
        self.active_tasks = {}


@pytest.fixture
def mock_config():
    """Fixture para config mock."""
    return MockConfig()


@pytest.fixture
def app_state():
    """Fixture para app_state."""
    registry = MockRegistryClient(registered=True)
    engine = MockExecutionEngine(active_tasks_count=0)
    return {"registry_client": registry, "execution_engine": engine}


@pytest.fixture
def client(mock_config, app_state):
    """Fixture para TestClient."""
    app = create_http_server(mock_config, app_state)
    return TestClient(app)


class TestHealthEndpoint:
    """Testes para /health (liveness probe)."""

    def test_health_returns_200(self, client):
        """Verifica que /health retorna 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_has_status_field(self, client):
        """Verifica que /health retorna campo status."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "unhealthy"]

    def test_health_has_agent_id(self, client):
        """Verifica que /health retorna agent_id."""
        response = client.get("/health")
        data = response.json()
        assert "agent_id" in data
        assert data["agent_id"] == "test-worker-agent-001"

    def test_health_has_timestamp(self, client):
        """Verifica que /health retorna timestamp."""
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], int)

    def test_health_has_vault_checks(self, client):
        """Verifica que /health retorna checks do vault."""
        response = client.get("/health")
        data = response.json()
        assert "checks" in data
        assert "vault" in data["checks"]
        assert data["checks"]["vault"]["enabled"] is False
        assert data["checks"]["vault"]["status"] == "disabled"


class TestReadyEndpoint:
    """Testes para /ready (readiness probe)."""

    def test_ready_returns_200_when_registered(self, client):
        """Verifica que /ready retorna 200 quando registrado."""
        response = client.get("/ready")
        assert response.status_code == 200

    def test_ready_has_ready_field(self, client):
        """Verifica que /ready retorna campo ready."""
        response = client.get("/ready")
        data = response.json()
        assert "ready" in data
        assert data["ready"] is True

    def test_ready_has_checks(self, client):
        """Verifica que /ready retorna checks."""
        response = client.get("/ready")
        data = response.json()
        assert "checks" in data
        assert "registered" in data["checks"]
        assert "active_tasks" in data["checks"]
        assert "max_concurrent" in data["checks"]

    def test_ready_returns_503_when_not_registered(self, mock_config):
        """Verifica que /ready retorna 503 quando não registrado."""
        registry = MockRegistryClient(registered=False)
        engine = MockExecutionEngine(active_tasks_count=0)
        app_state = {"registry_client": registry, "execution_engine": engine}

        app = create_http_server(mock_config, app_state)
        client = TestClient(app)

        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False


class TestStartupEndpoint:
    """Testes para /health/startup (startup probe)."""

    def test_startup_returns_200(self, client):
        """Verifica que /health/startup retorna 200."""
        response = client.get("/health/startup")
        assert response.status_code == 200

    def test_startup_has_status_field(self, client):
        """Verifica que /health/startup retorna status='started'."""
        response = client.get("/health/startup")
        data = response.json()
        assert "status" in data
        assert data["status"] == "started"

    def test_startup_has_agent_id(self, client):
        """Verifica que /health/startup retorna agent_id."""
        response = client.get("/health/startup")
        data = response.json()
        assert "agent_id" in data
        assert data["agent_id"] == "test-worker-agent-001"

    def test_startup_has_timestamp(self, client):
        """Verifica que /health/startup retorna timestamp."""
        response = client.get("/health/startup")
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], int)

    def test_startup_has_started_at_iso_format(self, client):
        """Verifica que /health/startup retorna started_at em formato ISO."""
        response = client.get("/health/startup")
        data = response.json()
        assert "started_at" in data

        # Verificar que started_at é parseável como ISO datetime
        try:
            datetime.fromisoformat(data["started_at"])
        except ValueError:
            pytest.fail(f"started_at não é um datetime ISO válido: {data['started_at']}")

    def test_startup_started_at_has_utc_timezone(self, client):
        """Verifica que started_at está em UTC."""
        response = client.get("/health/startup")
        data = response.json()

        # Parsear o datetime e verificar se tem timezone info
        started_at = datetime.fromisoformat(data["started_at"])
        # Se o timezone for UTC, o offset deve ser 0
        if started_at.tzinfo is not None:
            assert started_at.utcoffset().total_seconds() == 0


class TestStartupVsReadiness:
    """Testes comparativos entre /health/startup e /ready."""

    def test_startup_and_ready_are_different_endpoints(self, client):
        """Verifica que /health/startup e /ready são endpoints diferentes."""
        startup_response = client.get("/health/startup")
        ready_response = client.get("/ready")

        # Ambos devem retornar 200
        assert startup_response.status_code == 200
        assert ready_response.status_code == 200

        # Estruturas diferentes
        startup_data = startup_response.json()
        ready_data = ready_response.json()

        # Startup tem "status", Ready tem "ready"
        assert "status" in startup_data
        assert "ready" in ready_data

        # Startup não deve ter "ready"
        assert "ready" not in startup_data

        # Ready não deve ter "started_at"
        assert "started_at" not in ready_data

    def test_startup_always_returns_200_regardless_of_registration(self, mock_config):
        """Verifica que /health/startup sempre retorna 200, mesmo se não registrado."""
        registry = MockRegistryClient(registered=False)
        engine = MockExecutionEngine(active_tasks_count=0)
        app_state = {"registry_client": registry, "execution_engine": engine}

        app = create_http_server(mock_config, app_state)
        client = TestClient(app)

        # /ready deve falhar (503) quando não registrado
        ready_response = client.get("/ready")
        assert ready_response.status_code == 503

        # /health/startup deve sempre funcionar (200)
        startup_response = client.get("/health/startup")
        assert startup_response.status_code == 200
        assert startup_response.json()["status"] == "started"
