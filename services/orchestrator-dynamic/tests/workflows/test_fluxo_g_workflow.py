"""Tests para FluxoGWorkflow."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from src.workflows.fluxo_g_workflow import FluxoGWorkflow


@pytest.fixture()
def sample_input():
    """Input de exemplo para Fluxo G."""
    return {
        "cognitive_plan": {
            "plan_id": "PLAN-001",
            "intent_id": "INTENT-001",
            "summary": "Sistema de autenticação",
            "description": "Implementar login e registro",
        },
        "original_intent": "Preciso de um sistema de login",
        "consolidated_decision": {
            "decision_id": "DEC-001",
            "status": "approved",
        },
        "skip_approvals": True,  # Para testes mais rápidos
    }


@pytest.fixture()
def mock_tracer():
    """Mock do tracer OpenTelemetry."""
    tracer = MagicMock()
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    span.start_as_current_span = MagicMock(return_value=span)
    span.add_event = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=span)
    return tracer


@pytest.mark.asyncio()
class TestFluxoGWorkflow:
    """Testes para FluxoGWorkflow."""

    async def test_workflow_initialization(self):
        """Testa inicialização do workflow."""
        workflow = FluxoGWorkflow()

        assert workflow._status == "initializing"
        assert workflow._requirements_set is None
        assert workflow._documentation is None
        assert workflow._approvals == []

    async def test_workflow_skip_approvals(self, sample_input, mock_tracer):
        """Testa workflow pulando aprovações."""
        workflow = FluxoGWorkflow()

        # Mock activities
        with patch("src.workflows.fluxo_g_workflow.workflow") as mock_workflow:
            mock_workflow.info.return_value = MagicMock()
            mock_workflow.now = MagicMock(return_value=datetime.utcnow())
            mock_workflow.logger = MagicMock()

            with patch("src.workflows.fluxo_g_workflow.get_tracer", return_value=mock_tracer):
                with patch("src.workflows.fluxo_g_workflow.set_baggage"):
                    # Helper para criar awaitables
                    async def make_result(value):
                        return value

                    with patch(
                        "src.workflows.fluxo_g_workflow.workflow.execute_activity"
                    ) as mock_execute:
                        # Setup mock returns como awaitables
                        mock_execute.side_effect = [
                            make_result(
                                {  # G1: generate_requirements
                                    "requirements_set_id": "REQ-SET-001",
                                    "plan_id": "PLAN-001",
                                    "requirements": [],
                                }
                            ),
                            make_result(
                                {  # G2: generate_documentation
                                    "documentation_id": "DOC-001",
                                    "plan_id": "PLAN-001",
                                    "readme": "# README",
                                }
                            ),
                            make_result(
                                {  # G3: update_knowledge_graph
                                    "nodes_created": 5,
                                    "relations_created": 3,
                                }
                            ),
                            make_result(
                                {  # G5: query_knowledge_graph
                                    "query": "test",
                                    "response": "Test response",
                                    "context_used": True,
                                }
                            ),
                        ]

                        result = await workflow.run(sample_input)

                        # Verificar resultado
                        assert result["plan_id"] == "PLAN-001"
                        assert result["status"] == "completed"
                        assert result["approvals"] == "skipped"
                        assert result["requirements"]["set_id"] == "REQ-SET-001"
                        assert result["documentation"]["doc_id"] == "DOC-001"

    async def test_workflow_with_approvals(self, sample_input, mock_tracer):
        """Testa workflow com aprovações habilitadas."""
        sample_input["skip_approvals"] = False
        workflow = FluxoGWorkflow()

        with patch("src.workflows.fluxo_g_workflow.workflow") as mock_workflow:
            mock_workflow.info.return_value = MagicMock()
            mock_workflow.now = MagicMock(return_value=datetime.utcnow())
            mock_workflow.logger = MagicMock()

            with patch("src.workflows.fluxo_g_workflow.get_tracer", return_value=mock_tracer):
                with patch("src.workflows.fluxo_g_workflow.set_baggage"):

                    async def make_result(value):
                        return value

                    with patch(
                        "src.workflows.fluxo_g_workflow.workflow.execute_activity"
                    ) as mock_execute:
                        # Setup mock returns incluindo approvals como awaitables
                        mock_execute.side_effect = [
                            make_result(
                                {  # G1: generate_requirements
                                    "requirements_set_id": "REQ-SET-001",
                                    "plan_id": "PLAN-001",
                                    "requirements": [],
                                }
                            ),
                            make_result(
                                {  # G2: generate_documentation
                                    "documentation_id": "DOC-001",
                                    "plan_id": "PLAN-001",
                                    "readme": "# README",
                                }
                            ),
                            make_result(
                                {  # G3: update_knowledge_graph
                                    "nodes_created": 5,
                                    "relations_created": 3,
                                }
                            ),
                            make_result(
                                {  # G4: request_approval (requirement)
                                    "request_id": "APPR-001",
                                    "status": "approved",
                                    "confidence_score": 0.9,
                                    "requires_human_review": False,
                                }
                            ),
                            make_result(
                                {  # G4: request_approval (documentation)
                                    "request_id": "APPR-002",
                                    "status": "approved",
                                    "confidence_score": 0.85,
                                    "requires_human_review": False,
                                }
                            ),
                            make_result(
                                {  # G5: query_knowledge_graph
                                    "query": "test",
                                    "response": "Test response",
                                    "context_used": True,
                                }
                            ),
                        ]

                        result = await workflow.run(sample_input)

                        # Verificar que approvals foram processados
                        assert len(result["approvals"]) == 2
                        assert result["approvals"][0]["type"] == "requirement"
                        assert result["approvals"][1]["type"] == "documentation"

    async def test_workflow_human_review_required(self, sample_input, mock_tracer):
        """Testa workflow quando aprovação requer humano."""
        sample_input["skip_approvals"] = False
        workflow = FluxoGWorkflow()

        with patch("src.workflows.fluxo_g_workflow.workflow") as mock_workflow:
            mock_workflow.info.return_value = MagicMock()
            mock_workflow.warning = MagicMock()
            mock_workflow.now = MagicMock(return_value=datetime.utcnow())
            mock_workflow.logger = MagicMock()

            with patch("src.workflows.fluxo_g_workflow.get_tracer", return_value=mock_tracer):
                with patch("src.workflows.fluxo_g_workflow.set_baggage"):

                    async def make_result(value):
                        return value

                    with patch(
                        "src.workflows.fluxo_g_workflow.workflow.execute_activity"
                    ) as mock_execute:
                        # Setup com aprovação que requer humano como awaitables
                        mock_execute.side_effect = [
                            make_result(
                                {  # G1: generate_requirements
                                    "requirements_set_id": "REQ-SET-001",
                                    "plan_id": "PLAN-001",
                                    "requirements": [],
                                }
                            ),
                            make_result(
                                {  # G2: generate_documentation
                                    "documentation_id": "DOC-001",
                                    "plan_id": "PLAN-001",
                                    "readme": "# README",
                                }
                            ),
                            make_result(
                                {  # G3: update_knowledge_graph
                                    "nodes_created": 5,
                                    "relations_created": 3,
                                }
                            ),
                            make_result(
                                {  # G4: request_approval (requirement) - requer humano
                                    "request_id": "APPR-001",
                                    "status": "pending",
                                    "confidence_score": 0.5,
                                    "requires_human_review": True,
                                }
                            ),
                            make_result(
                                {  # G4: request_approval (documentation)
                                    "request_id": "APPR-002",
                                    "status": "approved",
                                    "confidence_score": 0.9,
                                    "requires_human_review": False,
                                }
                            ),
                            make_result(
                                {  # G5: query_knowledge_graph
                                    "query": "test",
                                    "response": "Test response",
                                    "context_used": True,
                                }
                            ),
                        ]

                        result = await workflow.run(sample_input)

                        # Workflow deve completar mesmo com revisão humana pendente
                        assert result["status"] == "completed"
                        assert len(result["approvals"]) == 2
                        # Verificar que warning foi logado no logger
                        assert mock_workflow.logger.warning.called

    def test_workflow_properties(self):
        """Testa propriedades do workflow."""
        workflow = FluxoGWorkflow()

        assert hasattr(workflow, "_status")
        assert hasattr(workflow, "_requirements_set")
        assert hasattr(workflow, "_documentation")
        assert hasattr(workflow, "_approvals")
        assert hasattr(workflow, "_workflow_result")
