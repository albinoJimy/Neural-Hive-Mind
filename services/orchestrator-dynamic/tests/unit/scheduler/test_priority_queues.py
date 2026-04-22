"""
Testes unitários para PriorityQueues e QueueManager.

Cobertura:
- Enfileiramento correcto por prioridade
- Weighted round-robin para dequeue
- Peek não remove tickets
- Obtenção de tamanhos das filas
- Limpeza de filas
- Preempção de filas de menor prioridade
- Integração com PriorityCalculator
"""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from src.config.settings import OrchestratorSettings
from src.scheduler.priority_queues import PriorityLevel, PriorityQueues
from src.scheduler.queue_manager import QueueManager

# Fixtures ====================================================================


@pytest.fixture()
def priority_queues():
    """Instância limpa de PriorityQueues para cada teste."""
    return PriorityQueues()


@pytest.fixture()
def mock_config():
    """Config mock para QueueManager."""
    config = MagicMock(spec=OrchestratorSettings)
    config.scheduler_priority_weights = {"risk": 0.4, "qos": 0.3, "sla": 0.3}
    return config


@pytest.fixture()
def queue_manager(mock_config):
    """Instância de QueueManager para testes."""
    return QueueManager(mock_config)


@pytest.fixture()
def sample_tickets() -> dict[str, dict[str, Any]]:
    """Tickets de amostra para testes."""
    now = datetime.now()

    return {
        "critical": {
            "ticket_id": "ticket-critical-001",
            "risk_band": "critical",
            "qos": {
                "delivery_mode": "EXACTLY_ONCE",
                "consistency": "STRONG",
                "durability": "PERSISTENT",
            },
            "sla": {"deadline": (now + timedelta(minutes=6)).isoformat(), "timeout_ms": 3600000},
            "created_at": (now - timedelta(minutes=54)).isoformat(),
            "estimated_duration_ms": 1000,
        },
        "high": {
            "ticket_id": "ticket-high-001",
            "risk_band": "high",
            "qos": {
                "delivery_mode": "AT_LEAST_ONCE",
                "consistency": "STRONG",
                "durability": "PERSISTENT",
            },
            "sla": {"deadline": (now + timedelta(hours=1)).isoformat(), "timeout_ms": 3600000},
            "created_at": now.isoformat(),
            "estimated_duration_ms": 1000,
        },
        "normal": {
            "ticket_id": "ticket-normal-001",
            "risk_band": "normal",
            "qos": {
                "delivery_mode": "AT_LEAST_ONCE",
                "consistency": "EVENTUAL",
                "durability": "PERSISTENT",
            },
            "sla": {"deadline": (now + timedelta(hours=2)).isoformat(), "timeout_ms": 7200000},
            "created_at": now.isoformat(),
            "estimated_duration_ms": 1000,
        },
        "low": {
            "ticket_id": "ticket-low-001",
            "risk_band": "low",
            "qos": {
                "delivery_mode": "AT_MOST_ONCE",
                "consistency": "EVENTUAL",
                "durability": "EPHEMERAL",
            },
            "sla": {"deadline": (now + timedelta(hours=4)).isoformat(), "timeout_ms": 14400000},
            "created_at": now.isoformat(),
            "estimated_duration_ms": 1000,
        },
    }


# Testes PriorityQueues =======================================================


