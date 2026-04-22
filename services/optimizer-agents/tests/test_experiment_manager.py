"""
Testes unitários para ExperimentManager.

Cobre:
- Submissão de experimentos
- Monitoramento de experimentos
- Análise de resultados
- Abort de experimentos
- Rollback de experimentos
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.config.settings import Settings
from src.models.optimization_event import OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.services.experiment_manager import ExperimentManager


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock(spec=Settings)
    settings.experiment_timeout_seconds = 300
    settings.degradation_threshold = 0.15
    settings.rollback_on_degradation = True
    settings.min_improvement_threshold = 0.05
    # Atributos para A/B testing
    settings.ab_test_default_alpha = 0.05
    settings.ab_test_default_power = 0.80
    settings.ab_test_min_sample_size = 100
    settings.ab_test_early_stopping_enabled = True
    settings.ab_test_bayesian_analysis_enabled = True
    settings.ab_test_sequential_testing_enabled = True
    settings.ab_test_default_traffic_split = 0.5
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

    # Criar um dict compatível com ExperimentRequest
    now_millis = int(datetime.now(UTC).timestamp() * 1000)
    experiment_doc = {
        "experiment_id": "exp-123",
        "version": "1.0.0",
        "correlation_id": "corr-123",
        "trace_id": "trace-123",
        "span_id": "span-123",
        "hypothesis": "Test hypothesis",
        "objective": "Test objective",
        "experiment_type": "A_B_TEST",
        "target_component": "consensus-engine",
        "baseline_configuration": {"latency": "1000"},
        "experimental_configuration": {},
        "success_criteria": [],
        "guardrails": [],
        "traffic_percentage": 0.1,
        "duration_seconds": 300,
        "sample_size": 100,
        "randomization_strategy": "RANDOM",
        "ethical_approval_required": False,
        "approved_by_compliance": False,
        "rollback_on_failure": True,
        "created_at": now_millis,
        "created_by": "optimizer-agents",
        "metadata": {},
        "control_group_size": 0,
        "treatment_group_size": 0,
        "control_metrics": {},
        "treatment_metrics": {},
        "statistical_results": {},
        "ab_test_config": {},
        "minimum_sample_size": 100,
    }

    client.get_experiment = AsyncMock(return_value=experiment_doc)
    client.list_experiments = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do RedisClient."""
    client = AsyncMock()
    client.lock_component = AsyncMock(return_value=True)
    client.unlock_component = AsyncMock(return_value=True)
    client.get_experiment_metrics = AsyncMock(
        return_value={
            "baseline": {"latency_p95": 1000, "error_rate": 0.05},
            "treatment": {"latency_p95": 800, "error_rate": 0.03},
        }
    )
    return client


@pytest.fixture
def experiment_manager(mock_settings, mock_argo_client, mock_mongodb_client, mock_redis_client):
    """Fixture do ExperimentManager."""
    return ExperimentManager(
        settings=mock_settings,
        argo_client=mock_argo_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
    )


@pytest.fixture
def sample_hypothesis():
    """Hipótese de exemplo para testes."""
    hypothesis = Mock(spec=OptimizationHypothesis)
    hypothesis.hypothesis_id = "hyp-test-1"
    hypothesis.hypothesis_text = "Test hypothesis for weight recalculation"
    hypothesis.optimization_type = OptimizationType.WEIGHT_RECALIBRATION
    hypothesis.target_component = "consensus-engine"
    hypothesis.baseline_metrics = {"latency_p95": 1000, "error_rate": 0.05}
    hypothesis.target_metrics = {"latency_p95": 800, "error_rate": 0.03}
    hypothesis.expected_improvement = 0.15
    hypothesis.confidence_score = 0.85
    hypothesis.risk_score = 0.25
    hypothesis.priority = 2
    hypothesis.proposed_adjustments = []
    hypothesis.metadata = {}
    hypothesis.requires_experiment = True
    hypothesis.validate_feasibility = Mock(return_value=True)
    return hypothesis


