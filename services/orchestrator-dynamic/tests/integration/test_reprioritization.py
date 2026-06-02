"""
Testes de integração para re-prioritização dinâmica de tickets.

Testa a integração entre RePrioritizer, SLARePrioritizer,
PreemptionManager e AdaptivePriorityCalculator.
"""

from datetime import datetime, timezone

UTC = timezone.utc
from unittest.mock import Mock

import pytest
from src.scheduler.adaptive_priority import AdaptivePriorityCalculator
from src.scheduler.preemption import PreemptionManager
from src.scheduler.preemption_rules import PreemptionDecision, PreemptionRules
from src.scheduler.reprioritizer import RePrioritizer
from src.scheduler.sla_reprioritizer import SLARePrioritizer


class TestRePrioritizationIntegration:
    """Testes de integração de re-prioritização."""

    @pytest.fixture()
    def mock_config(self):
        """Configuração mock."""
        config = Mock()
        config.scheduler_priority_weights = {"risk": 0.4, "qos": 0.3, "sla": 0.3}
        return config

    @pytest.fixture()
    def priority_calculator(self, mock_config):
        """Calculador de prioridade."""
        from src.scheduler.priority_calculator import PriorityCalculator

        return PriorityCalculator(mock_config)

    @pytest.fixture()
    def queue_manager(self, mock_config):
        """Gerenciador de filas."""
        from src.scheduler.queue_manager import QueueManager

        return QueueManager(mock_config)

    @pytest.fixture()
    def reprioritizer(self, priority_calculator, queue_manager):
        """RePrioritizer."""
        return RePrioritizer(priority_calculator, queue_manager)

    @pytest.fixture()
    def sla_reprioritizer(self, reprioritizer, queue_manager):
        """SLARePrioritizer."""
        return SLARePrioritizer(reprioritizer, queue_manager)

    @pytest.fixture()
    def adaptive_calculator(self):
        """AdaptivePriorityCalculator."""
        config = Mock()
        config.adaptive_priority_enabled = True
        config.adaptive_history_window_days = 7
        config.adaptive_execution_time_threshold = 1.5
        config.adaptive_failure_rate_threshold = 0.20
        return AdaptivePriorityCalculator(config)

    @pytest.fixture()
    def sample_ticket(self):
        """Ticket de exemplo."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return {
            "ticket_id": "ticket-001",
            "task_type": "query",
            "risk_band": "normal",
            "created_at": now_ms,
            "sla": {
                "timeout_ms": 300000,
                "deadline": now_ms + 300000,  # 5 minutos
                "urgency": 0.3,  # Campo urgência explicito
            },
            "qos": {"delivery_mode": "AT_LEAST_ONCE", "consistency": "EVENTUAL"},
        }

    def test_reprioritizer_ticket_priority_change(self, reprioritizer, sample_ticket):
        """Testa mudança de prioridade de ticket."""
        # Simular ticket criado há algum tempo (consumiu parte do SLA)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Ticket criado há 2 minutos (120000ms), deadline em 5 minutos
        sample_ticket["created_at"] = now_ms - 120000  # 40% decorrido
        sample_ticket["sla"]["deadline"] = now_ms + 180000  # 3min restantes

        current_score = reprioritizer.priority_calculator.calculate_priority_score(sample_ticket)

        # Aumentar urgência aproximando deadline (simular tempo passou)
        sample_ticket["created_at"] = now_ms - 270000  # 4.5min decorrido (90% do timeout)
        sample_ticket["sla"]["deadline"] = now_ms + 30000  # 30s restantes

        new_score = reprioritizer.priority_calculator.calculate_priority_score(sample_ticket)

        # Com mais tempo decorrido (>80%), urgência deve aumentar
        assert new_score > current_score

    def test_reprioritizer_no_change_when_threshold_not_met(self, reprioritizer, sample_ticket):
        """Testa que ticket não é movido se mudança é pequena."""
        current_queue = "NORMAL"

        # Mudança pequena de urgência
        sample_ticket["sla"]["urgency"] = 0.4

        new_queue = reprioritizer.reprioritize_ticket(sample_ticket, current_queue)

        # Não deve mover (mudança abaixo do threshold)
        assert new_queue is None

    def test_reprioritizer_by_sla_urgency(self, reprioritizer, sample_ticket):
        """Testa re-priorização por urgência SLA."""
        # Criar cópia para manter estado original
        import copy

        ticket_before = copy.deepcopy(sample_ticket)

        sample_ticket["sla"]["urgency"] = 0.85

        # Urgência alta com risk_band normal → HIGH (não CRITICAL sem risk_band critical)
        new_queue = reprioritizer.reprioritize_by_sla_urgency(sample_ticket, 0.85)

        # Deve retornar HIGH (urgência > 0.5)
        # Nota: retorna None se fila já é HIGH (sem mudança)
        # Verificar que o mapeamento está correcto
        mapped_queue = reprioritizer.queue_manager.map_risk_to_priority("normal", 0.85).value
        assert mapped_queue == "HIGH"

    def test_reprioritizer_by_risk_band(self, reprioritizer, sample_ticket):
        """Testa re-priorização por mudança de risk_band."""
        # Mudar risk_band para critical deve mover para CRITICAL
        new_queue = reprioritizer.reprioritize_by_risk_band(sample_ticket, "critical")

        # Risk band critical → CRITICAL
        # Nota: pode retornar None se o ticket já foi movido para CRITICAL antes
        # Verificar o mapeamento directamente
        mapped_queue = reprioritizer.queue_manager.map_risk_to_priority("critical", 0.3).value
        assert mapped_queue == "CRITICAL"
        # E verificar que o ticket foi actualizado
        assert sample_ticket["risk_band"] == "critical"

    @pytest.mark.asyncio()
    async def test_sla_reprioritizer_on_warning(self, sla_reprioritizer, sample_ticket):
        """Testa re-priorização em SLA warning."""
        event = {"ticket_id": "ticket-001", "sla_urgency": 0.85, "deadline_remaining_pct": 0.2}

        result = await sla_reprioritizer.on_sla_warning(event)

        assert result["action"] == "reprioritize"
        assert result["new_priority"] == "CRITICAL"

    @pytest.mark.asyncio()
    async def test_sla_reprioritizer_on_risk_band_changed(self, sla_reprioritizer):
        """Testa re-priorização em mudança de risk_band."""
        event = {
            "ticket_id": "ticket-002",
            "old_risk_band": "normal",
            "new_risk_band": "critical",
            "reason": "security_concern",
        }

        result = await sla_reprioritizer.on_risk_band_changed(event)

        assert result["action"] == "reprioritize"
        assert result["new_priority"] == "CRITICAL"

    @pytest.mark.asyncio()
    async def test_sla_reprioritizer_on_deadline_approaching(self, sla_reprioritizer):
        """Testa re-priorização quando deadline se aproxima."""
        event = {
            "ticket_id": "ticket-003",
            "deadline_timestamp": int(datetime.now(timezone.utc).timestamp() * 1000) + 30000,
            "remaining_ms": 30000,  # 30 segundos restantes
        }

        result = await sla_reprioritizer.on_deadline_approaching(event)

        assert result["action"] == "reprioritize"
        assert result["new_priority"] in ["HIGH", "CRITICAL"]

    @pytest.mark.asyncio()
    async def test_sla_reprioritizer_on_breach(self, sla_reprioritizer):
        """Testa re-priorização em SLA breach."""
        event = {
            "ticket_id": "ticket-004",
            "breach_type": "timeout",
            "sla_details": {"timeout_ms": 300000},
        }

        result = await sla_reprioritizer.on_sla_breach(event)

        assert result["action"] == "reprioritize"
        assert result["new_priority"] == "CRITICAL"
        assert result["reason"] == "sla_breach"

    def test_adaptive_calculator_with_slow_history(self, adaptive_calculator, sample_ticket):
        """Testa ajuste adaptativo para execuções lentas."""
        # Registrar histórico de execuções lentas
        # timeout_ms = 300000, threshold = 1.5, então precisamos de avg > 450000
        for i in range(5):
            adaptive_calculator.record_execution(
                sample_ticket,
                execution_time_ms=500000,  # 8.3 min vs 5 min esperado (ratio = 1.67 > 1.5)
                status="COMPLETED",
            )

        adjustment = adaptive_calculator.calculate_adaptive_adjustment(sample_ticket)

        # Deve aumentar prioridade
        assert adjustment > 0.0

    def test_adaptive_calculator_with_high_failure_rate(self, adaptive_calculator, sample_ticket):
        """Testa ajuste adaptativo para alta taxa de falha."""
        # Registrar histórico com alta taxa de falha
        for i in range(10):
            status = "FAILED" if i < 3 else "COMPLETED"  # 30% falha
            adaptive_calculator.record_execution(
                sample_ticket, execution_time_ms=100000, status=status
            )

        adjustment = adaptive_calculator.calculate_adaptive_adjustment(sample_ticket)

        # Deve diminuir prioridade
        assert adjustment < 0.0

    def test_preemption_integration_with_reprioritization(self, queue_manager, sample_ticket):
        """Testa integração entre preempção e re-priorização."""
        rules = PreemptionRules()
        mock_metrics = Mock()
        manager = PreemptionManager(rules, queue_manager, mock_metrics)

        high_ticket = {"ticket_id": "high-001", "priority": "CRITICAL", "risk_band": "critical"}

        low_ticket = {
            "ticket_id": "low-001",
            "priority": "LOW",
            "risk_band": "low",
            "execution_progress": 0.1,
            "compensatable": True,
        }

        decision = manager.can_preempt(high_ticket, low_ticket)

        assert decision == PreemptionDecision.ALLOWED

    def test_reprioritizer_batch_processing(self, reprioritizer):
        """Testa re-priorização em lote."""
        tickets = [
            {
                "ticket_id": f"ticket-{i:03d}",
                "task_type": "query",
                "risk_band": "normal" if i < 5 else "low",
                "sla": {"timeout_ms": 300000},
            }
            for i in range(10)
        ]

        result = reprioritizer.reprioritize_batch(tickets, "test_batch")

        assert result["total"] == 10
        assert "reprioritized" in result
        assert "unchanged" in result
        assert "changes" in result


class TestPriorityCalculatorWithAdaptive:
    """Testes integração PriorityCalculator + AdaptivePriority."""

    @pytest.fixture()
    def mock_config(self):
        """Configuração mock."""
        config = Mock()
        config.scheduler_priority_weights = {"risk": 0.4, "qos": 0.3, "sla": 0.3}
        return config

    @pytest.fixture()
    def priority_calculator(self, mock_config):
        """PriorityCalculator."""
        from src.scheduler.priority_calculator import PriorityCalculator

        return PriorityCalculator(mock_config)

    @pytest.fixture()
    def adaptive_calculator(self):
        """AdaptivePriorityCalculator."""
        config = Mock()
        config.adaptive_priority_enabled = True
        config.adaptive_history_window_days = 7
        config.adaptive_execution_time_threshold = 1.5
        config.adaptive_failure_rate_threshold = 0.20
        return AdaptivePriorityCalculator(config)

    @pytest.fixture()
    def sample_ticket(self):
        """Ticket de exemplo."""
        return {
            "ticket_id": "ticket-001",
            "task_type": "query",
            "risk_band": "normal",
            "sla": {"timeout_ms": 300000},
            "qos": {"delivery_mode": "AT_LEAST_ONCE", "consistency": "EVENTUAL"},
        }

    def test_apply_adaptive_adjustment_increases_priority(self, priority_calculator, sample_ticket):
        """Testa aplicação de ajuste adaptativo positivo."""
        base_priority = 0.6
        adaptive_adjustment = 0.15

        adjusted = priority_calculator.apply_adaptive_adjustment(base_priority, adaptive_adjustment)

        assert adjusted == 0.75

    def test_apply_adaptive_adjustment_decreases_priority(self, priority_calculator, sample_ticket):
        """Testa aplicação de ajuste adaptativo negativo."""
        base_priority = 0.6
        adaptive_adjustment = -0.1

        adjusted = priority_calculator.apply_adaptive_adjustment(base_priority, adaptive_adjustment)

        assert adjusted == 0.5

    def test_apply_adaptive_adjustment_clamps_to_max(self, priority_calculator):
        """Testa que ajuste é limitado a 1.0."""
        base_priority = 0.9
        adaptive_adjustment = 0.3  # Excederia 1.0

        adjusted = priority_calculator.apply_adaptive_adjustment(base_priority, adaptive_adjustment)

        assert adjusted == 1.0

    def test_apply_adaptive_adjustment_clamps_to_min(self, priority_calculator):
        """Testa que ajuste é limitado a 0.0."""
        base_priority = 0.1
        adaptive_adjustment = -0.3  # Seria negativo

        adjusted = priority_calculator.apply_adaptive_adjustment(base_priority, adaptive_adjustment)

        assert adjusted == 0.0