class TestPriorityQueuesEnqueue:
    """Testes de enfileiramento."""

    def test_enqueue_to_critical_queue(self, priority_queues):
        """Ticket com score >= 0.9 vai para CRITICAL."""
        ticket = {"ticket_id": "test-001"}
        queue_name = priority_queues.enqueue(ticket, 0.95)

        assert queue_name == "CRITICAL"
        assert priority_queues.get_queue_size("CRITICAL") == 1
        assert priority_queues.peek("CRITICAL")["ticket_id"] == "test-001"

    def test_enqueue_to_high_queue(self, priority_queues):
        """Ticket com 0.7 <= score < 0.9 vai para HIGH."""
        ticket = {"ticket_id": "test-002"}
        queue_name = priority_queues.enqueue(ticket, 0.75)

        assert queue_name == "HIGH"
        assert priority_queues.get_queue_size("HIGH") == 1

    def test_enqueue_to_normal_queue(self, priority_queues):
        """Ticket com 0.4 <= score < 0.7 vai para NORMAL."""
        ticket = {"ticket_id": "test-003"}
        queue_name = priority_queues.enqueue(ticket, 0.55)

        assert queue_name == "NORMAL"
        assert priority_queues.get_queue_size("NORMAL") == 1

    def test_enqueue_to_low_queue(self, priority_queues):
        """Ticket com score < 0.4 vai para LOW."""
        ticket = {"ticket_id": "test-004"}
        queue_name = priority_queues.enqueue(ticket, 0.25)

        assert queue_name == "LOW"
        assert priority_queues.get_queue_size("LOW") == 1

    def test_enqueue_boundary_critical_high(self, priority_queues):
        """Testa boundary entre CRITICAL e HIGH (0.9)."""
        ticket = {"ticket_id": "test-boundary-1"}

        # 0.9 deve ser CRITICAL
        queue_name = priority_queues.enqueue(ticket, 0.9)
        assert queue_name == "CRITICAL"

        # 0.899 deve ser HIGH
        ticket2 = {"ticket_id": "test-boundary-2"}
        queue_name2 = priority_queues.enqueue(ticket2, 0.899)
        assert queue_name2 == "HIGH"

    def test_enqueue_boundary_high_normal(self, priority_queues):
        """Testa boundary entre HIGH e NORMAL (0.7)."""
        ticket = {"ticket_id": "test-boundary-3"}

        # 0.7 deve ser HIGH
        queue_name = priority_queues.enqueue(ticket, 0.7)
        assert queue_name == "HIGH"

        # 0.699 deve ser NORMAL
        ticket2 = {"ticket_id": "test-boundary-4"}
        queue_name2 = priority_queues.enqueue(ticket2, 0.699)
        assert queue_name2 == "NORMAL"

    def test_enqueue_boundary_normal_low(self, priority_queues):
        """Testa boundary entre NORMAL e LOW (0.4)."""
        ticket = {"ticket_id": "test-boundary-5"}

        # 0.4 deve ser NORMAL
        queue_name = priority_queues.enqueue(ticket, 0.4)
        assert queue_name == "NORMAL"

        # 0.399 deve ser LOW
        ticket2 = {"ticket_id": "test-boundary-6"}
        queue_name2 = priority_queues.enqueue(ticket2, 0.399)
        assert queue_name2 == "LOW"

    def test_enqueue_extreme_values(self, priority_queues):
        """Testa valores extremos de score."""
        ticket1 = {"ticket_id": "test-extreme-1"}
        ticket2 = {"ticket_id": "test-extreme-2"}

        # Score 1.0 (máximo)
        queue1 = priority_queues.enqueue(ticket1, 1.0)
        assert queue1 == "CRITICAL"

        # Score 0.0 (mínimo)
        queue2 = priority_queues.enqueue(ticket2, 0.0)
        assert queue2 == "LOW"

    def test_enqueue_multiple_tickets_same_queue(self, priority_queues):
        """Múltiplos tickets na mesma fila mantêm ordem."""
        for i in range(5):
            ticket = {"ticket_id": f"ticket-{i}"}
            priority_queues.enqueue(ticket, 0.5)  # Todos NORMAL

        assert priority_queues.get_queue_size("NORMAL") == 5

        # Verificar ordem FIFO
        for i in range(5):
            ticket = priority_queues.peek("NORMAL")
            assert ticket["ticket_id"] == f"ticket-{i}"
            priority_queues.queues[PriorityLevel.NORMAL].popleft()


