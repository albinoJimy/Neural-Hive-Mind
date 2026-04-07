"""
Testes unitários para PreemptionManager e PreemptionRules.

Testa regras de preempção e gerenciamento de preempção de tickets.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime, timezone

from src.scheduler.preemption_rules import PreemptionRules, PreemptionDecision
from src.scheduler.preemption import PreemptionManager, PreemptionStatus
from src.scheduler.priority_queues import PriorityLevel


class TestPreemptionRules:
    """Testes para PreemptionRules."""

    @pytest.fixture
    def rules(self):
        """Retorna instância de PreemptionRules."""
        return PreemptionRules()

    @pytest.fixture
    def high_priority_critical_ticket(self):
        """Retorna ticket CRITICAL."""
        return {
            "ticket_id": "critical-001",
            "priority": "CRITICAL",
            "risk_band": "critical",
            "task_type": "query",
        }

    @pytest.fixture
    def high_priority_high_ticket(self):
        """Retorna ticket HIGH."""
        return {
            "ticket_id": "high-001",
            "priority": "HIGH",
            "risk_band": "high",
            "task_type": "transform",
        }

    @pytest.fixture
    def normal_priority_ticket(self):
        """Retorna ticket NORMAL."""
        return {
            "ticket_id": "normal-001",
            "priority": "NORMAL",
            "risk_band": "normal",
            "task_type": "validate",
        }

    @pytest.fixture
    def low_priority_ticket(self):
        """Retorna ticket LOW."""
        return {
            "ticket_id": "low-001",
            "priority": "LOW",
            "risk_band": "low",
            "task_type": "analyze",
        }

    @pytest.fixture
    def low_priority_ticket_in_progress(self, low_priority_ticket):
        """Retorna ticket LOW em execução com baixo progresso."""
        ticket = low_priority_ticket.copy()
        ticket["started_at"] = (
            int(datetime.now(timezone.utc).timestamp() * 1000) - 10000
        )  # 10s atrás
        ticket["sla"] = {"timeout_ms": 300000}  # 5 min
        ticket["compensatable"] = True
        ticket["execution_progress"] = 0.1  # 10%
        return ticket

    @pytest.fixture
    def low_priority_ticket_far_in_progress(self, low_priority_ticket):
        """Retorna ticket LOW com progresso alto (não preemptível)."""
        ticket = low_priority_ticket.copy()
        ticket["execution_progress"] = 0.5  # 50% - acima do threshold
        ticket["compensatable"] = True
        return ticket

    @pytest.fixture
    def non_compensatable_ticket(self):
        """Retorna ticket não compensatable."""
        return {
            "ticket_id": "non-comp-001",
            "priority": "LOW",
            "risk_band": "low",
            "compensatable": False,
            "execution_progress": 0.1,
        }

    def test_critical_can_preempt_normal(
        self, rules, high_priority_critical_ticket, normal_priority_ticket
    ):
        """Testa que CRITICAL pode preemptar NORMAL."""
        decision = rules.can_preempt(high_priority_critical_ticket, normal_priority_ticket)

        assert decision == PreemptionDecision.ALLOWED

    def test_critical_can_preempt_low(
        self, rules, high_priority_critical_ticket, low_priority_ticket
    ):
        """Testa que CRITICAL pode preemptar LOW."""
        decision = rules.can_preempt(high_priority_critical_ticket, low_priority_ticket)

        assert decision == PreemptionDecision.ALLOWED

    def test_high_can_preempt_low(self, rules, high_priority_high_ticket, low_priority_ticket):
        """Testa que HIGH pode preemptar LOW."""
        decision = rules.can_preempt(high_priority_high_ticket, low_priority_ticket)

        assert decision == PreemptionDecision.ALLOWED

    def test_high_cannot_preempt_normal(
        self, rules, high_priority_high_ticket, normal_priority_ticket
    ):
        """Testa que HIGH NÃO pode preemptar NORMAL."""
        decision = rules.can_preempt(high_priority_high_ticket, normal_priority_ticket)

        assert decision == PreemptionDecision.DENIED_PRIORITY_DIFF

    def test_same_priority_cannot_preempt(self, rules, normal_priority_ticket):
        """Testa que mesma prioridade não pode preemptar."""
        decision = rules.can_preempt(normal_priority_ticket, normal_priority_ticket)

        assert decision == PreemptionDecision.DENIED_PRIORITY_DIFF

    def test_preemption_denied_execution_progress_too_high(
        self, rules, high_priority_critical_ticket, low_priority_ticket_far_in_progress
    ):
        """Testa que preempção é negada quando progresso > 30%."""
        decision = rules.can_preempt(
            high_priority_critical_ticket, low_priority_ticket_far_in_progress
        )

        assert decision == PreemptionDecision.DENIED_EXECUTION_PROGRESS

    def test_preemption_denied_not_compensatable(
        self, rules, high_priority_critical_ticket, non_compensatable_ticket
    ):
        """Testa que preempção é negada quando ticket não é compensatable."""
        decision = rules.can_preempt(high_priority_critical_ticket, non_compensatable_ticket)

        assert decision == PreemptionDecision.DENIED_NOT_COMPENSATABLE

    def test_get_execution_progress_from_field(self, rules):
        """Testa obtenção de progresso de campo direto."""
        ticket = {"execution_progress": 0.45}
        progress = rules._get_execution_progress(ticket)

        assert progress == 0.45

    def test_get_execution_progress_from_timestamps(self, rules):
        """Testa cálculo de progresso baseado em timestamps."""
        started_at = int(datetime.now(timezone.utc).timestamp() * 1000) - 60000  # 60s atrás
        ticket = {"started_at": started_at, "sla": {"timeout_ms": 300000}}  # 5 min
        # Não incluir execution_progress para forçar cálculo por timestamp
        progress = rules._get_execution_progress(ticket)

        # 60s / 300s = 0.2 (margem para tolerância de execução)
        assert 0.15 <= progress <= 0.30

    def test_is_compensatable_true(self, rules):
        """Testa verificação de compensatable (True)."""
        ticket = {"compensatable": True}
        assert rules._is_compensatable(ticket) is True

    def test_is_compensatable_false(self, rules):
        """Testa verificação de compensatable (False)."""
        ticket = {"compensatable": False}
        assert rules._is_compensatable(ticket) is False

    def test_is_compensatable_from_compensation_action(self, rules):
        """Testa verificação de compensatable via compensation_action."""
        ticket = {"compensation_action": "rollback"}
        assert rules._is_compensatable(ticket) is True

    def test_extract_priority_from_field(self, rules):
        """Testa extração de prioridade do campo."""
        ticket = {"priority": "HIGH"}
        assert rules._extract_priority(ticket) == "HIGH"

    def test_extract_priority_from_risk_band(self, rules):
        """Testa extração de prioridade do risk_band."""
        ticket = {"risk_band": "critical"}
        assert rules._extract_priority(ticket) == "CRITICAL"

    def test_get_preemption_cost(self, rules, low_priority_ticket_in_progress):
        """Testa cálculo de custo de preempção."""
        cost = rules.get_preemption_cost(low_priority_ticket_in_progress)

        assert "progress_lost" in cost
        assert "needs_compensation" in cost
        assert "estimated_rollback_ms" in cost
        assert "resource_waste" in cost

        assert cost["progress_lost"] == 0.1
        assert cost["needs_compensation"] is True


class TestPreemptionManager:
    """Testes para PreemptionManager."""

    @pytest.fixture
    def mock_rules(self):
        """Mock de PreemptionRules."""
        rules = Mock(spec=PreemptionRules)
        rules.can_preempt = Mock(return_value=PreemptionDecision.ALLOWED)
        rules._get_execution_progress = Mock(return_value=0.1)
        rules._is_compensatable = Mock(return_value=True)
        rules._extract_priority = Mock(return_value="LOW")
        rules.max_execution_progress_pct = 0.3
        rules._is_preemption_allowed = Mock(return_value=True)
        return rules

    @pytest.fixture
    def mock_queue_manager(self):
        """Mock de QueueManager."""
        return Mock()

    @pytest.fixture
    def mock_metrics(self):
        """Mock de métricas."""
        metrics = Mock()
        metrics.preemption_executed_total = Mock()
        metrics.preemption_executed_total.labels = Mock(return_value=Mock())
        return metrics

    @pytest.fixture
    def manager(self, mock_rules, mock_queue_manager, mock_metrics):
        """Retorna instância de PreemptionManager."""
        return PreemptionManager(mock_rules, mock_queue_manager, mock_metrics)

    @pytest.fixture
    def sample_executing_tickets(self):
        """Retorna lista de tickets em execução."""
        return [
            {"ticket_id": "exec-001", "priority": "LOW", "execution_progress": 0.1},
            {"ticket_id": "exec-002", "priority": "NORMAL", "execution_progress": 0.2},
            {"ticket_id": "exec-003", "priority": "LOW", "execution_progress": 0.05},
        ]

    def test_can_preempt_delegates_to_rules(self, manager, mock_rules):
        """Testa que can_preempt delega para PreemptionRules."""
        high_ticket = {"ticket_id": "high-001", "priority": "CRITICAL"}
        low_ticket = {"ticket_id": "low-001", "priority": "LOW"}

        decision = manager.can_preempt(high_ticket, low_ticket)

        mock_rules.can_preempt.assert_called_once_with(high_ticket, low_ticket)
        assert decision == PreemptionDecision.ALLOWED

    def test_find_preemptible_ticket_returns_first_allowed(
        self, manager, mock_rules, sample_executing_tickets
    ):
        """Testa que find_preemptible_ticket retorna primeiro ticket permitido."""
        # Configurar mock para permitir apenas o primeiro
        mock_rules.can_preempt.side_effect = [
            PreemptionDecision.ALLOWED,  # Primeiro ticket
            PreemptionDecision.DENIED_PRIORITY_DIFF,  # Segundo ticket
        ]

        ticket = manager.find_preemptible_ticket(PriorityLevel.CRITICAL, sample_executing_tickets)

        # Deve retornar o primeiro (último da lista devido ao reversed)
        assert ticket is not None
        assert ticket["ticket_id"] == "exec-003"

    def test_find_preemptible_ticket_none_allowed(
        self, manager, mock_rules, sample_executing_tickets
    ):
        """Testa que find_preemptible_ticket retorna None se nenhum permitido."""
        mock_rules.can_preempt.return_value = PreemptionDecision.DENIED_EXECUTION_PROGRESS

        ticket = manager.find_preemptible_ticket(PriorityLevel.CRITICAL, sample_executing_tickets)

        assert ticket is None

    @pytest.mark.asyncio
    async def test_preempt_ticket_success(self, manager):
        """Testa preempção bem-sucedida."""
        ticket = {
            "ticket_id": "low-001",
            "priority": "LOW",
            "execution_progress": 0.1,
            "compensatable": True,
        }

        result = await manager.preempt_ticket(ticket, "test_preemption")

        assert result["status"] == PreemptionStatus.SUCCESS
        assert result["ticket_id"] == "low-001"
        assert "compensation_ticket_id" in result

    @pytest.mark.asyncio
    async def test_preempt_ticket_denied(self, mock_queue_manager, mock_metrics):
        """Testa preempção negada."""
        # Criar regras mock específicas para este teste
        rules = Mock(spec=PreemptionRules)
        rules.can_preempt = Mock(return_value=PreemptionDecision.ALLOWED)
        rules._get_execution_progress = Mock(return_value=0.5)  # Acima do threshold
        rules._is_compensatable = Mock(return_value=True)
        rules._extract_priority = Mock(return_value="LOW")
        rules.max_execution_progress_pct = 0.3
        rules._is_preemption_allowed = Mock(return_value=True)

        manager = PreemptionManager(rules, mock_queue_manager, mock_metrics)

        ticket = {
            "ticket_id": "low-002",
            "priority": "LOW",
            "execution_progress": 0.5,  # Acima do threshold
        }

        result = await manager.preempt_ticket(ticket, "test_preemption")

        assert result["status"] == PreemptionStatus.DENIED

    def test_get_preemption_history(self, manager):
        """Testa obtenção de histórico de preempções."""
        # Registrar algumas verificações
        high_ticket = {"ticket_id": "high-001", "priority": "CRITICAL"}
        low_ticket = {"ticket_id": "low-001", "priority": "LOW"}
        manager.can_preempt(high_ticket, low_ticket)

        history = manager.get_preemption_history()

        assert len(history) == 1
        assert history[0]["high_ticket_id"] == "high-001"
        assert history[0]["low_ticket_id"] == "low-001"

    def test_get_preemption_statistics(self, manager):
        """Testa estatísticas de preempção."""
        # Registrar verificações
        for i in range(5):
            high_ticket = {"ticket_id": f"high-{i}", "priority": "CRITICAL"}
            low_ticket = {"ticket_id": f"low-{i}", "priority": "LOW"}
            manager.can_preempt(high_ticket, low_ticket)

        stats = manager.get_preemption_statistics()

        assert stats["total_checks"] == 5
        assert stats["total_allowed"] == 5
        assert stats["allowance_rate"] == 100.0
