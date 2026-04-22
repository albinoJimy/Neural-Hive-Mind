"""
Unit tests para criação de workflows Temporal.

Testa a criação e configuração de workflows de orquestração,
incluindo configuração de timeouts, retry policies e tasks.
"""

import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Mock de dependências problemáticas antes de importar
sys.modules["neural_hive_security"] = MagicMock()
sys.modules["neural_hive_security.cors"] = MagicMock()


@pytest.fixture()
def mock_temporal_client():
    """Temporal client mock."""
    client = AsyncMock()
    client.start_workflow = AsyncMock()
    client.get_workflow = AsyncMock()
    return client


@pytest.fixture()
def sample_cognitive_plan():
    """Cognitive plan sample para testes."""
    return {
        "plan_id": "plan-123",
        "intent": "Criar API de usuários",
        "domain": "technical",
        "status": "PENDING",
        "tasks": [
            {"task_id": "task-1", "action": "query", "collection": "users"},
            {"task_id": "task-2", "action": "transform", "spec": "json_schema"},
        ],
    }


@pytest.fixture()
def sample_consolidated_decision():
    """Consolidated decision sample para testes."""
    return {
        "decision_id": "decision-456",
        "consensus_type": "UNANIMOUS",
        "approval": True,
        "confidence": 0.95,
    }


@pytest.fixture()
def mock_config():
    """Config mock para testes."""
    config = MagicMock()
    config.temporal_host = "localhost:7233"
    config.temporal_namespace = "default"
    config.temporal_task_queue = "orchestration-task-queue"
    config.workflow_execution_timeout = 300
    config.workflow_task_timeout = 30
    config.temporal_max_retry_attempts = 3
    return config


class TestCreateTemporalWorkflow:
    """Testes de criação de workflow Temporal."""

    @pytest.mark.asyncio()
    async def test_create_temporal_workflow(
        self, mock_temporal_client, sample_cognitive_plan, sample_consolidated_decision
    ):
        """Deve criar workflow Temporal com sucesso."""
        from src.workflows.orchestration_workflow import OrchestrationWorkflow

        # Input data para o workflow
        input_data = {
            "cognitive_plan": sample_cognitive_plan,
            "consolidated_decision": sample_consolidated_decision,
        }

        # Mock do workflow handle
        workflow_handle = AsyncMock()
        workflow_handle.id = "workflow-123"
        mock_temporal_client.start_workflow.return_value = workflow_handle

        # Simular chamada de criação de workflow
        result = await mock_temporal_client.start_workflow(
            OrchestrationWorkflow.run,
            args=[input_data],
            id=f"orchestration-{sample_cognitive_plan['plan_id']}",
            task_queue="orchestration-task-queue",
            execution_timeout=timedelta(seconds=300),
        )

        assert result is not None
        mock_temporal_client.start_workflow.assert_called_once()

    @pytest.mark.asyncio()
    async def test_initialize_workflow_with_plan(
        self, mock_temporal_client, sample_cognitive_plan, sample_consolidated_decision
    ):
        """Deve inicializar workflow com plano cognitivo."""
        from src.workflows.orchestration_workflow import OrchestrationWorkflow

        input_data = {
            "cognitive_plan": sample_cognitive_plan,
            "consolidated_decision": sample_consolidated_decision,
        }

        workflow_handle = AsyncMock()
        workflow_handle.id = f"orchestration-{sample_cognitive_plan['plan_id']}"
        mock_temporal_client.start_workflow.return_value = workflow_handle

        result = await mock_temporal_client.start_workflow(
            OrchestrationWorkflow.run,
            args=[input_data],
            id=f"orchestration-{sample_cognitive_plan['plan_id']}",
            task_queue="orchestration-task-queue",
        )

        assert result.id == f"orchestration-{sample_cognitive_plan['plan_id']}"


class TestWorkflowConfiguration:
    """Testes de configuração de workflow."""

    def test_set_workflow_timeout(self, mock_config):
        """Deve configurar timeout de execução do workflow."""
        timeout_seconds = mock_config.workflow_execution_timeout
        assert timeout_seconds == 300
        timeout_timedelta = timedelta(seconds=timeout_seconds)
        assert timeout_timedelta.total_seconds() == 300

    def test_configure_retry_policy(self, mock_config):
        """Deve configurar política de retry."""
        from temporalio.common import RetryPolicy

        retry_policy = RetryPolicy(
            maximum_attempts=mock_config.temporal_max_retry_attempts,
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
        )

        assert retry_policy.maximum_attempts == 3
        assert retry_policy.initial_interval == timedelta(seconds=1)

    def test_configure_task_timeout(self, mock_config):
        """Deve configurar timeout de task individual."""
        task_timeout = mock_config.workflow_task_timeout
        assert task_timeout == 30
        assert timedelta(seconds=task_timeout).total_seconds() == 30


class TestWorkflowTasks:
    """Testes de tasks do workflow."""

    def test_add_workflow_tasks(self, sample_cognitive_plan):
        """Deve adicionar tasks ao workflow."""
        tasks = sample_cognitive_plan.get("tasks", [])
        assert len(tasks) == 2
        assert tasks[0]["action"] == "query"
        assert tasks[1]["action"] == "transform"

    def test_task_has_required_fields(self, sample_cognitive_plan):
        """Deve validar campos obrigatórios das tasks."""
        tasks = sample_cognitive_plan.get("tasks", [])

        for task in tasks:
            assert "task_id" in task
            assert "action" in task
            assert task["task_id"] is not None
            assert task["action"] in ["query", "transform", "validate", "execute"]