class TestPriorityQueuesDequeue:
    """Testes de desenfileiramento."""

    @pytest.mark.asyncio()
    async def test_dequeue_from_specific_queue(self, priority_queues):
        """Dequeue de fila específica retorna ticket correto."""
        ticket = {"ticket_id": "test-dequeue-1"}
        priority_queues.enqueue(ticket, 0.8)  # HIGH

        retrieved = await priority_queues.dequeue("HIGH")

        assert retrieved is not None
        assert retrieved["ticket_id"] == "test-dequeue-1"
        assert priority_queues.get_queue_size("HIGH") == 0

    @pytest.mark.asyncio()
    async def test_dequeue_from_empty_queue(self, priority_queues):
        """Dequeue de fila vazia retorna None."""
        result = await priority_queues.dequeue("CRITICAL")
        assert result is None

    @pytest.mark.asyncio()
    async def test_dequeue_all_empty_queues(self, priority_queues):
        """Dequeue com todas as filas vazias retorna None."""
        result = await priority_queues.dequeue()  # round-robin
        assert result is None

    @pytest.mark.asyncio()
    async def test_weighted_round_robin_distribution(self, priority_queues):
        """Testa distribuição weighted round-robin (4:3:2:1)."""
        # Enfileirar 10 tickets em cada fila
        for i in range(10):
            priority_queues.enqueue({"ticket_id": f"critical-{i}"}, 0.95)
            priority_queues.enqueue({"ticket_id": f"high-{i}"}, 0.75)
            priority_queues.enqueue({"ticket_id": f"normal-{i}"}, 0.5)
            priority_queues.enqueue({"ticket_id": f"low-{i}"}, 0.2)

        # Dequeue 20 tickets e verificar proporção
        queue_counts = {"CRITICAL": 0, "HIGH": 0, "NORMAL": 0, "LOW": 0}

        for _ in range(20):
            ticket = await priority_queues.dequeue()
            if ticket:
                ticket_id = ticket["ticket_id"]
                if ticket_id.startswith("critical"):
                    queue_counts["CRITICAL"] += 1
                elif ticket_id.startswith("high"):
                    queue_counts["HIGH"] += 1
                elif ticket_id.startswith("normal"):
                    queue_counts["NORMAL"] += 1
                elif ticket_id.startswith("low"):
                    queue_counts["LOW"] += 1

        # Proporção esperada aproximada: CRITICAL=8, HIGH=6, NORMAL=4, LOW=2
        # (total 20, weights 4:3:2:1)
        # Verificar que CRITICAL tem mais tickets que outras filas (devido ao weight 4)
        assert queue_counts["CRITICAL"] >= queue_counts["HIGH"]
        assert queue_counts["HIGH"] >= queue_counts["NORMAL"]
        # Total deve ser 20
        assert sum(queue_counts.values()) == 20

    @pytest.mark.asyncio()
    async def test_critical_preempts_normal(self, priority_queues):
        """Tickets CRITICAL são processados antes de NORMAL."""
        # Enfileirar NORMAL primeiro
        priority_queues.enqueue({"ticket_id": "normal-1"}, 0.5)

        # Enfileirar CRITICAL depois
        priority_queues.enqueue({"ticket_id": "critical-1"}, 0.95)

        # Primeiro dequeue deve ser CRITICAL
        ticket = await priority_queues.dequeue()
        assert ticket["ticket_id"] == "critical-1"

    @pytest.mark.asyncio()
    async def test_high_preempts_low(self, priority_queues):
        """Tickets HIGH são processados antes de LOW."""
        priority_queues.enqueue({"ticket_id": "low-1"}, 0.2)
        priority_queues.enqueue({"ticket_id": "high-1"}, 0.75)

        ticket = await priority_queues.dequeue()
        assert ticket["ticket_id"] == "high-1"

    @pytest.mark.asyncio()
    async def test_fifo_within_same_priority(self, priority_queues):
        """Tickets da mesma prioridade seguem ordem FIFO."""
        # Enfileirar 3 tickets CRITICAL
        for i in range(3):
            priority_queues.enqueue({"ticket_id": f"critical-{i}"}, 0.95)

        # Deve retornar em ordem
        for i in range(3):
            ticket = await priority_queues.dequeue()
            assert ticket["ticket_id"] == f"critical-{i}"