class TestExperimentSubmission:
    """Testes de submissão de experimentos."""

    @pytest.mark.asyncio
    async def test_submit_experiment_success(
        self, experiment_manager, sample_hypothesis, mock_argo_client, mock_mongodb_client
    ):
        """Testa submissão bem-sucedida de experimento."""
        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        assert experiment_id is not None
        mock_argo_client.submit_experiment_workflow.assert_called_once()
        # save_experiment é chamado duas vezes: uma para AB test, outra para experiment request
        assert mock_mongodb_client.save_experiment.call_count == 2

    @pytest.mark.asyncio
    async def test_submit_experiment_rejects_infeasible_hypothesis(
        self, experiment_manager, sample_hypothesis
    ):
        """Testa que hipóteses inviáveis são rejeitadas."""
        sample_hypothesis.validate_feasibility.return_value = False

        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        assert experiment_id is None

    @pytest.mark.asyncio
    async def test_submit_experiment_respects_component_lock(
        self, experiment_manager, sample_hypothesis, mock_redis_client
    ):
        """Testa que experimento não é submetido se componente está bloqueado."""
        mock_redis_client.lock_component.return_value = False

        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        assert experiment_id is None

    @pytest.mark.asyncio
    async def test_submit_experiment_validates_guardrails(
        self, experiment_manager, sample_hypothesis, mock_argo_client
    ):
        """Testa validação de guardrails antes de submeter."""
        with patch.object(experiment_manager, "_hypothesis_to_experiment_request") as mock_convert:
            mock_request = Mock()
            mock_request.validate_guardrails.return_value = False
            mock_request.experiment_id = "exp-123"
            mock_convert.return_value = mock_request

            experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

            assert experiment_id is None
            mock_argo_client.submit_experiment_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_experiment_unlocks_on_error(
        self, experiment_manager, sample_hypothesis, mock_redis_client, mock_argo_client
    ):
        """Testa que componente é desbloqueado em caso de erro."""
        mock_argo_client.submit_experiment_workflow.side_effect = Exception("Argo error")

        # O método captura a exceção e retorna None
        experiment_id = await experiment_manager.submit_experiment(sample_hypothesis)

        # Deve retornar None devido ao erro
        assert experiment_id is None
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
    async def test_monitor_experiment_returns_none_on_error(
        self, experiment_manager, mock_argo_client
    ):
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
    async def test_analyze_results_positive_outcome(self, experiment_manager):
        """Testa análise de resultados com melhoria positiva."""
        experiment_id = "exp-123"

        # Mock do ab_testing_engine.analyze_results para retornar resultado positivo
        from unittest.mock import AsyncMock, Mock

        mock_ab_result = Mock()
        mock_ab_result.statistical_recommendation = "APPLY"
        mock_ab_result.confidence_level = 0.95
        mock_ab_result.control_size = 100
        mock_ab_result.treatment_size = 100
        mock_ab_result.primary_metrics_analysis = [
            {"control_mean": 1000, "treatment_mean": 800, "metric_name": "latency_p95"}
        ]
        mock_ab_result.secondary_metrics_analysis = []
        mock_ab_result.bayesian_analysis = []
        mock_ab_result.guardrails_status = {"passed": True}
        mock_ab_result.early_stopped = False
        mock_ab_result.early_stop_reason = None

        experiment_manager.ab_testing_engine.analyze_results = AsyncMock(
            return_value=mock_ab_result
        )

        results = await experiment_manager.analyze_experiment_results(experiment_id)

        assert results is not None
        assert results.get("success") is True
        assert results.get("confidence") == 0.95
        assert results.get("recommendation") == "APPLY"
        assert (
            results.get("improvement_percentage", 0) < 0
        )  # 800 < 1000 means improvement (lower latency)

    @pytest.mark.asyncio
    async def test_analyze_results_negative_outcome(self, experiment_manager):
        """Testa análise de resultados com degradação."""
        experiment_id = "exp-123"

        # Mock do ab_testing_engine.analyze_results para retornar resultado negativo
        from unittest.mock import AsyncMock, Mock

        mock_ab_result = Mock()
        mock_ab_result.statistical_recommendation = "REJECT"
        mock_ab_result.confidence_level = 0.0
        mock_ab_result.control_size = 100
        mock_ab_result.treatment_size = 100
        mock_ab_result.primary_metrics_analysis = [
            {"control_mean": 800, "treatment_mean": 1200, "metric_name": "latency_p95"}
        ]
        mock_ab_result.secondary_metrics_analysis = []
        mock_ab_result.bayesian_analysis = []
        mock_ab_result.guardrails_status = {"passed": False}
        mock_ab_result.early_stopped = False
        mock_ab_result.early_stop_reason = None

        experiment_manager.ab_testing_engine.analyze_results = AsyncMock(
            return_value=mock_ab_result
        )

        results = await experiment_manager.analyze_experiment_results(experiment_id)

        assert results is not None
        assert results.get("success") is False
        assert results.get("recommendation") == "REJECT"
        assert results.get("improvement_percentage", 0) > 0  # 1200 > 800 means degradation


