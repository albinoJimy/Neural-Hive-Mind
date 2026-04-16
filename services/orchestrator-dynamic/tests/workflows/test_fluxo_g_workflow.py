"""Tests para FluxoGWorkflow."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.workflows.fluxo_g_workflow import FluxoGWorkflow


@pytest.fixture
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


@pytest.mark.asyncio
class TestFluxoGWorkflow:
    """Testes para FluxoGWorkflow."""

    async def test_workflow_initialization(self):
        """Testa inicialização do workflow."""
        workflow = FluxoGWorkflow()

        assert workflow._status == "initializing"
        assert workflow._requirements_set is None
        assert workflow._documentation is None
        assert workflow._approvals == []

    async def test_workflow_skip_approvals(self, sample_input):
        """Testa workflow pulando aprovações."""
        workflow = FluxoGWorkflow()

        # Mock activities
        with patch("src.workflows.fluxo_g_workflow.workflow") as mock_workflow:
            mock_workflow.info.return_value = MagicMock()
            mock_workflow.now = MagicMock(return_value=datetime.utcnow())

            with patch("src.workflows.fluxo_g_workflow.workflow.execute_activity") as mock_execute:
                # Setup mock returns
                mock_execute.side_effect = [
                    # G1: generate_requirements
                    {
                        "requirements_set_id": "REQ-SET-001",
                        "plan_id": "PLAN-001",
                        "requirements": [],
                    },
                    # G2: generate_documentation
                    {
                        "documentation_id": "DOC-001",
                        "plan_id": "PLAN-001",
                        "readme": "# README",
                    },
                    # G3: update_knowledge_graph
                    {"nodes_created": 5, "relations_created": 3},
                    # G5: query_knowledge_graph
                    {"query": "test", "response": "Test response", "context_used": True},
                ]

                result = await workflow.run(sample_input)

                # Verificar resultado
                assert result["plan_id"] == "PLAN-001"
                assert result["status"] == "completed"
                assert result["approvals"] == "skipped"
                assert result["requirements"]["set_id"] == "REQ-SET-001"
                assert result["documentation"]["doc_id"] == "DOC-001"

    async def test_workflow_with_approvals(self, sample_input):
        """Testa workflow com aprovações habilitadas."""
        sample_input["skip_approvals"] = False
        workflow = FluxoGWorkflow()

        with patch("src.workflows.fluxo_g_workflow.workflow") as mock_workflow:
            mock_workflow.info.return_value = MagicMock()
            mock_workflow.now = MagicMock(return_value=datetime.utcnow())

            with patch("src.workflows.fluxo_g_workflow.workflow.execute_activity") as mock_execute:
                # Setup mock returns incluindo approvals
                mock_execute.side_effect = [
                    # G1: generate_requirements
                    {
                        "requirements_set_id": "REQ-SET-001",
                        "plan_id": "PLAN-001",
                        "requirements": [],
                    },
                    # G2: generate_documentation
                    {
                        "documentation_id": "DOC-001",
                        "plan_id": "PLAN-001",
                        "readme": "# README",
                    },
                    # G3: update_knowledge_graph
                    {"nodes_created": 5, "relations_created": 3},
                    # G4: request_approval (requirement)
                    {
                        "request_id": "APPR-001",
                        "status": "approved",
                        "confidence_score": 0.9,
                        "requires_human_review": False,
                    },
                    # G4: request_approval (documentation)
                    {
                        "request_id": "APPR-002",
                        "status": "approved",
                        "confidence_score": 0.85,
                        "requires_human_review": False,
                    },
                    # G5: query_knowledge_graph
                    {"query": "test", "response": "Test response", "context_used": True},
                ]

                result = await workflow.run(sample_input)

                # Verificar que approvals foram processados
                assert len(result["approvals"]) == 2
                assert result["approvals"][0]["type"] == "requirement"
                assert result["approvals"][1]["type"] == "documentation"

    async def test_workflow_human_review_required(self, sample_input):
        """Testa workflow quando aprovação requer humano."""
        sample_input["skip_approvals"] = False
        workflow = FluxoGWorkflow()

        with patch("src.workflows.fluxo_g_workflow.workflow") as mock_workflow:
            mock_workflow.info.return_value = MagicMock()
            mock_workflow.warning = MagicMock()
            mock_workflow.now = MagicMock(return_value=datetime.utcnow())

            with patch("src.workflows.fluxo_g_workflow.workflow.execute_activity") as mock_execute:
                # Setup com aprovação que requer humano
                mock_execute.side_effect = [
                    # G1: generate_requirements
                    {
                        "requirements_set_id": "REQ-SET-001",
                        "plan_id": "PLAN-001",
                        "requirements": [],
                    },
                    # G2: generate_documentation
                    {
                        "documentation_id": "DOC-001",
                        "plan_id": "PLAN-001",
                        "readme": "# README",
                    },
                    # G3: update_knowledge_graph
                    {"nodes_created": 5, "relations_created": 3},
                    # G4: request_approval (requirement) - requer humano
                    {
                        "request_id": "APPR-001",
                        "status": "pending",
                        "confidence_score": 0.5,
                        "requires_human_review": True,
                    },
                    # G4: request_approval (documentation)
                    {
                        "request_id": "APPR-002",
                        "status": "approved",
                        "confidence_score": 0.9,
                        "requires_human_review": False,
                    },
                    # G5: query_knowledge_graph
                    {"query": "test", "response": "Test response", "context_used": True},
                ]

                result = await workflow.run(sample_input)

                # Workflow deve completar mesmo com revisão humana pendente
                assert result["status"] == "completed"
                assert len(result["approvals"]) == 2
                # Verificar que warning foi logado
                assert mock_workflow.warning.called

    def test_workflow_properties(self):
        """Testa propriedades do workflow."""
        workflow = FluxoGWorkflow()

        assert hasattr(workflow, "_status")
        assert hasattr(workflow, "_requirements_set")
        assert hasattr(workflow, "_documentation")
        assert hasattr(workflow, "_approvals")
        assert hasattr(workflow, "_workflow_result")