class TestPriorityQueuesPeek:
    """Testes de peek (inspecionar sem remover)."""

    def test_peek_returns_ticket_without_removing(self, priority_queues):
        """Peek retorna ticket sem remover da fila."""
        ticket = {"ticket_id": "test-peek-1"}
        priority_queues.enqueue(ticket, 0.6)  # NORMAL

        # Peek não altera tamanho
        size_before = priority_queues.get_queue_size("NORMAL")
        peeked = priority_queues.peek("NORMAL")
        size_after = priority_queues.get_queue_size("NORMAL")

        assert peeked["ticket_id"] == "test-peek-1"
        assert size_before == size_after == 1

    def test_peek_empty_queue(self, priority_queues):
        """Peek em fila vazia retorna None."""
        result = priority_queues.peek("CRITICAL")
        assert result is None

    def test_peek_multiple_times_same_ticket(self, priority_queues):
        """Peek múltiplas vezes retorna mesmo ticket."""
        ticket = {"ticket_id": "test-peek-2"}
        priority_queues.enqueue(ticket, 0.8)  # HIGH

        peek1 = priority_queues.peek("HIGH")
        peek2 = priority_queues.peek("HIGH")
        peek3 = priority_queues.peek("HIGH")

        assert peek1["ticket_id"] == "test-peek-2"
        assert peek2["ticket_id"] == "test-peek-2"
        assert peek3["ticket_id"] == "test-peek-2"


class TestPriorityQueuesSizes:
    """Testes de obtenção de tamanhos."""

    def test_get_queue_size_single_queue(self, priority_queues):
        """Retorna tamanho correto de fila específica."""
        assert priority_queues.get_queue_size("CRITICAL") == 0

        for i in range(5):
            priority_queues.enqueue({"ticket_id": f"ticket-{i}"}, 0.95)

        assert priority_queues.get_queue_size("CRITICAL") == 5

    def test_get_all_sizes(self, priority_queues):
        """Retorna tamanhos de todas as filas."""
        # Enfileirar tickets
        priority_queues.enqueue({"ticket_id": "c1"}, 0.95)  # CRITICAL
        priority_queues.enqueue({"ticket_id": "h1"}, 0.75)  # HIGH
        priority_queues.enqueue({"ticket_id": "n1"}, 0.5)  # NORMAL
        priority_queues.enqueue({"ticket_id": "n2"}, 0.5)  # NORMAL
        priority_queues.enqueue({"ticket_id": "l1"}, 0.2)  # LOW

        sizes = priority_queues.get_all_sizes()

        assert sizes["CRITICAL"] == 1
        assert sizes["HIGH"] == 1
        assert sizes["NORMAL"] == 2
        assert sizes["LOW"] == 1

    def test_has_pending_tickets(self, priority_queues):
        """Verifica se há tickets pendentes."""
        assert not priority_queues.has_pending_tickets()

        priority_queues.enqueue({"ticket_id": "test-1"}, 0.5)

        assert priority_queues.has_pending_tickets()

    def test_get_total_pending(self, priority_queues):
        """Retorna total de tickets em todas as filas."""
        assert priority_queues.get_total_pending() == 0

        for i in range(3):
            priority_queues.enqueue({"ticket_id": f"ticket-{i}"}, 0.95)  # CRITICAL
        for i in range(2):
            priority_queues.enqueue({"ticket_id": f"ticket-{i}"}, 0.2)  # LOW

        assert priority_queues.get_total_pending() == 5


class TestPriorityQueuesClear:
    """Testes de limpeza de filas."""

    def test_clear_queue(self, priority_queues):
        """Limpa fila específica."""
        # Enfileirar tickets
        for i in range(5):
            priority_queues.enqueue({"ticket_id": f"ticket-{i}"}, 0.95)

        assert priority_queues.get_queue_size("CRITICAL") == 5

        # Limpar
        removed = priority_queues.clear_queue("CRITICAL")

        assert removed == 5
        assert priority_queues.get_queue_size("CRITICAL") == 0

    def test_clear_empty_queue(self, priority_queues):
        """Limpar fila vazia retorna 0."""
        removed = priority_queues.clear_queue("HIGH")
        assert removed == 0

    def test_clear_one_queue_others_untouched(self, priority_queues):
        """Limpar uma fila não afeta as outras."""
        priority_queues.enqueue({"ticket_id": "c1"}, 0.95)  # CRITICAL
        priority_queues.enqueue({"ticket_id": "h1"}, 0.75)  # HIGH

        priority_queues.clear_queue("CRITICAL")

        assert priority_queues.get_queue_size("CRITICAL") == 0
        assert priority_queues.get_queue_size("HIGH") == 1