class TestExperimentAbort:
    """Testes de abort de experimentos."""

    @pytest.mark.asyncio
    async def test_abort_experiment_success(
        self, experiment_manager, mock_argo_client, mock_mongodb_client
    ):
        """Testa abort bem-sucedido de experimento."""
        experiment_id = "exp-123"
        reason = "timeout"

        # O método não retorna valor, apenas executa
        await experiment_manager.abort_experiment(experiment_id, reason)

        # Verificar que delete_workflow foi chamado (não abort_workflow)
        mock_argo_client.delete_workflow.assert_called_once_with(f"experiment-{experiment_id}")
        mock_mongodb_client.update_experiment_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_experiment_handles_argo_error(self, experiment_manager, mock_argo_client):
        """Testa handling de erro ao abortar no Argo."""
        mock_argo_client.delete_workflow.side_effect = Exception("Argo abort failed")
        experiment_id = "exp-123"

        # O método não retorna valor mesmo em caso de erro (apenas loga)
        await experiment_manager.abort_experiment(experiment_id, "test")

        # Deve ter tentado deletar o workflow
        mock_argo_client.delete_workflow.assert_called_once_with(f"experiment-{experiment_id}")


class TestExperimentRollback:
    """Testes de rollback de experimentos."""

    @pytest.mark.asyncio
    async def test_rollback_experiment_success(self, experiment_manager, mock_mongodb_client):
        """Testa rollback bem-sucedido."""
        experiment_id = "exp-123"

        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": experiment_id,
            "target_component": "consensus-engine",
            "baseline_config": {"weights": {"accuracy": 0.5, "speed": 0.5}},
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
        # A reason contém "not_found" como parte da mensagem de erro
        assert (
            result.get("reason", "").find("not_found") != -1
            or result.get("reason", "").find("not found") != -1
        )

    @pytest.mark.asyncio
    async def test_rollback_updates_mongodb(self, experiment_manager, mock_mongodb_client):
        """Testa que rollback atualiza status no MongoDB."""
        experiment_id = "exp-123"

        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": experiment_id,
            "target_component": "consensus-engine",
            "baseline_config": {},
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
        # ExperimentRequest tem 'hypothesis' (texto) não 'hypothesis_id'
        assert experiment_request.hypothesis == sample_hypothesis.hypothesis_text

    def test_conversion_sets_baseline_metrics(self, experiment_manager, sample_hypothesis):
        """Testa que métricas baseline são copiadas."""
        experiment_request = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)

        # ExperimentRequest tem 'baseline_configuration' (Dict[str, str]) não 'baseline_metrics'
        assert "latency_p95" in experiment_request.baseline_configuration
        assert experiment_request.baseline_configuration["latency_p95"] == "1000"

    def test_conversion_generates_unique_experiment_id(self, experiment_manager, sample_hypothesis):
        """Testa que cada conversão gera ID único."""
        request1 = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)
        request2 = experiment_manager._hypothesis_to_experiment_request(sample_hypothesis)

        assert request1.experiment_id != request2.experiment_id
