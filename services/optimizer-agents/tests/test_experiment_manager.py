"""
Testes unitários para ExperimentManager.

Cobre:
- Submissão de experimentos
- Monitoramento de experimentos
- Análise de resultados
- Abort de experimentos
- Rollback de experimentos
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.services.experiment_manager import ExperimentManager
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.models.optimization_event import OptimizationType
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock(spec=Settings)
    settings.experiment_timeout_seconds = 300
    settings.degradation_threshold = 0.15
    settings.rollback_on_degradation = True
    settings.min_improvement_threshold = 0.05
    return settings


@pytest.fixture
def mock_argo_client():
    """Mock do ArgoWorkflowsClient."""
    client = AsyncMock()
    client.submit_experiment_workflow = AsyncMock(return_value="workflow-test-123")
    client.get_workflow_status = AsyncMock(return_value={"status": "Running", "phase": "Running"})
    client.abort_workflow = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient."""
    client = AsyncMock()
    client.save_experiment = AsyncMock(return_value=True)
    client.update_experiment_status = AsyncMock(return_value=True)
    client.get_experiment = AsyncMock(return_value={
        "experiment_id": "exp-123",
        "status": "RUNNING",
        "target_component": "consensus-engine"
    })
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do RedisClient."""
    client = AsyncMock()
    client.lock_component = AsyncMock(return_value=True)
    client.unlock_component = AsyncMock(return_value=True)
    client.get_experiment_metrics = AsyncMock(return_value={
        "baseline": {"latency_p95": 1000, "error_rate": 0.05},
        "treatment": {"latency_p95": 800, "error_rate": 0.03}
    })
    return client


@pytest.fixture
def experiment_manager(mock_settings, mock_argo_client, mock_mongodb_client, mock_redis_client):
    """Fixture do ExperimentManager."""
    return ExperimentManager(
        settings=mock_settings,
        argo_client=mock_argo_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client
    )


@pytest.fixture
def sample_hypothesis():
    """Hipótese de exemplo para testes."""
    hypothesis = Mock(spec=OptimizationHypothesis)
    hypothesis.hypothesis_id = "hyp-test-1"
    hypothesis.optimization_type = OptimizationType.WEIGHT_RECALIBRATION
    hypothesis.target_component = "consensus-engine"
    hypothesis.baseline_metrics = {"latency_p95": 1000, "error_rate": 0.05}
    hypothesis.expected_improvement = 0.15
    hypothesis.confidence = 0.85
    hypothesis.risk_score = 0.25
    hypothesis.validate_feasibility = Mock(return_value=True)
    return hypothesis


class TestExperimentSubmission:
    """Testes de submissão de experimentos."""

    @pytest.mark.asyncio
    async def test_submit_experiment_success(self, experiment_manager, sample_hypothesis, mock_argo_client, mock_mongodb_client):
        """Testa submissão bem-sucedida de experimento."""
        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        assert experiment_id is not None
        mock_argo_client.submit_experiment_workflow.assert_called_once()
        mock_mongodb_client.save_experiment.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_experiment_rejects_infeasible_hypothesis(self, experiment_manager, sample_hypothesis):
        """Testa que hipóteses inviáveis são rejeitadas."""
        sample_hypothesis.validate_feasibility.return_value = False

        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        assert experiment_id is None

    @pytest.mark.asyncio
    async def test_submit_experiment_respects_component_lock(self, experiment_manager, sample_hypothesis, mock_redis_client):
        """Testa que experimento não é submetido se componente está bloqueado."""
        mock_redis_client.lock_component.return_value = False

        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        assert experiment_id is None

    @pytest.mark.asyncio
    async def test_submit_experiment_validates_guardrails(self, experiment_manager, sample_hypothesis, mock_argo_client):
        """Testa validação de guardrails antes de submeter."""
        with patch.object(experiment_manager, '_hypothesis_to_experiment_request') as mock_convert:
            mock_request = Mock()
            mock_request.validate_guardrails.return_value = False
            mock_request.experiment_id = "exp-123"
            mock_convert.return_value = mock_request

            experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

            assert experiment_id is None
            mock_argo_client.submit_experiment_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_experiment_unlocks_on_error(self, experiment_manager, sample_hypothesis, mock_redis_client, mock_argo_client):
        """Testa que componente é desbloqueado em caso de erro."""
        mock_argo_client.submit_experiment_workflow.side_effect = Exception("Argo error")

        with pytest.raises(Exception):
            await experiment_manager.submit_experiment(sample_hypothesis)

        # Componente deve ser desbloqueado
        mock_redis_client.unlock_component.assert_called_with(sample_hypothesis.target_component)


class TestExperimentMonitoring:
    """Testes de monitoramento de experimentos."""

    @pytest.mark.asyncio
    async def test_monitor_experiment_running(self, experiment_manager, mock_argo_client):
        """Testa monitoramento de experimento em execução."""
        experiment_id = "exp-test-123"

        status = await experiment_manager.monitor_experiment(experiment_id)

        assert status is not None
        assert "status" in status
        mock_argo_client.get_workflow_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_experiment_returns_none_on_error(self, experiment_manager, mock_argo_client):
        """Testa que retorna None em caso de erro."""
        mock_argo_client.get_workflow_status.side_effect = Exception("Workflow not found")
        experiment_id = "exp-nonexistent"

        status = await experiment_manager.monitor_experiment(experiment_id)

        assert status is None

    @pytest.mark.asyncio
    async def test_list_active_experiments(self, experiment_manager, mock_mongodb_client):
        """Testa listagem de experimentos ativos."""
        mock_mongodb_client.list_experiments.return_value = [
            {"experiment_id": "exp-1", "status": "RUNNING"},
            {"experiment_id": "exp-2", "status": "RUNNING"},
        ]

        active = await experiment_manager.list_active_experiments()

        assert len(active) == 2
        mock_mongodb_client.list_experiments.assert_called_once()


class TestExperimentAnalysis:
    """Testes de análise de resultados."""

    @pytest.mark.asyncio
    async def test_analyze_results_positive_outcome(self, experiment_manager, mock_redis_client):
        """Testa análise de resultados com melhoria positiva."""
        experiment_id = "exp-123"

        # Mock de métricas com melhoria
        mock_redis_client.get_experiment_metrics.return_value = {
            "baseline": {"latency_p95": 1000, "error_rate": 0.05},
            "treatment": {"latency_p95": 800, "error_rate": 0.03}
        }

        results = await experiment_manager.analyze_results(experiment_id)

        assert results is not None
        assert results.get("improvement_percentage", 0) > 0
        assert results.get("statistical_significance", False) is True

    @pytest.mark.asyncio
    async def test_analyze_results_negative_outcome(self, experiment_manager, mock_redis_client):
        """Testa análise de resultados com degradação."""
        experiment_id = "exp-123"

        # Mock de métricas com degradação
        mock_redis_client.get_experiment_metrics.return_value = {
            "baseline": {"latency_p95": 800, "error_rate": 0.03},
            "treatment": {"latency_p95": 1200, "error_rate": 0.08}
        }

        results = await experiment_manager.analyze_results(experiment_id)

        assert results is not None
        assert results.get("improvement_percentage", 0) < 0
        assert results.get("degradation_detected", False) is True


class TestExperimentAbort:
    """Testes de abort de experimentos."""

    @pytest.mark.asyncio
    async def test_abort_experiment_success(self, experiment_manager, mock_argo_client, mock_mongodb_client):
        """Testa abort bem-sucedido de experimento."""
        experiment_id = "exp-123"
        reason = "timeout"

        success = await experiment_manager.abort_experiment(experiment_id, reason)

        assert success is True
        mock_argo_client.abort_workflow.assert_called_once()
        mock_mongodb_client.update_experiment_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_experiment_handles_argo_error(self, experiment_manager, mock_argo_client):
        """Testa handling de erro ao abortar no Argo."""
        mock_argo_client.abort_workflow.side_effect = Exception("Argo abort failed")
        experiment_id = "exp-123"

        success = await experiment_manager.abort_experiment(experiment_id, "test")

        assert success is False


class TestExperimentRollback:
    """Testes de rollback de experimentos."""

    @pytest.mark.asyncio
    async def test_rollback_experiment_success(self, experiment_manager, mock_mongodb_client):
        """Testa rollback bem-sucedido."""
        experiment_id = "exp-123"

        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": experiment_id,
            "target_component": "consensus-engine",
            "baseline_config": {"weights": {"accuracy": 0.5, "speed": 0.5}}
        }

        result = await experiment_manager.rollback_experiment(experiment_id)

        assert result.get("success", False) is True
        assert result.get("component") == "consensus-engine"

    @pytest.mark.asyncio
    async def test_rollback_experiment_not_found(self, experiment_manager, mock_mongodb_client):
        """Testa rollback de experimento inexistente."""
        mock_mongodb_client.get_experiment.return_value = None
        experiment_id = "exp-nonexistent"

        result = await experiment_manager.rollback_experiment(experiment_id)

        assert result.get("success", False) is False
        assert "not found" in result.get("reason", "").lower()

    @pytest.mark.asyncio
    async def test_rollback_updates_mongodb(self, experiment_manager, mock_mongodb_client):
        """Testa que rollback atualiza status no MongoDB."""
        experiment_id = "exp-123"

        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": experiment_id,
            "target_component": "consensus-engine",
            "baseline_config": {}
        }

        await experiment_manager.rollback_experiment(experiment_id)

        # Deve atualizar status para ROLLED_BACK
        calls = mock_mongodb_client.update_experiment_status.call_args_list
        assert any("ROLLED_BACK" in str(call) for call in calls)


class TestHypothesisToExperimentConversion:
    """Testes de conversão de hipótese para requisição de experimento."""

    def test_hypothesis_to_experiment_request(self, experiment_manager, sample_hypothesis):
        """Testa conversão de hipótese para ExperimentRequest."""
        experiment_request = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)

        assert experiment_request.target_component == sample_hypothesis.target_component
        assert experiment_request.hypothesis_id == sample_hypothesis.hypothesis_id

    def test_conversion_sets_baseline_metrics(self, experiment_manager, sample_hypothesis):
        """Testa que métricas baseline são copiadas."""
        experiment_request = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)

        assert experiment_request.baseline_metrics == sample_hypothesis.baseline_metrics

    def test_conversion_generates_unique_experiment_id(self, experiment_manager, sample_hypothesis):
        """Testa que cada conversão gera ID único."""
        request1 = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)
        request2 = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)

        assert request1.experiment_id != request2.experiment_id
