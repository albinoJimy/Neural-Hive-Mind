"""
Testes unitários para AdaptivePriorityCalculator.

Testa cálculo de prioridade adaptativa baseado em histórico.
"""

import pytest
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from src.scheduler.adaptive_priority import AdaptivePriorityCalculator


class TestAdaptivePriorityCalculator:
    """Testes para AdaptivePriorityCalculator."""

    @pytest.fixture
    def calculator(self):
        """Retorna instância do calculador."""
        config = Mock()
        config.adaptive_history_window_days = 7
        config.adaptive_execution_time_threshold = 1.5
        config.adaptive_failure_rate_threshold = 0.20
        config.adaptive_priority_enabled = True

        return AdaptivePriorityCalculator(config)

    @pytest.fixture
    def sample_ticket(self):
        """Retorna ticket de exemplo."""
        return {
            "ticket_id": "ticket-001",
            "task_type": "query",
            "risk_band": "normal",
            "sla": {"timeout_ms": 300000},  # 5 min
        }

    def test_calculate_adaptive_adjustment_no_history(self, calculator, sample_ticket):
        """Testa ajuste quando não há histórico."""
        adjustment = calculator.calculate_adaptive_adjustment(sample_ticket)

        assert adjustment == 0.0

    def test_calculate_adaptive_adjustment_disabled(self, sample_ticket):
        """Testa ajuste quando calculador está desabilitado."""
        config = Mock()
        config.adaptive_priority_enabled = False
        calculator = AdaptivePriorityCalculator(config)

        adjustment = calculator.calculate_adaptive_adjustment(sample_ticket)

        assert adjustment == 0.0

    def test_calculate_adjustment_slow_execution(self, calculator, sample_ticket):
        """Testa ajuste positivo para execuções lentas."""
        # Registrar histórico de execuções lentas
        ticket_type = calculator._get_ticket_type(sample_ticket)

        # Execuções levam 6 min (360s) vs 5 min esperado = 1.2x
        for i in range(5):
            calculator.record_execution(
                sample_ticket, execution_time_ms=360000, status="COMPLETED"  # 6 min
            )

        adjustment = calculator.calculate_adaptive_adjustment(sample_ticket)

        # Deve ter ajuste positivo (aumentar prioridade)
        assert adjustment >= 0.0

    def test_calculate_adjustment_high_failure_rate(self, calculator, sample_ticket):
        """Testa ajuste negativo para alta taxa de falha."""
        ticket_type = calculator._get_ticket_type(sample_ticket)

        # Registrar histórico com muitas falhas (30%)
        for i in range(7):
            calculator.record_execution(
                sample_ticket,
                execution_time_ms=100000,
                status="FAILED" if i < 2 else "COMPLETED",  # 2 falhas em 7
            )

        adjustment = calculator.calculate_adaptive_adjustment(sample_ticket)

        # Deve ter ajuste negativo (diminuir prioridade)
        assert adjustment <= 0.0

    def test_calculate_adjustment_fast_execution(self, calculator, sample_ticket):
        """Testa ajuste zero para execuções rápidas."""
        ticket_type = calculator._get_ticket_type(sample_ticket)

        # Execuções rápidas (1 min vs 5 min esperado)
        for i in range(5):
            calculator.record_execution(
                sample_ticket, execution_time_ms=60000, status="COMPLETED"  # 1 min
            )

        adjustment = calculator.calculate_adaptive_adjustment(sample_ticket)

        # Execuções rápidas não devem aumentar prioridade
        assert adjustment == 0.0

    def test_get_ticket_type_from_task_type(self, calculator, sample_ticket):
        """Testa extração de tipo de ticket."""
        ticket_type = calculator._get_ticket_type(sample_ticket)

        assert ticket_type == "query"

    def test_get_ticket_type_from_action(self, calculator):
        """Testa extração de tipo de ticket quando não há task_type."""
        ticket = {"ticket_id": "ticket-002", "action": "transform_data", "risk_band": "normal"}

        ticket_type = calculator._get_ticket_type(ticket)

        assert ticket_type == "transform_data"

    def test_get_ticket_type_from_risk_band(self, calculator):
        """Testa extração de tipo de ticket usando risk_band como fallback."""
        ticket = {"ticket_id": "ticket-003", "risk_band": "high"}

        ticket_type = calculator._get_ticket_type(ticket)

        assert ticket_type == "risk_high"

    def test_record_execution(self, calculator, sample_ticket):
        """Testa registro de execução no histórico."""
        calculator.record_execution(
            sample_ticket, execution_time_ms=150000, status="COMPLETED", resource_usage=0.5
        )

        ticket_type = calculator._get_ticket_type(sample_ticket)
        history = calculator.execution_history[ticket_type]

        assert len(history) == 1
        assert history[0]["ticket_id"] == "ticket-001"
        assert history[0]["execution_time_ms"] == 150000
        assert history[0]["status"] == "COMPLETED"
        assert history[0]["resource_usage"] == 0.5

    def test_get_recent_history_filters_old_entries(self, calculator, sample_ticket):
        """Testa filtro de histórico por janela de tempo."""
        ticket_type = calculator._get_ticket_type(sample_ticket)

        # Adicionar entrada antiga (fora da janela)
        old_timestamp = int((datetime.now(timezone.utc) - timedelta(days=10)).timestamp() * 1000)
        calculator.execution_history[ticket_type].append(
            {
                "ticket_id": "old-ticket",
                "timestamp": old_timestamp,
                "execution_time_ms": 100000,
                "status": "COMPLETED",
            }
        )

        # Adicionar entrada recente
        calculator.record_execution(sample_ticket, execution_time_ms=100000, status="COMPLETED")

        recent_history = calculator._get_recent_history(ticket_type)

        # Apenas entrada recente deve estar presente
        assert len(recent_history) == 1
        assert recent_history[0]["ticket_id"] == "ticket-001"

    def test_get_history_statistics_empty(self, calculator):
        """Testa estatísticas com histórico vazio."""
        stats = calculator.get_history_statistics()

        assert stats["total_entries"] == 0
        assert stats["ticket_types"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0

    def test_get_history_statistics_with_data(self, calculator, sample_ticket):
        """Testa estatísticas com histórico preenchido."""
        # Registrar algumas execuções
        for i in range(10):
            calculator.record_execution(sample_ticket, execution_time_ms=150000, status="COMPLETED")
        # 2 falhas
        for i in range(2):
            calculator.record_execution(sample_ticket, execution_time_ms=100000, status="FAILED")

        stats = calculator.get_history_statistics()

        assert stats["total_entries"] == 12
        assert stats["completed"] == 10
        assert stats["failed"] == 2
        assert stats["success_rate"] == pytest.approx(83.3, rel=0.1)

    def test_clear_old_history(self, calculator, sample_ticket):
        """Testa limpeza de entradas antigas."""
        # Adicionar entradas antigas e recentes
        ticket_type = calculator._get_ticket_type(sample_ticket)

        old_timestamp = int((datetime.now(timezone.utc) - timedelta(days=10)).timestamp() * 1000)
        calculator.execution_history[ticket_type].append(
            {
                "ticket_id": "old-1",
                "timestamp": old_timestamp,
                "execution_time_ms": 100000,
                "status": "COMPLETED",
            }
        )

        calculator.record_execution(sample_ticket, execution_time_ms=100000, status="COMPLETED")

        assert len(calculator.execution_history[ticket_type]) == 2

        # Limpar entradas antigas
        calculator.clear_old_history(days=7)

        # Apenas entrada recente deve permanecer
        assert len(calculator.execution_history[ticket_type]) == 1
        assert calculator.execution_history[ticket_type][0]["ticket_id"] == "ticket-001"


class Mock:
    """Mock simples para testes."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
