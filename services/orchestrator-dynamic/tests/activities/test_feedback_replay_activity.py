"""
Tests for FeedbackReplayActivity.
"""

from unittest.mock import patch

import pytest
from src.services.feedback_replay_service import FeedbackReplayService, ReplayPriority


@pytest.fixture()
def mock_service():
    """Retorna instância do serviço de feedback replay."""
    with patch("src.activities.feedback_replay_activity.get_feedback_replay_service") as mock:
        service = FeedbackReplayService()
        mock.return_value = service
        yield service


class TestRegisterFailedWorkflowForReplay:
    """Testes para register_failed_workflow_for_replay activity."""

    @pytest.mark.asyncio()
    async def test_register_success(self, mock_service):
        """Testa registro bem-sucedido."""
        from src.activities.feedback_replay_activity import (
            register_failed_workflow_for_replay,
        )

        result = await register_failed_workflow_for_replay(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model prediction failed",
            model_version="v1.0.0",
            plan_id="plan-789",
            priority="high",
            estimated_impact=0.8,
        )

        assert result["status"] == "registered"
        assert result["workflow_id"] == "wf-123"

    @pytest.mark.asyncio()
    async def test_register_invalid_priority(self, mock_service):
        """Testa registro com prioridade inválida (usa default)."""
        from src.activities.feedback_replay_activity import (
            register_failed_workflow_for_replay,
        )

        result = await register_failed_workflow_for_replay(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority="invalid",  # Deve usar MEDIUM como default
        )

        assert result["status"] == "registered"


class TestCheckModelImprovement:
    """Testes para check_model_improvement activity."""

    @pytest.mark.asyncio()
    async def test_significant_improvement(self, mock_service):
        """Testa detecção de melhoria significativa."""
        from src.activities.feedback_replay_activity import check_model_improvement

        result = await check_model_improvement(
            old_model_version="v1.0.0",
            new_model_version="v2.0.0",
            metrics_old={"accuracy": 0.7, "f1_score": 0.65},
            metrics_new={"accuracy": 0.9, "f1_score": 0.85},
        )

        assert result["improvement_level"] == "significant"

    @pytest.mark.asyncio()
    async def test_no_improvement(self, mock_service):
        """Testa sem melhoria."""
        from src.activities.feedback_replay_activity import check_model_improvement

        result = await check_model_improvement(
            old_model_version="v1.0.0",
            new_model_version="v2.0.0",
            metrics_old={"accuracy": 0.7},
            metrics_new={"accuracy": 0.7},
        )

        assert result["improvement_level"] == "none"


class TestOnModelUpdatedTriggerReplay:
    """Testes para on_model_updated_trigger_replay activity."""

    @pytest.mark.asyncio()
    async def test_trigger_with_pending_replays(self, mock_service):
        """Testa trigger com replays pendentes."""
        from src.activities.feedback_replay_activity import (
            on_model_updated_trigger_replay,
        )

        # Registrar workflow pendente
        await mock_service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model prediction failed",
            model_version="v1.0.0",
        )

        result = await on_model_updated_trigger_replay(
            new_model_version="v2.0.0",
            metrics_old={"accuracy": 0.7},
            metrics_new={"accuracy": 0.9},  # Melhoria significativa
            max_concurrent=10,
        )

        assert result["status"] == "replay_scheduled"
        assert result["scheduled_count"] == 1
        assert "wf-123" in result["workflows"]

    @pytest.mark.asyncio()
    async def test_trigger_no_improvement(self, mock_service):
        """Testa trigger sem melhoria suficiente."""
        from src.activities.feedback_replay_activity import (
            on_model_updated_trigger_replay,
        )

        result = await on_model_updated_trigger_replay(
            new_model_version="v2.0.0",
            metrics_old={"accuracy": 0.7},
            metrics_new={"accuracy": 0.72},  # Pequena melhoria
        )

        assert result["status"] == "no_replay"


class TestScheduleWorkflowReplay:
    """Testes para schedule_workflow_replay activity."""

    @pytest.mark.asyncio()
    async def test_schedule_success(self, mock_service):
        """Testa agendamento bem-sucedido."""
        from src.activities.feedback_replay_activity import schedule_workflow_replay

        # Registrar workflow pendente
        await mock_service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await schedule_workflow_replay(
            workflow_id="wf-123",
            original_run_id="run-456",
            new_model_version="v2.0.0",
        )

        assert result["workflow_id"] == "wf-123"
        assert result["new_model_version"] == "v2.0.0"
        assert "new_run_id" in result

    @pytest.mark.asyncio()
    async def test_schedule_not_found(self, mock_service):
        """Testa agendamento de workflow não encontrado."""
        from src.activities.feedback_replay_activity import schedule_workflow_replay
        from temporalio.exceptions import ApplicationError

        with pytest.raises(ApplicationError):
            await schedule_workflow_replay(
                workflow_id="wf-inexistente",
                original_run_id="run-456",
                new_model_version="v2.0.0",
            )


