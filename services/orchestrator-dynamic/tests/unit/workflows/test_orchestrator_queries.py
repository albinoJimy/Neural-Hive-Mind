"""
Testes unitários para queries do OrchestrationWorkflow.

Testa os métodos @workflow.query que expõem estado do workflow.
"""

import pytest
from src.workflows.orchestration_workflow import OrchestrationWorkflow


class TestOrchestrationWorkflowQueries:
    """Testes para queries do OrchestrationWorkflow."""

    @pytest.fixture()
    def workflow(self):
        """Retorna instância do workflow para testes."""
        return OrchestrationWorkflow()

    @pytest.fixture()
    def sample_tickets(self):
        """Retorna lista de tickets de exemplo."""
        return [
            {
                "ticket_id": "ticket-001",
                "task_type": "query",
                "status": "COMPLETED",
                "risk_band": "normal",
            },
            {
                "ticket_id": "ticket-002",
                "task_type": "transform",
                "status": "COMPLETED",
                "risk_band": "high",
            },
            {
                "ticket_id": "ticket-003",
                "task_type": "validate",
                "status": "PENDING",
                "risk_band": "low",
            },
            {
                "ticket_id": "ticket-004",
                "task_type": "analyze",
                "status": "IN_PROGRESS",
                "risk_band": "normal",
            },
        ]

    @pytest.fixture()
    def rejected_tickets(self):
        """Retorna lista de tickets rejeitados."""
        return [{"ticket_id": "ticket-rejected-001", "rejection_reason": "resource_unavailable"}]

    def test_get_saga_state_initial(self, workflow):
        """Testa get_saga_state no estado inicial."""
        state = workflow.get_saga_state()

        assert state["saga_id"] is None
        assert state["status"] == "initializing"
        assert state["steps"] == []
        assert state["compensation_order"] == []
        assert state["completed_steps"] == []
        assert state["pending_steps"] == []
        assert state["rejected_tickets"] == []
        assert state["total_steps"] == 0
        assert state["completed_count"] == 0
        assert state["pending_count"] == 0
        assert state["rejected_count"] == 0

    def test_get_saga_state_with_tickets(self, workflow, sample_tickets, rejected_tickets):
        """Testa get_saga_state com tickets gerados."""
        workflow._tickets_generated = sample_tickets
        workflow._rejected_tickets = rejected_tickets
        workflow._status = "publishing_tickets"
        workflow._saga_id = "saga-123"

        state = workflow.get_saga_state()

        assert state["saga_id"] == "saga-123"
        assert state["status"] == "publishing_tickets"
        assert state["total_steps"] == 4

        # Verificar steps completados
        assert len(state["completed_steps"]) == 2
        assert state["completed_count"] == 2
        completed_ids = {t["ticket_id"] for t in state["completed_steps"]}
        assert "ticket-001" in completed_ids
        assert "ticket-002" in completed_ids

        # Verificar steps pendentes
        assert len(state["pending_steps"]) == 2
        assert state["pending_count"] == 2
        pending_ids = {t["ticket_id"] for t in state["pending_steps"]}
        assert "ticket-003" in pending_ids
        assert "ticket-004" in pending_ids

        # Verificar tickets rejeitados
        assert state["rejected_tickets"] == rejected_tickets
        assert state["rejected_count"] == 1

        # Verificar ordem de compensação (ordem reversa dos completados)
        assert len(state["compensation_order"]) == 2
        # Ordem deve ser reversa: ticket-002, ticket-001
        assert state["compensation_order"] == ["ticket-002", "ticket-001"]

    def test_get_saga_state_compensation_order_calculation(self, workflow):
        """Testa cálculo automático da ordem de compensação."""
        # Tickets com status variados
        tickets = [
            {"ticket_id": "t1", "status": "COMPLETED"},
            {"ticket_id": "t2", "status": "COMPLETED"},
            {"ticket_id": "t3", "status": "FAILED"},
            {"ticket_id": "t4", "status": "COMPLETED"},
        ]

        workflow._tickets_generated = tickets
        workflow._saga_id = "saga-456"

        # Primeira chamada calcula a ordem
        state = workflow.get_saga_state()

        # Apenas completados devem estar na ordem de compensação
        # Ordem reversa: t4, t2, t1
        assert state["compensation_order"] == ["t4", "t2", "t1"]
        assert state["completed_count"] == 3

    def test_get_saga_state_all_pending(self, workflow):
        """Testa get_saga_state quando todos os tickets estão pendentes."""
        tickets = [
            {"ticket_id": "t1", "status": "PENDING"},
            {"ticket_id": "t2", "status": "PENDING"},
        ]

        workflow._tickets_generated = tickets
        workflow._status = "generating_tickets"

        state = workflow.get_saga_state()

        assert state["completed_steps"] == []
        assert state["pending_steps"] == tickets
        assert state["compensation_order"] == []
        assert state["total_steps"] == 2
        assert state["completed_count"] == 0
        assert state["pending_count"] == 2

    def test_get_status_query(self, workflow):
        """Testa query get_status existente."""
        workflow._status = "allocating_resources"
        workflow._sla_warnings = [
            {"checkpoint": "post_ticket_generation", "warning": "SLA warning"}
        ]

        status = workflow.get_status()

        assert status["status"] == "allocating_resources"
        assert "tickets_generated" in status
        assert "workflow_result" in status
        assert status["sla_warnings"] == workflow._sla_warnings

    def test_get_tickets_query(self, workflow, sample_tickets):
        """Testa query get_tickets existente."""
        workflow._tickets_generated = sample_tickets

        tickets = workflow.get_tickets()

        assert tickets == sample_tickets
        assert len(tickets) == 4
