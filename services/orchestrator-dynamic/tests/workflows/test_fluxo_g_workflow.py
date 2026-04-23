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
                        # Setup mock returns como awaitables (13 etapas)
                        mock_execute.side_effect = [
                            make_result({"requirements_set_id": "REQ-SET-001", "plan_id": "PLAN-001", "requirements": []}),  # G1
                            make_result({"documentation_id": "DOC-001", "plan_id": "PLAN-001", "readme": "# README"}),  # G2
                            make_result({"nodes_created": 5, "relations_created": 3}),  # G3
                            make_result({"query": "test", "response": "Test response", "context_used": True}),  # G5
                            make_result({"code_artifact_id": "CODE-001", "language": "python", "framework": "fastapi", "lines_of_code": 1500}),  # G6
                            make_result({"pipeline_id": "BUILD-001", "image_tag": "v1.0.0", "container_image": "service:latest", "quality_score": 0.92}),  # G7
                            make_result({"approved": True, "pass_rate": 1.0}),  # G7 quality validation
                            make_result({"deployment_id": "DEP-001", "service_url": "http://service.nhm.local", "status": "deployed"}),  # G8
                            make_result({"verified": True, "reasons": []}),  # G8 verification
                            make_result({"deployment_id": "DEP-001", "plan_id": "PLAN-001", "workflow_id": "WF-001", "service_url": "http://service.nhm.local", "performance": {"response_time_ms": 150.0}, "reliability": {"uptime_pct": 99.9}, "quality": {"test_coverage": 0.85}, "resource_usage": {"avg_cpu_pct": 35.0}, "health_status": "healthy"}),  # G9
                            make_result({"deployment_id": "DEP-001", "overall_score": 0.87, "status": "good", "scores": {}, "issues": [], "recommendations": []}),  # G10
                            make_result({"needs_feedback": False, "overall_score": 0.87, "issues_count": 0, "action": "continue_monitoring"}),  # G11
                            make_result({"status": "recorded", "training_example": {"features": {}, "labels": {"success": True}}}),  # G13
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
                        # Setup mock returns incluindo approvals como awaitables (13 etapas)
                        mock_execute.side_effect = [
                            make_result({"requirements_set_id": "REQ-SET-001", "plan_id": "PLAN-001", "requirements": []}),  # G1
                            make_result({"documentation_id": "DOC-001", "plan_id": "PLAN-001", "readme": "# README"}),  # G2
                            make_result({"nodes_created": 5, "relations_created": 3}),  # G3
                            make_result({"request_id": "APPR-001", "status": "approved", "confidence_score": 0.9, "requires_human_review": False}),  # G4 approval 1
                            make_result({"request_id": "APPR-002", "status": "approved", "confidence_score": 0.85, "requires_human_review": False}),  # G4 approval 2
                            make_result({"query": "test", "response": "Test response", "context_used": True}),  # G5
                            make_result({"code_artifact_id": "CODE-001", "language": "python", "framework": "fastapi", "lines_of_code": 1500}),  # G6
                            make_result({"pipeline_id": "BUILD-001", "image_tag": "v1.0.0", "container_image": "service:latest", "quality_score": 0.92}),  # G7
                            make_result({"approved": True, "pass_rate": 1.0}),  # G7 quality validation
                            make_result({"deployment_id": "DEP-001", "service_url": "http://service.nhm.local", "status": "deployed"}),  # G8
                            make_result({"verified": True, "reasons": []}),  # G8 verification
                            make_result({"deployment_id": "DEP-001", "plan_id": "PLAN-001", "workflow_id": "WF-001", "service_url": "http://service.nhm.local", "performance": {"response_time_ms": 150.0}, "reliability": {"uptime_pct": 99.9}, "quality": {"test_coverage": 0.85}, "resource_usage": {"avg_cpu_pct": 35.0}, "health_status": "healthy"}),  # G9
                            make_result({"deployment_id": "DEP-001", "overall_score": 0.87, "status": "good", "scores": {}, "issues": [], "recommendations": []}),  # G10
                            make_result({"needs_feedback": False, "overall_score": 0.87, "issues_count": 0, "action": "continue_monitoring"}),  # G11
                            make_result({"status": "recorded", "training_example": {"features": {}, "labels": {"success": True}}}),  # G13
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
                        # Setup com aprovação que requer humano como awaitables (13 etapas)
                        mock_execute.side_effect = [
                            make_result({"requirements_set_id": "REQ-SET-001", "plan_id": "PLAN-001", "requirements": []}),  # G1
                            make_result({"documentation_id": "DOC-001", "plan_id": "PLAN-001", "readme": "# README"}),  # G2
                            make_result({"nodes_created": 5, "relations_created": 3}),  # G3
                            make_result({"request_id": "APPR-001", "status": "pending", "confidence_score": 0.5, "requires_human_review": True}),  # G4 approval 1 - requer humano
                            make_result({"request_id": "APPR-002", "status": "approved", "confidence_score": 0.9, "requires_human_review": False}),  # G4 approval 2
                            make_result({"query": "test", "response": "Test response", "context_used": True}),  # G5
                            make_result({"code_artifact_id": "CODE-001", "language": "python", "framework": "fastapi", "lines_of_code": 1500}),  # G6
                            make_result({"pipeline_id": "BUILD-001", "image_tag": "v1.0.0", "container_image": "service:latest", "quality_score": 0.92}),  # G7
                            make_result({"approved": True, "pass_rate": 1.0}),  # G7 quality validation
                            make_result({"deployment_id": "DEP-001", "service_url": "http://service.nhm.local", "status": "deployed"}),  # G8
                            make_result({"verified": True, "reasons": []}),  # G8 verification
                            make_result({"deployment_id": "DEP-001", "plan_id": "PLAN-001", "workflow_id": "WF-001", "service_url": "http://service.nhm.local", "performance": {"response_time_ms": 150.0}, "reliability": {"uptime_pct": 99.9}, "quality": {"test_coverage": 0.85}, "resource_usage": {"avg_cpu_pct": 35.0}, "health_status": "healthy"}),  # G9
                            make_result({"deployment_id": "DEP-001", "overall_score": 0.87, "status": "good", "scores": {}, "issues": [], "recommendations": []}),  # G10
                            make_result({"needs_feedback": False, "overall_score": 0.87, "issues_count": 0, "action": "continue_monitoring"}),  # G11
                            make_result({"status": "recorded", "training_example": {"features": {}, "labels": {"success": True}}}),  # G13
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

    async def test_workflow_complete_with_feedback_loop(self, sample_input, mock_tracer):
        """Testa workflow completo com todas as 13 etapas (G1-G13)."""
        sample_input["skip_approvals"] = True
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
                        # Todas as 13 etapas como awaitables
                        mock_execute.side_effect = [
                            make_result({"requirements_set_id": "REQ-001", "plan_id": "PLAN-001", "requirements": []}),  # G1
                            make_result({"documentation_id": "DOC-001", "plan_id": "PLAN-001", "readme": "# README"}),  # G2
                            make_result({"nodes_created": 5, "relations_created": 3}),  # G3
                            make_result({"query": "test", "response": "response", "context_used": True}),  # G5
                            make_result({"code_artifact_id": "CODE-001", "language": "python", "framework": "fastapi", "lines_of_code": 1500}),  # G6
                            make_result({"pipeline_id": "BUILD-001", "image_tag": "v1.0.0", "container_image": "service:latest", "quality_score": 0.92}),  # G7
                            make_result({"approved": True, "pass_rate": 1.0}),  # G7 quality validation
                            make_result({"deployment_id": "DEP-001", "service_url": "http://service.nhm.local", "status": "deployed"}),  # G8
                            make_result({"verified": True, "reasons": []}),  # G8 verification
                            make_result({"deployment_id": "DEP-001", "plan_id": "PLAN-001", "workflow_id": "WF-001", "service_url": "http://service.nhm.local", "performance": {"response_time_ms": 150.0, "error_rate": 0.001}, "reliability": {"uptime_pct": 99.9}, "quality": {"test_coverage": 0.85}, "resource_usage": {"avg_cpu_pct": 35.0}, "health_status": "healthy"}),  # G9
                            make_result({"deployment_id": "DEP-001", "overall_score": 0.87, "status": "good", "scores": {"response_time": 0.9, "error_rate": 0.95, "uptime": 1.0, "test_coverage": 0.85, "cpu_usage": 0.9}, "issues": [], "recommendations": ["Continue monitoring"]}),  # G10
                            make_result({"needs_feedback": False, "overall_score": 0.87, "issues_count": 0, "action": "continue_monitoring"}),  # G11
                            make_result({"status": "recorded", "training_example": {"features": {}, "labels": {"success": True}}}),  # G13
                        ]

                        result = await workflow.run(sample_input)

                        # Verificar todas as etapas
                        assert result["status"] == "completed"
                        assert result["plan_id"] == "PLAN-001"
                        assert result["requirements"]["set_id"] == "REQ-001"
                        assert result["documentation"]["doc_id"] == "DOC-001"
                        assert result["code_generation"]["artifact_id"] == "CODE-001"
                        assert result["build"]["image_tag"] == "v1.0.0"
                        assert result["deployment"]["service_url"] == "http://service.nhm.local"
                        assert result["post_deployment"]["quality_score"] == 0.87
                        assert result["post_deployment"]["quality_status"] == "good"
                        assert result["feedback_loop"]["needs_feedback"] is False
                        assert result["feedback_loop"]["ml_feedback_recorded"] is True

    async def test_workflow_with_feedback_trigger(self, sample_input, mock_tracer):
        """Testa workflow quando feedback é necessário (baixa qualidade)."""
        sample_input["skip_approvals"] = True
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
                        # Etapas com baixa qualidade no deployment
                        mock_execute.side_effect = [
                            make_result({"requirements_set_id": "REQ-001", "plan_id": "PLAN-001", "requirements": []}),  # G1
                            make_result({"documentation_id": "DOC-001", "plan_id": "PLAN-001", "readme": "# README"}),  # G2
                            make_result({"nodes_created": 5, "relations_created": 3}),  # G3
                            make_result({"query": "test", "response": "response", "context_used": True}),  # G5
                            make_result({"code_artifact_id": "CODE-001", "language": "python", "framework": "fastapi", "lines_of_code": 1500}),  # G6
                            make_result({"pipeline_id": "BUILD-001", "image_tag": "v1.0.0", "container_image": "service:latest", "quality_score": 0.92}),  # G7
                            make_result({"approved": True, "pass_rate": 1.0}),  # G7 quality
                            make_result({"deployment_id": "DEP-001", "service_url": "http://service.nhm.local", "status": "deployed"}),  # G8
                            make_result({"verified": True, "reasons": []}),  # G8 verify
                            make_result({"deployment_id": "DEP-001", "plan_id": "PLAN-001", "workflow_id": "WF-001", "service_url": "http://service.nhm.local", "performance": {"response_time_ms": 800.0, "error_rate": 0.1}, "reliability": {"uptime_pct": 95.0}, "quality": {"test_coverage": 0.5}, "resource_usage": {"avg_cpu_pct": 90.0}, "health_status": "degraded"}),  # G9 métricas ruins
                            make_result({"deployment_id": "DEP-001", "overall_score": 0.4, "status": "needs_improvement", "scores": {}, "issues": ["high_response_time", "high_error_rate", "low_uptime", "low_test_coverage", "high_cpu_usage"], "recommendations": ["Optimize performance", "Fix errors"]}),  # G10
                            make_result({"needs_feedback": True, "overall_score": 0.4, "issues_count": 5, "action": "escalate_immediately", "trigger_reason": "very_low_quality_score"}),  # G11
                            make_result({"priority": "high", "recommendations": ["Fix issues immediately"]}),  # G12
                            make_result({"status": "recorded", "training_example": {"features": {}, "labels": {"success": False}}}),  # G13
                        ]

                        result = await workflow.run(sample_input)

                        # Verificar que feedback foi acionado
                        assert result["status"] == "completed"
                        assert result["post_deployment"]["quality_score"] == 0.4
                        assert result["post_deployment"]["quality_status"] == "needs_improvement"
                        assert len(result["post_deployment"]["issues"]) == 5
                        assert result["feedback_loop"]["needs_feedback"] is True
                        assert result["feedback_loop"]["action"] == "escalate_immediately"
                        assert result["feedback_loop"]["specialist_feedback"] == "high"