class TestRecordReplayResult:
    """Testes para record_replay_result activity."""

    @pytest.mark.asyncio()
    async def test_record_success(self, mock_service):
        """Testa registro de replay bem-sucedido."""
        from src.activities.feedback_replay_activity import record_replay_result

        # Registrar workflow
        await mock_service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await record_replay_result(
            workflow_id="wf-123",
            replay_id="replay-1",
            success=True,
            result={"status": "completed"},
        )

        assert result["status"] == "recorded"
        assert result["success"] is True

    @pytest.mark.asyncio()
    async def test_record_failure(self, mock_service):
        """Testa registro de replay falhado."""
        from src.activities.feedback_replay_activity import record_replay_result

        # Registrar workflow
        await mock_service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await record_replay_result(
            workflow_id="wf-123",
            replay_id="replay-1",
            success=False,
            result={"error": "failed again"},
        )

        assert result["status"] == "recorded"
        assert result["success"] is False


class TestGetPendingReplays:
    """Testes para get_pending_replays activity."""

    @pytest.mark.asyncio()
    async def test_get_all_pending(self, mock_service):
        """Testa busca de todos os pendentes."""
        from src.activities.feedback_replay_activity import get_pending_replays

        # Registrar workflows
        await mock_service.register_failed_workflow(
            workflow_id="wf-1",
            run_id="run-1",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.HIGH,
        )
        await mock_service.register_failed_workflow(
            workflow_id="wf-2",
            run_id="run-2",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.LOW,
        )

        result = await get_pending_replays()

        assert result["count"] == 2
        assert len(result["pending"]) == 2

    @pytest.mark.asyncio()
    async def test_get_filtered_by_priority(self, mock_service):
        """Testa filtro por prioridade."""
        from src.activities.feedback_replay_activity import get_pending_replays

        # Registrar workflows
        await mock_service.register_failed_workflow(
            workflow_id="wf-1",
            run_id="run-1",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.HIGH,
        )
        await mock_service.register_failed_workflow(
            workflow_id="wf-2",
            run_id="run-2",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.LOW,
        )

        result = await get_pending_replays(priority="high")

        assert result["count"] == 1
        assert result["pending"][0]["workflow_id"] == "wf-1"


class TestGetReplayMetrics:
    """Testes para get_replay_metrics activity."""

    @pytest.mark.asyncio()
    async def test_get_metrics(self, mock_service):
        """Testa busca de métricas."""
        from src.activities.feedback_replay_activity import get_replay_metrics

        # Registrar alguns workflows
        await mock_service.register_failed_workflow(
            workflow_id="wf-1",
            run_id="run-1",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await get_replay_metrics()

        assert "metrics" in result
        assert result["metrics"]["queue_size"] == 1


class TestCheckReplayEligibility:
    """Testes para check_replay_eligibility activity."""

    @pytest.mark.asyncio()
    async def test_eligible_model_related(self):
        """Testa elegibilidade para erro de modelo."""
        from src.activities.feedback_replay_activity import check_replay_eligibility

        result = await check_replay_eligibility(
            workflow_id="wf-123",
            run_id="run-456",
            error_message="Model prediction confidence too low",
            model_version="v1.0.0",
        )

        assert result["eligible"] is True
        assert result["recommended_action"] == "register_for_replay"

    @pytest.mark.asyncio()
    async def test_not_eligible_timeout(self):
        """Testa não elegibilidade para timeout."""
        from src.activities.feedback_replay_activity import check_replay_eligibility

        result = await check_replay_eligibility(
            workflow_id="wf-123",
            run_id="run-456",
            error_message="Task timed out",
            model_version="v1.0.0",
        )

        assert result["eligible"] is False
        assert result["recommended_action"] == "standard_retry"

    @pytest.mark.asyncio()
    async def test_not_eligible_no_model(self):
        """Testa não elegibilidade sem versão de modelo."""
        from src.activities.feedback_replay_activity import check_replay_eligibility

        result = await check_replay_eligibility(
            workflow_id="wf-123",
            run_id="run-456",
            error_message="Model prediction failed",
            model_version="unknown",
        )

        assert result["eligible"] is False
        assert result["reason"]["has_valid_model"] is False
