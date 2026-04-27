"""
Tests for FeedbackReplayService.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.services.feedback_replay_service import (
    FeedbackReplayService,
    ModelImprovement,
    PendingReplay,
    ReplayPriority,
    ReplayStatus,
)


@pytest.fixture(autouse=True)
def mock_tracer():
    """Mock tracer para evitar erros de None."""
    with patch("src.services.feedback_replay_service.get_tracer") as mock:
        tracer = MagicMock()
        mock.return_value = tracer
        yield tracer


class TestPendingReplay:
    """Testes para PendingReplay."""

    def test_creation(self):
        """Testa criação de PendingReplay."""
        pending = PendingReplay(
            workflow_id="wf-123",
            original_run_id="run-456",
            failure_reason="Model prediction failed",
            model_version_at_failure="v1.0.0",
            plan_id="plan-789",
            priority=ReplayPriority.HIGH,
            estimated_impact=0.8,
        )

        assert pending.workflow_id == "wf-123"
        assert pending.original_run_id == "run-456"
        assert pending.failure_reason == "Model prediction failed"
        assert pending.model_version_at_failure == "v1.0.0"
        assert pending.priority == ReplayPriority.HIGH
        assert pending.estimated_impact == 0.8
        assert pending.status == ReplayStatus.PENDING

    def test_to_dict(self):
        """Testa conversão para dict."""
        pending = PendingReplay(
            workflow_id="wf-123",
            original_run_id="run-456",
            failure_reason="Model timeout",
            model_version_at_failure="v1.0.0",
        )

        data = pending.to_dict()

        assert data["workflow_id"] == "wf-123"
        assert data["original_run_id"] == "run-456"
        assert data["status"] == "pending"
        assert data["priority"] == "medium"  # default
        assert "created_at" in data


class TestFeedbackReplayService:
    """Testes para FeedbackReplayService."""

    @pytest.fixture()
    def service(self):
        """Retorna instância do serviço."""
        return FeedbackReplayService()

    @pytest.mark.asyncio()
    async def test_register_failed_workflow(self, service):
        """Testa registro de workflow falhado."""
        result = await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model prediction failed",
            model_version="v1.0.0",
            plan_id="plan-789",
            priority=ReplayPriority.HIGH,
        )

        assert result["status"] == "registered"
        assert result["workflow_id"] == "wf-123"
        assert "wf-123" in service._pending_replays

    @pytest.mark.asyncio()
    async def test_register_duplicate_workflow(self, service):
        """Testa registro de workflow duplicado."""
        await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-789",
            failure_reason="Model failed again",
            model_version="v1.0.0",
        )

        assert result["status"] == "already_registered"

    @pytest.mark.asyncio()
    async def test_check_model_improvement_significant(self, service):
        """Testa detecção de melhoria significativa."""
        metrics_old = {"accuracy": 0.7, "f1_score": 0.65}
        metrics_new = {"accuracy": 0.9, "f1_score": 0.85}

        improvement = await service.check_model_improvement(
            old_model_version="v1.0.0",
            new_model_version="v2.0.0",
            metrics_old=metrics_old,
            metrics_new=metrics_new,
        )

        assert improvement == ModelImprovement.SIGNIFICANT

    @pytest.mark.asyncio()
    async def test_check_model_improvement_moderate(self, service):
        """Testa detecção de melhoria moderada."""
        metrics_old = {"accuracy": 0.7, "f1_score": 0.65}
        metrics_new = {"accuracy": 0.8, "f1_score": 0.72}

        improvement = await service.check_model_improvement(
            old_model_version="v1.0.0",
            new_model_version="v2.0.0",
            metrics_old=metrics_old,
            metrics_new=metrics_new,
        )

        assert improvement == ModelImprovement.MODERATE

    @pytest.mark.asyncio()
    async def test_check_model_improvement_none(self, service):
        """Testa detecção sem melhoria."""
        metrics_old = {"accuracy": 0.7, "f1_score": 0.65}
        metrics_new = {"accuracy": 0.7, "f1_score": 0.65}

        improvement = await service.check_model_improvement(
            old_model_version="v1.0.0",
            new_model_version="v2.0.0",
            metrics_old=metrics_old,
            metrics_new=metrics_new,
        )

        assert improvement == ModelImprovement.NONE

    @pytest.mark.asyncio()
    async def test_check_model_regression(self, service):
        """Testa detecção de regressão."""
        metrics_old = {"accuracy": 0.8, "f1_score": 0.75}
        metrics_new = {"accuracy": 0.6, "f1_score": 0.55}

        improvement = await service.check_model_improvement(
            old_model_version="v1.0.0",
            new_model_version="v2.0.0",
            metrics_old=metrics_old,
            metrics_new=metrics_new,
        )

        assert improvement == ModelImprovement.REGRESSION

    @pytest.mark.asyncio()
    async def test_on_model_updated_no_replay(self, service):
        """Testa callback sem melhoria suficiente."""
        metrics_old = {"accuracy": 0.7}
        metrics_new = {"accuracy": 0.72}  # Pequena melhoria

        result = await service.on_model_updated(
            new_model_version="v2.0.0",
            metrics_old=metrics_old,
            metrics_new=metrics_new,
        )

        assert result["status"] == "no_replay"

    @pytest.mark.asyncio()
    async def test_on_model_updated_with_replay(self, service):
        """Testa callback com melhoria suficiente."""
        # Registrar workflow falhado
        await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model prediction failed",
            model_version="v1.0.0",
            priority=ReplayPriority.HIGH,
        )

        metrics_old = {"accuracy": 0.7}
        metrics_new = {"accuracy": 0.9}  # Melhoria significativa

        result = await service.on_model_updated(
            new_model_version="v2.0.0",
            metrics_old=metrics_old,
            metrics_new=metrics_new,
        )

        assert result["status"] == "replay_scheduled"
        assert result["scheduled_count"] == 1
        assert "wf-123" in result["workflows"]

    @pytest.mark.asyncio()
    async def test_record_replay_result_success(self, service):
        """Testa registro de replay bem-sucedido."""
        # Registrar workflow
        await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await service.record_replay_result(
            workflow_id="wf-123",
            replay_id="replay-1",
            success=True,
            result={"status": "completed"},
        )

        assert result["status"] == "recorded"
        assert result["success"] is True
        # Workflow deve ter sido removido da fila
        assert "wf-123" not in service._pending_replays

    @pytest.mark.asyncio()
    async def test_record_replay_result_failure(self, service):
        """Testa registro de replay falhado."""
        # Registrar workflow
        await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        result = await service.record_replay_result(
            workflow_id="wf-123",
            replay_id="replay-1",
            success=False,
            result={"error": "failed again"},
        )

        assert result["status"] == "recorded"
        assert result["success"] is False
        # Workflow ainda deve estar na fila (tem tentativas restantes)
        assert "wf-123" in service._pending_replays

    def test_get_pending_replays(self, service):
        """Testa busca de replays pendentes."""
        # Adicionar alguns pendentes
        service._pending_replays["wf-1"] = PendingReplay(
            workflow_id="wf-1",
            original_run_id="run-1",
            failure_reason="Model failed",
            model_version_at_failure="v1.0.0",
            priority=ReplayPriority.CRITICAL,
        )
        service._pending_replays["wf-2"] = PendingReplay(
            workflow_id="wf-2",
            original_run_id="run-2",
            failure_reason="Model failed",
            model_version_at_failure="v1.0.0",
            priority=ReplayPriority.LOW,
        )

        pending = service.get_pending_replays()

        assert len(pending) == 2
        # CRITICAL deve vir antes de LOW
        assert pending[0]["workflow_id"] == "wf-1"
        assert pending[1]["workflow_id"] == "wf-2"

    def test_get_pending_replays_filtered_by_priority(self, service):
        """Testa filtro de replays por prioridade."""
        service._pending_replays["wf-1"] = PendingReplay(
            workflow_id="wf-1",
            original_run_id="run-1",
            failure_reason="Model failed",
            model_version_at_failure="v1.0.0",
            priority=ReplayPriority.HIGH,
        )
        service._pending_replays["wf-2"] = PendingReplay(
            workflow_id="wf-2",
            original_run_id="run-2",
            failure_reason="Model failed",
            model_version_at_failure="v1.0.0",
            priority=ReplayPriority.LOW,
        )

        high_priority = service.get_pending_replays(priority=ReplayPriority.HIGH)

        assert len(high_priority) == 1
        assert high_priority[0]["workflow_id"] == "wf-1"

    def test_get_metrics(self, service):
        """Testa busca de métricas."""
        service._pending_replays["wf-1"] = PendingReplay(
            workflow_id="wf-1",
            original_run_id="run-1",
            failure_reason="Model failed",
            model_version_at_failure="v1.0.0",
            priority=ReplayPriority.HIGH,
        )

        metrics = service.get_metrics()

        assert metrics["queue_size"] == 1
        assert metrics["total_pending"] == 1
        assert metrics["by_priority"]["high"] == 1

    @pytest.mark.asyncio()
    async def test_evict_lowest_priority(self, service):
        """Testa remoção de menor prioridade quando fila cheia."""
        # Criar serviço com fila pequena
        small_service = FeedbackReplayService(replay_queue_size=3)

        # Adicionar 3 workflows
        await small_service.register_failed_workflow(
            workflow_id="wf-1",
            run_id="run-1",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.CRITICAL,
        )
        await small_service.register_failed_workflow(
            workflow_id="wf-2",
            run_id="run-2",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.MEDIUM,
        )
        await small_service.register_failed_workflow(
            workflow_id="wf-3",
            run_id="run-3",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.LOW,
        )

        assert len(small_service._pending_replays) == 3

        # Adicionar quarto (deve evictar LOW)
        await small_service.register_failed_workflow(
            workflow_id="wf-4",
            run_id="run-4",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority=ReplayPriority.HIGH,
        )

        # Fila deve ter tamanho máximo de 3
        assert len(small_service._pending_replays) == 3
        # LOW priority deve ter sido removido
        assert "wf-3" not in small_service._pending_replays
        # Novo workflow deve estar presente
        assert "wf-4" in small_service._pending_replays

    @pytest.mark.asyncio()
    async def test_max_replay_attempts_exceeded(self, service):
        """Testa que workflow é removido após max tentativas."""
        await service.register_failed_workflow(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
        )

        # Agendar e falhar 3 vezes (max padrão)
        for i in range(3):
            # Agendar replay (adiciona a replay_attempts)
            pending = service._pending_replays.get("wf-123")
            await service._schedule_replay(pending, f"v{i+1}.0.0")
            # Registrar falha
            await service.record_replay_result(
                workflow_id="wf-123",
                replay_id=f"replay-wf-123-v{i+1}.0.0",
                success=False,
                result={"error": "failed"},
            )

        # Workflow deve ter sido removido após exceder tentativas
        assert "wf-123" not in service._pending_replays