class TestPriorityQueuesRiskMapping:
    """Testes de mapeamento de risk_band para fila."""

    def test_map_critical_risk_band(self, priority_queues):
        """risk_band='critical' mapeia para CRITICAL."""
        level = priority_queues.map_risk_band_to_queue("critical")
        assert level == PriorityLevel.CRITICAL

    def test_map_high_risk_band(self, priority_queues):
        """risk_band='high' mapeia para HIGH."""
        level = priority_queues.map_risk_band_to_queue("high")
        assert level == PriorityLevel.HIGH

    def test_map_high_risk_with_urgent_sla(self, priority_queues):
        """risk_band='high' com sla_urgency > 0.8 mapeia para CRITICAL."""
        level = priority_queues.map_risk_band_to_queue("high", sla_urgency=0.9)
        assert level == PriorityLevel.CRITICAL

    def test_map_low_risk_band(self, priority_queues):
        """risk_band='low' mapeia para LOW."""
        level = priority_queues.map_risk_band_to_queue("low")
        assert level == PriorityLevel.LOW

    def test_map_normal_risk_band(self, priority_queues):
        """risk_band='normal' mapeia para NORMAL."""
        level = priority_queues.map_risk_band_to_queue("normal")
        assert level == PriorityLevel.NORMAL

    def test_map_unknown_risk_band(self, priority_queues):
        """risk_band desconhecido mapeia para NORMAL."""
        level = priority_queues.map_risk_band_to_queue("unknown")
        assert level == PriorityLevel.NORMAL

    def test_map_sla_urgency_overrides_risk(self, priority_queues):
        """sla_urgency alta pode elevar prioridade."""
        # risk_band='normal' com sla_urgency alta deve ser HIGH
        level = priority_queues.map_risk_band_to_queue("normal", sla_urgency=0.7)
        assert level == PriorityLevel.HIGH


# Testes QueueManager =========================================================


class TestQueueManagerEnqueue:
    """Testes de enfileiramento no QueueManager."""

    def test_enqueue_ticket_auto_calculates_priority(self, queue_manager, sample_tickets):
        """Enqueue automático calcula prioridade."""
        ticket = sample_tickets["critical"]

        queue_name = queue_manager.enqueue_ticket(ticket)

        assert queue_name == "CRITICAL"
        assert queue_manager.get_total_pending() == 1

    def test_enqueue_ticket_with_explicit_score(self, queue_manager):
        """Enqueue com score explícito não recalcula."""
        ticket = {"ticket_id": "test-explicit"}

        queue_name = queue_manager.enqueue_ticket(ticket, priority_score=0.85)

        assert queue_name == "HIGH"

    def test_enqueue_multiple_tickets(self, queue_manager, sample_tickets):
        """Múltiplos tickets distribuídos corretamente."""
        for ticket in sample_tickets.values():
            queue_manager.enqueue_ticket(ticket)

        sizes = queue_manager.get_queue_sizes()

        # critical -> CRITICAL (score >= 0.9)
        assert sizes["CRITICAL"] == 1
        # high -> NORMAL (score ~0.58, < 0.7 porque sla_urgency é 0.3)
        # normal -> NORMAL (score ~0.47, < 0.7)
        assert sizes["NORMAL"] == 2
        # low -> LOW (score ~0.31, < 0.4)
        assert sizes["LOW"] == 1
        assert queue_manager.get_total_pending() == 4

    def test_enqueue_by_risk(self, queue_manager, sample_tickets):
        """Enqueue por risk_band sem cálculo de score."""
        ticket = sample_tickets["normal"]

        queue_name = queue_manager.enqueue_by_risk(ticket, risk_band="high", sla_urgency=0.3)

        assert queue_name == "HIGH"


