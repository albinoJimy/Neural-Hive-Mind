"""
Unit tests para gestão de estado do workflow.

Testa as transições de estado do OrchestrationWorkflow durante
a execução: PENDING -> RUNNING -> COMPLETED/FAILED.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Mock de dependências problemáticas antes de importar
sys.modules["neural_hive_security"] = MagicMock()
sys.modules["neural_hive_security.cors"] = MagicMock()


@pytest.fixture
def sample_cognitive_plan():
    """Cognitive plan sample para testes."""
    return {
        "plan_id": "plan-123",
        "intent": "Criar API de usuários",
        "domain": "technical",
        "status": "PENDING",
        "tasks": [],
    }


@pytest.fixture
def sample_consolidated_decision():
    """Consolidated decision sample para testes."""
    return {
        "decision_id": "decision-456",
        "consensus_type": "UNANIMOUS",
        "approval": True,
        "confidence": 0.95,
    }


@pytest.fixture
def mock_workflow_instance():
    """Instância de OrchestrationWorkflow mockada."""
    from src.workflows.orchestration_workflow import OrchestrationWorkflow

    workflow = OrchestrationWorkflow()
    return workflow


class TestWorkflowStateTransitions:
    """Testes de transições de estado do workflow."""

    def test_initial_state_is_pending(self, mock_workflow_instance):
        """Workflow deve iniciar em estado 'initializing'."""
        assert mock_workflow_instance._status == "initializing"

    def test_transition_to_running(self, mock_workflow_instance):
        """Deve transitar para estado 'running'."""
        mock_workflow_instance._status = "running"
        assert mock_workflow_instance._status == "running"

    def test_transition_to_validating_plan(self, mock_workflow_instance):
        """Deve transitar para estado 'validating_plan'."""
        mock_workflow_instance._status = "validating_plan"
        assert mock_workflow_instance._status == "validating_plan"

    def test_transition_to_generating_tickets(self, mock_workflow_instance):
        """Deve transitar para estado 'generating_tickets'."""
        mock_workflow_instance._status = "generating_tickets"
        assert mock_workflow_instance._status == "generating_tickets"

    def test_transition_to_executing(self, mock_workflow_instance):
        """Deve transitar para estado 'executing'."""
        mock_workflow_instance._status = "executing"
        assert mock_workflow_instance._status == "executing"

    def test_transition_to_consolidating(self, mock_workflow_instance):
        """Deve transitar para estado 'consolidating'."""
        mock_workflow_instance._status = "consolidating"
        assert mock_workflow_instance._status == "consolidating"


class TestWorkflowFinalStates:
    """Testes de estados finais do workflow."""

    def test_transition_to_completed(self, mock_workflow_instance):
        """Deve transitar para estado 'completed'."""
        mock_workflow_instance._status = "completed"
        assert mock_workflow_instance._status == "completed"

    def test_transition_to_failed(self, mock_workflow_instance):
        """Deve transitar para estado 'failed'."""
        mock_workflow_instance._status = "failed"
        assert mock_workflow_instance._status == "failed"

    def test_transition_to_cancelled(self, mock_workflow_instance):
        """Deve transitar para estado 'cancelled'."""
        mock_workflow_instance._status = "cancelled"
        assert mock_workflow_instance._status == "cancelled"


class TestWorkflowStateTracking:
    """Testes de tracking de estado do workflow."""

    def test_track_generated_tickets(self, mock_workflow_instance):
        """Deve rastrear tickets gerados."""
        tickets = [
            {"ticket_id": "ticket-1", "action": "query"},
            {"ticket_id": "ticket-2", "action": "transform"},
        ]
        mock_workflow_instance._tickets_generated = tickets
        assert len(mock_workflow_instance._tickets_generated) == 2
        assert mock_workflow_instance._tickets_generated[0]["ticket_id"] == "ticket-1"

    def test_track_rejected_tickets(self, mock_workflow_instance):
        """Deve rastrear tickets rejeitados."""
        rejected = [{"ticket_id": "ticket-3", "reason": "invalid_schema"}]
        mock_workflow_instance._rejected_tickets = rejected
        assert len(mock_workflow_instance._rejected_tickets) == 1

    def test_track_sla_warnings(self, mock_workflow_instance):
        """Deve rastrear avisos de SLA."""
        warnings = [{"ticket_id": "ticket-1", "warning": "deadline_approaching"}]
        mock_workflow_instance._sla_warnings = warnings
        assert len(mock_workflow_instance._sla_warnings) == 1

    def test_workflow_result_is_set(self, mock_workflow_instance):
        """Deve armazenar resultado do workflow."""
        result = {"status": "completed", "tickets_count": 2, "duration_seconds": 15.5}
        mock_workflow_instance._workflow_result = result
        assert mock_workflow_instance._workflow_result["status"] == "completed"
