"""
Tests for FeedbackReplayIntegration.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.ml.feedback_replay_integration import (
    FeedbackReplayIntegration,
    get_feedback_replay_integration,
)
from src.services.feedback_replay_service import ModelImprovement


@pytest.fixture()
def mock_service():
    """Mock do FeedbackReplayService."""

    class MockService:
        async def check_model_improvement(
            self, old_model_version, new_model_version, metrics_old, metrics_new
        ):
            # Simular melhoria significativa se precision aumentar >10%
            old_precision = metrics_old.get("precision", 0)
            new_precision = metrics_new.get("precision", 0)
            if new_precision > old_precision * 1.1:
                return ModelImprovement.SIGNIFICANT
            elif new_precision > old_precision:
                return ModelImprovement.MODERATE
            return ModelImprovement.NONE

        async def on_model_updated(self, new_model_version, metrics_old, metrics_new):
            return {
                "status": "replay_scheduled",
                "improvement": "significant",
                "scheduled_count": 2,
                "workflows": ["wf-1", "wf-2"],
            }

        async def register_failed_workflow(
            self, workflow_id, run_id, failure_reason, model_version, **kwargs
        ):
            return {"status": "registered", "workflow_id": workflow_id}

        def get_metrics(self):
            return {"queue_size": 5, "total_pending": 5}

    return MockService()


@pytest.fixture()
def integration(mock_service):
    """Retorna instância da integração com serviço mockado."""
    with patch(
        "src.ml.feedback_replay_integration.get_feedback_replay_service", return_value=mock_service
    ):
        integration = FeedbackReplayIntegration(enabled=True)
        integration.feedback_replay_service = mock_service
        return integration


class TestFeedbackReplayIntegration:
    """Testes para FeedbackReplayIntegration."""

    @pytest.mark.asyncio()
    async def test_initialize(self):
        """Testa inicialização da integração."""
        with patch("src.ml.feedback_replay_integration.get_feedback_replay_service") as mock_get:
            mock_service = MagicMock()
            mock_get.return_value = mock_service

            integration = FeedbackReplayIntegration(enabled=True)
            await integration.initialize()

            assert integration.feedback_replay_service == mock_service

    @pytest.mark.asyncio()
    async def test_initialize_disabled(self):
        """Testa inicialização com integração desabilitada."""
        integration = FeedbackReplayIntegration(enabled=False)
        await integration.initialize()

        assert integration.feedback_replay_service is None

    @pytest.mark.asyncio()
    async def test_on_model_promoted_significant_improvement(self, integration):
        """Testa replay disparado com melhoria significativa."""
        old_metrics = {"precision": 0.70, "recall": 0.65}
        new_metrics = {"precision": 0.85, "recall": 0.80}

        result = await integration.on_model_promoted(
            model_name="approval-predictor",
            old_version="v1.0.0",
            new_version="v2.0.0",
            old_metrics=old_metrics,
            new_metrics=new_metrics,
        )

        assert result["status"] == "replay_triggered"
        assert result["improvement"] == "significant"
        assert result["replay_result"]["scheduled_count"] == 2

    @pytest.mark.asyncio()
    async def test_on_model_promoted_moderate_improvement(self, integration):
        """Testa replay disparado com melhoria moderada."""
        old_metrics = {"precision": 0.70, "recall": 0.65}
        new_metrics = {"precision": 0.75, "recall": 0.68}

        result = await integration.on_model_promoted(
            model_name="approval-predictor",
            old_version="v1.0.0",
            new_version="v2.0.0",
            old_metrics=old_metrics,
            new_metrics=new_metrics,
        )

        assert result["status"] == "replay_triggered"
        assert result["improvement"] == "moderate"

    @pytest.mark.asyncio()
    async def test_on_model_promoted_no_improvement(self, integration):
        """Testa sem replay quando não há melhoria."""
        old_metrics = {"precision": 0.70, "recall": 0.65}
        new_metrics = {"precision": 0.68, "recall": 0.63}

        result = await integration.on_model_promoted(
            model_name="approval-predictor",
            old_version="v1.0.0",
            new_version="v2.0.0",
            old_metrics=old_metrics,
            new_metrics=new_metrics,
        )

        assert result["status"] == "no_replay"

    @pytest.mark.asyncio()
    async def test_on_model_promoted_disabled(self):
        """Testa skip quando integração desabilitada."""
        integration = FeedbackReplayIntegration(enabled=False)

        result = await integration.on_model_promoted(
            model_name="approval-predictor",
            old_version="v1.0.0",
            new_version="v2.0.0",
            old_metrics={},
            new_metrics={},
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "integration_disabled_or_not_initialized"

    @pytest.mark.asyncio()
    async def test_register_workflow_failure(self, integration):
        """Testa registro de workflow falhado."""
        result = await integration.register_workflow_failure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model prediction confidence too low",
            model_version="v1.0.0",
            priority="high",
            estimated_impact=0.8,
        )

        assert result["status"] == "registered"
        assert result["workflow_id"] == "wf-123"

    @pytest.mark.asyncio()
    async def test_register_workflow_failure_invalid_priority(self, integration):
        """Testa registro com prioridade inválida (usa default)."""
        result = await integration.register_workflow_failure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_reason="Model failed",
            model_version="v1.0.0",
            priority="invalid_priority",
        )

        assert result["status"] == "registered"

    @pytest.mark.asyncio()
    async def test_get_replay_metrics(self, integration):
        """Testa busca de métricas de replay."""
        metrics = await integration.get_replay_metrics()

        assert metrics["queue_size"] == 5
        assert metrics["total_pending"] == 5

    @pytest.mark.asyncio()
    async def test_get_replay_metrics_not_initialized(self):
        """Testa busca de métricas quando não inicializado."""
        integration = FeedbackReplayIntegration(enabled=True)

        metrics = await integration.get_replay_metrics()

        assert metrics["status"] == "not_initialized"

    @pytest.mark.asyncio()
    async def test_close(self, integration):
        """Testa fechamento da integração."""
        await integration.close()

        assert integration.feedback_replay_service is None


class TestSingleton:
    """Testes para singleton get_feedback_replay_integration."""

    def test_singleton_returns_same_instance(self):
        """Testa que singleton retorna mesma instância."""
        # Reset singleton
        import src.ml.feedback_replay_integration as mod

        mod._integration_instance = None

        instance1 = get_feedback_replay_integration()
        instance2 = get_feedback_replay_integration()

        assert instance1 is instance2

    def test_singleton_persists(self):
        """Testa que singleton persiste entre chamadas."""
        import src.ml.feedback_replay_integration as mod

        mod._integration_instance = None

        integration = get_feedback_replay_integration()
        integration.enabled = False

        integration2 = get_feedback_replay_integration()
        assert integration2.enabled is False