class TestQueueManagerDequeue:
    """Testes de desenfileiramento no QueueManager."""

    @pytest.mark.asyncio()
    async def test_get_next_ticket_round_robin(self, queue_manager, sample_tickets):
        """Dequeue usa weighted round-robin."""
        # Enfileirar tickets
        queue_manager.enqueue_ticket(sample_tickets["critical"])
        queue_manager.enqueue_ticket(sample_tickets["high"])
        queue_manager.enqueue_ticket(sample_tickets["normal"])

        # Dequeue deve retornar CRITICAL primeiro
        ticket = await queue_manager.get_next_ticket()
        assert ticket["ticket_id"] == "ticket-critical-001"

    @pytest.mark.asyncio()
    async def test_get_next_ticket_from_specific_queue(self, queue_manager, sample_tickets):
        """Dequeue de fila específica."""
        queue_manager.enqueue_ticket(sample_tickets["normal"])

        ticket = await queue_manager.get_next_ticket(queue_name="NORMAL")

        assert ticket["ticket_id"] == "ticket-normal-001"


class TestQueueManagerUtilities:
    """Testes de utilitários do QueueManager."""

    def test_peek_queue(self, queue_manager, sample_tickets):
        """Peek não remove ticket."""
        queue_manager.enqueue_ticket(sample_tickets["critical"])

        ticket = queue_manager.peek_queue("CRITICAL")

        assert ticket["ticket_id"] == "ticket-critical-001"
        assert queue_manager.get_queue_size("CRITICAL") == 1

    def test_has_pending_tickets(self, queue_manager, sample_tickets):
        """Verifica tickets pendentes."""
        assert not queue_manager.has_pending_tickets()

        queue_manager.enqueue_ticket(sample_tickets["low"])

        assert queue_manager.has_pending_tickets()

    def test_calculate_priority(self, queue_manager, sample_tickets):
        """Calcula priority_score para ticket."""
        ticket = sample_tickets["critical"]

        score = queue_manager.calculate_priority(ticket)

        assert score >= 0.9

    def test_get_queue_statistics(self, queue_manager, sample_tickets):
        """Retorna estatísticas detalhadas."""
        # Enfileirar tickets
        for i, ticket in enumerate(sample_tickets.values()):
            if i < 2:  # Adicionar 2 críticos
                queue_manager.enqueue_ticket(ticket)
            else:
                queue_manager.enqueue_ticket(ticket)

        stats = queue_manager.get_queue_statistics()

        assert stats["total_pending"] == 4
        assert "CRITICAL" in stats["queues"]
        assert "weights" in stats
        assert stats["weights"]["CRITICAL"] == 4

    def test_map_risk_to_priority(self, queue_manager):
        """Mapeia risk_band para PriorityLevel."""
        level = queue_manager.map_risk_to_priority("critical")
        assert level == PriorityLevel.CRITICAL

        level = queue_manager.map_risk_to_priority("low", sla_urgency=0.9)
        # low + sla_urgency > 0.5 eleva para HIGH
        assert level == PriorityLevel.HIGH


class TestQueueManagerEdgeCases:
    """Testes de casos extremos no QueueManager."""

    def test_enqueue_ticket_without_risk_band(self, queue_manager):
        """Ticket sem risk_band usa valor default."""
        ticket = {
            "ticket_id": "test-no-risk",
            "qos": {"delivery_mode": "AT_LEAST_ONCE"},
            "sla": {"timeout_ms": 3600000},
        }

        queue_name = queue_manager.enqueue_ticket(ticket)

        # Sem risk_band, score tende a NORMAL
        assert queue_name in ["NORMAL", "HIGH", "LOW"]

    def test_invalid_queue_name_raises_error(self, queue_manager):
        """Nome de fila inválido levanta ValueError."""
        with pytest.raises(ValueError, match="Invalid queue_name"):
            queue_manager.priority_queues.get_queue_size("INVALID")

    @pytest.mark.asyncio()
    async def test_dequeue_empty_manager(self, queue_manager):
        """Dequeue de manager vazio retorna None."""
        ticket = await queue_manager.get_next_ticket()
        assert ticket is None
