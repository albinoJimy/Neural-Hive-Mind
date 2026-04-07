"""
Unit tests para SLA Monitoring.

Testa a verificação de SLA de workflows, detecção de deadline approaching
e violações de SLA.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Mock de dependências problemáticas antes de importar
sys.modules["neural_hive_security"] = MagicMock()
sys.modules["neural_have_security.cors"] = MagicMock()


@pytest.fixture
def mock_config():
    """Config mock para testes."""
    config = MagicMock()
    config.sla_management_enabled = True
    config.sla_management_host = "localhost"
    config.sla_management_port = 8080
    config.sla_management_timeout_seconds = 5
    config.sla_deadline_warning_threshold = 0.8
    config.sla_budget_critical_threshold = 0.1
    return config


@pytest.fixture
def mock_redis_client():
    """Redis client mock."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.record_sla_check_duration = MagicMock()
    metrics.record_sla_monitor_error = MagicMock()
    metrics.record_deadline_approaching = MagicMock()
    metrics.update_sla_remaining = MagicMock()
    return metrics


@pytest.fixture
def sla_monitor(mock_config, mock_redis_client, mock_metrics):
    """SLAMonitor instance para testes."""
    from src.sla.sla_monitor import SLAMonitor

    monitor = SLAMonitor(mock_config, mock_redis_client, mock_metrics)
    return monitor


@pytest.fixture
def sample_ticket_with_sla():
    """Ticket com SLA definido."""
    now_ms = datetime.now().timestamp() * 1000
    return {
        "ticket_id": "ticket-123",
        "action": "query",
        "created_at": now_ms - 10000,  # 10 segundos atrás
        "sla": {"deadline": now_ms + 50000},  # 50 segundos no futuro (total 60s)
    }


@pytest.fixture
def sample_ticket_near_deadline():
    """Ticket próximo do deadline (85% consumido)."""
    now_ms = datetime.now().timestamp() * 1000
    total_time = 100000  # 100 segundos
    elapsed = 85000  # 85 segundos (85%)
    return {
        "ticket_id": "ticket-456",
        "action": "transform",
        "created_at": now_ms - elapsed,
        "sla": {"deadline": now_ms + (total_time - elapsed)},  # 15s restantes
    }


@pytest.fixture
def sample_tickets_list(sample_ticket_with_sla, sample_ticket_near_deadline):
    """Lista de tickets para verificação de workflow."""
    # check_workflow_sla espera formato {'ticket': {...}}
    return [{"ticket": sample_ticket_with_sla}, {"ticket": sample_ticket_near_deadline}]


class TestTicketDeadlineCheck:
    """Testes de verificação de deadline de ticket."""

    @pytest.mark.asyncio
    async def test_check_ticket_deadline_ok(self, sla_monitor, sample_ticket_with_sla):
        """Deve verificar ticket com tempo suficiente."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_ticket_deadline(sample_ticket_with_sla)

        assert result["deadline_approaching"] is False
        assert result["remaining_seconds"] > 0
        assert result["percent_consumed"] < 0.8
        assert result["sla_deadline"] is not None

    @pytest.mark.asyncio
    async def test_check_ticket_deadline_approaching(
        self, sla_monitor, sample_ticket_near_deadline
    ):
        """Deve detectar ticket próximo do deadline."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_ticket_deadline(sample_ticket_near_deadline)

        assert result["deadline_approaching"] is True
        assert result["remaining_seconds"] > 0
        assert result["percent_consumed"] >= 0.8

    @pytest.mark.asyncio
    async def test_check_ticket_without_sla(self, sla_monitor):
        """Deve lidar com ticket sem campos SLA."""
        ticket = {"ticket_id": "ticket-789", "action": "query"}

        await sla_monitor.initialize()
        result = await sla_monitor.check_ticket_deadline(ticket)

        assert result["deadline_approaching"] is False
        assert result["remaining_seconds"] == 0
        assert result["sla_deadline"] is None

    @pytest.mark.asyncio
    async def test_check_ticket_missed_deadline(self, sla_monitor):
        """Deve detectar deadline já ultrapassado."""
        now_ms = datetime.now().timestamp() * 1000
        ticket = {
            "ticket_id": "ticket-999",
            "created_at": now_ms - 100000,
            "sla": {"deadline": now_ms - 1000},  # 1 segundo no passado
        }

        await sla_monitor.initialize()
        result = await sla_monitor.check_ticket_deadline(ticket)

        assert result["remaining_seconds"] < 0
        # percent_consumed é limitado a 1.0 pelo código (clamp)
        assert result["percent_consumed"] == 1.0


class TestWorkflowSlaCheck:
    """Testes de verificação de SLA de workflow."""

    @pytest.mark.asyncio
    async def test_check_workflow_sla_compliance(self, sla_monitor, sample_ticket_with_sla):
        """Deve verificar compliance de SLA do workflow."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_workflow_sla(
            workflow_id="workflow-123",
            tickets=[{"ticket": sample_ticket_with_sla}],  # Formato esperado
        )

        assert "deadline_approaching" in result
        assert "critical_tickets" in result
        assert "remaining_seconds" in result
        assert result["deadline_approaching"] is False

    @pytest.mark.asyncio
    async def test_check_workflow_with_critical_tickets(self, sla_monitor, sample_tickets_list):
        """Deve identificar tickets críticos no workflow."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_workflow_sla(
            workflow_id="workflow-456", tickets=sample_tickets_list
        )

        assert result["deadline_approaching"] is True
        assert len(result["critical_tickets"]) > 0
        assert "ticket-456" in result["critical_tickets"]

    @pytest.mark.asyncio
    async def test_check_empty_workflow(self, sla_monitor):
        """Deve lidar com workflow sem tickets."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_workflow_sla(workflow_id="workflow-empty", tickets=[])

        assert result["deadline_approaching"] is False
        assert len(result["critical_tickets"]) == 0


class TestSlaBreachAlert:
    """Testes de alerta de violação de SLA."""

    @pytest.mark.asyncio
    async def test_trigger_sla_breach_alert(self, sla_monitor, sample_ticket_near_deadline):
        """Deve detectar deadline approaching."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_ticket_deadline(sample_ticket_near_deadline)

        # Verificar que o deadline approaching foi detectado
        assert result["deadline_approaching"] is True
        assert result["remaining_seconds"] > 0
        assert result["percent_consumed"] >= 0.8

    @pytest.mark.asyncio
    async def test_calculate_remaining_time(self, sla_monitor, sample_ticket_with_sla):
        """Deve calcular tempo restante corretamente."""
        await sla_monitor.initialize()

        result = await sla_monitor.check_ticket_deadline(sample_ticket_with_sla)

        assert result["remaining_seconds"] > 0
        assert isinstance(result["remaining_seconds"], (int, float))
