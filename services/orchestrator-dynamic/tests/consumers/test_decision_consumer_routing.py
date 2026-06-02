"""
Tests para Decision Consumer workflow routing logic.

TDD: Tests para a lógica de seleção de workflow baseado em workflow_type.
"""

from unittest.mock import patch

from src.consumers.decision_consumer import (
    _select_workflow_class,
    _get_workflow_type_from_plan,
)


class TestWorkflowTypeExtraction:
    """Tests para extração de workflow_type do CognitivePlan."""

    def test_get_workflow_type_from_plan_orchestration_default(self):
        """Sem workflow_type no plano deve retornar ORCHESTRATION (default)."""
        plan = {
            "plan_id": "test-123",
            "intent_id": "intent-456",
            # Sem workflow_type
        }
        result = _get_workflow_type_from_plan(plan)
        assert result == "orchestration"

    def test_get_workflow_type_from_plan_orchestration_explicit(self):
        """workflow_type=orchestration deve retornar ORCHESTRATION."""
        plan = {
            "plan_id": "test-123",
            "intent_id": "intent-456",
            "workflow_type": "orchestration",
        }
        result = _get_workflow_type_from_plan(plan)
        assert result == "orchestration"

    def test_get_workflow_type_from_plan_generation(self):
        """workflow_type=generation deve retornar GENERATION."""
        plan = {
            "plan_id": "test-123",
            "intent_id": "intent-456",
            "workflow_type": "generation",
        }
        result = _get_workflow_type_from_plan(plan)
        assert result == "generation"


class TestWorkflowClassSelection:
    """Tests para seleção da classe de workflow."""

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_select_workflow_orchestration_type(self, mock_fluxo_g, mock_orchestration):
        """workflow_type=orchestration deve retornar OrchestrationWorkflow."""
        workflow_class = _select_workflow_class("orchestration")
        assert workflow_class == mock_orchestration
        mock_fluxo_g.assert_not_called()

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_select_workflow_generation_type(self, mock_fluxo_g, mock_orchestration):
        """workflow_type=generation deve retornar FluxoGWorkflow."""
        workflow_class = _select_workflow_class("generation")
        assert workflow_class == mock_fluxo_g
        mock_orchestration.assert_not_called()

    @patch("src.consumers.decision_consumer.OrchestrationWorkflow")
    @patch("src.consumers.decision_consumer.FluxoGWorkflow")
    def test_select_workflow_invalid_defaults_to_orchestration(
        self, mock_fluxo_g, mock_orchestration
    ):
        """workflow_type inválido deve default para Orchestration."""
        workflow_class = _select_workflow_class("invalid")
        assert workflow_class == mock_orchestration
        mock_fluxo_g.assert_not_called()
