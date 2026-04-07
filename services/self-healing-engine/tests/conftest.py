"""
Configuração global de testes para Self-Healing Engine.

Este módulo configura o path para imports e fornece fixtures
para mocks de clientes externos (ETS, Orchestrator, OPA).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from prometheus_client import REGISTRY


# Adicionar diretório src ao path Python
# Isso resolve os erros de import "ModuleNotFoundError: No module named 'src'"
_project_root = Path(__file__).resolve().parents[1]
_src_path = _project_root / "src"

if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


@pytest.fixture(autouse=True)
def clean_prometheus_registry():
    """Limpa o registry do Prometheus entre testes para evitar duplicatas."""
    # Limpar métricas padrão
    for collector in list(REGISTRY._collector_to_names.keys()):
        REGISTRY.unregister(collector)
    yield
    # Limpar novamente após o teste
    for collector in list(REGISTRY._collector_to_names.keys()):
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass


@pytest.fixture
def mock_tracer():
    """Mock do OpenTelemetry tracer."""
    tracer = MagicMock()
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    tracer.start_as_current_span = MagicMock(return_value=span)
    return tracer


@pytest.fixture
def mock_service_registry_client():
    """Mock do Service Registry Client."""
    client = AsyncMock()
    client.get_service_address = AsyncMock(return_value="http://test-service:8080")
    client.health_check = AsyncMock(return_value=True)
    client.initialize = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_execution_ticket_client():
    """Mock do Execution Ticket Service Client."""
    client = AsyncMock()
    client.reallocate_ticket = AsyncMock(return_value={"success": True, "ticket_id": "test-123"})
    client.reallocate_multiple_tickets = AsyncMock(
        return_value={"success": True, "tickets": ["test-123"]}
    )
    client.update_ticket_status = AsyncMock(return_value={"success": True})
    client.get_ticket = AsyncMock(return_value={"ticket_id": "test-123", "status": "pending"})
    client.initialize = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    # Circuit breaker state
    client._circuit_breaker_open = False
    return client


@pytest.fixture
def mock_orchestrator_client():
    """Mock do Orchestrator gRPC Client."""
    client = AsyncMock()
    client.pause_workflow = AsyncMock(return_value={"success": True, "workflow_id": "wf-123"})
    client.resume_workflow = AsyncMock(return_value={"success": True, "workflow_id": "wf-123"})
    client.get_workflow_status = AsyncMock(
        return_value={"workflow_id": "wf-123", "status": "RUNNING", "tickets": []}
    )
    client.trigger_replanning = AsyncMock(return_value={"success": True, "plan_id": "plan-123"})
    client.initialize = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_opa_client():
    """Mock do OPA Client."""
    client = AsyncMock()
    client.validate_action = AsyncMock(return_value={"allowed": True, "reason": "Action permitted"})
    client.check_policy = AsyncMock(return_value={"result": True})
    client.initialize = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_kafka_consumer():
    """Mock do AIOKafkaConsumer."""
    consumer = AsyncMock()
    consumer.start = AsyncMock(return_value=None)
    consumer.stop = AsyncMock(return_value=None)
    consumer.commit = AsyncMock(return_value=None)

    # Simula iterador vazio por padrão
    async def empty_iterator():
        raise StopAsyncIteration

    consumer.__aiter__ = lambda self: self
    consumer.__anext__ = empty_iterator

    return consumer


@pytest.fixture
def mock_k8s_client():
    """Mock do cliente Kubernetes CoreV1Api."""
    with patch("kubernetes.client.CoreV1Api") as mock:
        api = MagicMock()
        mock.return_value = api
        yield api


@pytest.fixture
def mock_k8s_custom_api():
    """Mock do cliente Kubernetes CustomObjectsApi (Metrics API)."""
    with patch("kubernetes.client.CustomObjectsApi") as mock:
        api = MagicMock()
        mock.return_value = api
        yield api


@pytest.fixture
def mock_k8s_apps_client():
    """Mock do cliente Kubernetes AppsV1Api."""
    with patch("kubernetes.client.AppsV1Api") as mock:
        api = MagicMock()
        mock.return_value = api
        yield api


@pytest.fixture
def sample_playbook_path(tmp_path):
    """Fixture que cria um playbook YAML de teste."""
    import yaml

    playbook_path = tmp_path / "test_playbook.yaml"
    playbook_content = {
        "playbook_name": "test_playbook",
        "description": "Test playbook for unit tests",
        "timeout_seconds": 60,
        "actions": [
            {"type": "check_worker_health", "parameters": {"worker_id": "worker-1"}},
            {
                "type": "reallocate_ticket",
                "parameters": {"ticket_id": "ticket-123", "reason": "test_recovery"},
            },
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))
    return str(playbook_path)


@pytest.fixture
def sample_incident():
    """Fixture que fornece um incidente de teste."""
    return {
        "incident_id": "inc-123",
        "incident_type": "ticket_timeout",
        "severity": "medium",
        "service": "worker-agents",
        "description": "Ticket execution timeout",
        "detected_at": "2026-03-18T10:00:00Z",
        "metadata": {"ticket_id": "ticket-123", "worker_id": "worker-1", "timeout_seconds": 300},
    }


@pytest.fixture
def sample_chaos_experiment():
    """Fixture que fornece um experimento de chaos de teste."""
    from src.chaos.chaos_models import ChaosExperiment, FaultInjection, FaultType, TargetSelector

    target = TargetSelector(namespace="neural-hive-orchestration", service_name="worker-agents")
    injection = FaultInjection(fault_type=FaultType.POD_KILL, target=target, duration_seconds=60)
    experiment = ChaosExperiment(
        name="Test Pod Kill",
        description="Test experiment",
        environment="staging",
        fault_injections=[injection],
    )
    return experiment


# Configuração de asyncio para testes
@pytest.fixture(scope="session")
def event_loop_policy():
    """Configura a policy de event loop para testes."""
    import asyncio

    policy = (
        asyncio.WindowsSelectorEventLoopPolicy()
        if sys.platform == "win32"
        else asyncio.DefaultEventLoopPolicy()
    )
    return policy
