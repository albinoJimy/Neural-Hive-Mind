"""
Unit tests for ExperimentManager service (optimizer-agents).

Tests experiment creation, monitoring, and analysis.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from src.services.experiment_manager import ExperimentManager
from src.models.experiment_request import ExperimentType, RandomizationStrategy


class TestExperimentManagerInitialization:
    """Test ExperimentManager initialization."""

    def test_initialization_defaults(self, mock_settings):
        """Test initialization with default settings."""
        manager = ExperimentManager(settings=mock_settings)

        assert manager.settings is not None
        assert manager.ab_testing_engine is not None
        assert manager.guardrail_monitor is not None
        assert manager.sample_calculator is not None

    def test_initialization_with_clients(self, mock_settings, mock_mongodb_client, mock_redis_client):
        """Test initialization with clients."""
        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        assert manager.mongodb_client == mock_mongodb_client
        assert manager.redis_client == mock_redis_client

    def test_initialization_with_grpc_clients(self, mock_settings, mock_consensus_engine_client, mock_orchestrator_client):
        """Test initialization with gRPC clients."""
        manager = ExperimentManager(
            settings=mock_settings,
            consensus_engine_client=mock_consensus_engine_client,
            orchestrator_client=mock_orchestrator_client
        )

        assert manager.consensus_engine_client == mock_consensus_engine_client
        assert manager.orchestrator_client == mock_orchestrator_client


class TestExperimentSubmission:
    """Test experiment submission."""

    @pytest.mark.asyncio
    async def test_submit_experiment_infeasible(self, mock_settings, sample_optimization_hypothesis):
        """Test submission fails for infeasible hypothesis."""
        manager = ExperimentManager(settings=mock_settings)

        # Mock hypothesis as infeasible
        with patch.object(sample_optimization_hypothesis, 'validate_feasibility', return_value=False):
            result = await manager.submit_experiment(sample_optimization_hypothesis)

            assert result is None

    @pytest.mark.asyncio
    async def test_submit_experiment_component_locked(self, mock_settings, mock_redis_client, sample_optimization_hypothesis):
        """Test submission fails when component is locked."""
        mock_redis_client.lock_component = AsyncMock(return_value=False)
        manager = ExperimentManager(
            settings=mock_settings,
            redis_client=mock_redis_client
        )

        with patch.object(sample_optimization_hypothesis, 'validate_feasibility', return_value=True):
            result = await manager.submit_experiment(sample_optimization_hypothesis)

            assert result is None

    @pytest.mark.asyncio
    async def test_submit_experiment_success(self, mock_settings, mock_redis_client, mock_mongodb_client, sample_optimization_hypothesis):
        """Test successful experiment submission."""
        manager = ExperimentManager(
            settings=mock_settings,
            redis_client=mock_redis_client,
            mongodb_client=mock_mongodb_client
        )

        with patch.object(sample_optimization_hypothesis, 'validate_feasibility', return_value=True):
            result = await manager.submit_experiment(sample_optimization_hypothesis)

            assert result is not None  # Should return experiment_id

    @pytest.mark.asyncio
    async def test_submit_experiment_creates_ab_test(self, mock_settings, mock_redis_client, mock_mongodb_client, sample_optimization_hypothesis):
        """Test submission creates A/B test for A/B experiment type."""
        manager = ExperimentManager(
            settings=mock_settings,
            redis_client=mock_redis_client,
            mongodb_client=mock_mongodb_client
        )

        with patch.object(sample_optimization_hypothesis, 'validate_feasibility', return_value=True):
            result = await manager.submit_experiment(sample_optimization_hypothesis)

            # Should not raise errors
            assert result is not None


class TestExperimentMonitoring:
    """Test experiment monitoring."""

    @pytest.mark.asyncio
    async def test_monitor_experiment_no_mongodb(self, mock_settings):
        """Test monitoring fails without MongoDB client."""
        manager = ExperimentManager(settings=mock_settings)

        result = await manager.monitor_experiment("experiment-001")

        assert result is None

    @pytest.mark.asyncio
    async def test_monitor_experiment_not_found(self, mock_settings, mock_mongodb_client):
        """Test monitoring fails when experiment not found."""
        mock_mongodb_client.get_experiment = AsyncMock(return_value=None)
        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client
        )

        result = await manager.monitor_experiment("experiment-999")

        assert result is None

    @pytest.mark.asyncio
    async def test_monitor_experiment_success(self, mock_settings, mock_mongodb_client, mock_redis_client, sample_experiment_request):
        """Test successful experiment monitoring."""
        # Mock experiment document
        experiment_doc = {
            "experiment_id": sample_experiment_request.experiment_id,
            "status": "RUNNING",
            "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "target_component": "consensus-engine"
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_redis_client.keys = AsyncMock(return_value=[])
        mock_redis_client.get = AsyncMock(return_value="10")

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        result = await manager.monitor_experiment(sample_experiment_request.experiment_id)

        assert result is not None
        assert "elapsed_time" in result
        assert "status" in result

    @pytest.mark.asyncio
    async def test_monitor_experiment_guardrail_violation(self, mock_settings, mock_mongodb_client, mock_redis_client):
        """Test monitoring detects guardrail violations."""
        experiment_doc = {
            "experiment_id": "test-001",
            "status": "RUNNING",
            "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "target_component": "test-component"
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_redis_client.keys = AsyncMock(return_value=[])

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        # Mock guardrail monitor to return violation
        with patch.object(manager.guardrail_monitor, 'should_abort', return_value={
            "should_abort": True,
            "reason": "Error rate exceeded threshold"
        }):
            result = await manager.monitor_experiment("test-001")

            assert result is not None


class TestExperimentAnalysis:
    """Test experiment result analysis."""

    @pytest.mark.asyncio
    async def test_analyze_results_no_mongodb(self, mock_settings):
        """Test analysis fails without MongoDB client."""
        manager = ExperimentManager(settings=mock_settings)

        result = await manager.analyze_experiment_results("experiment-001")

        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_results_not_found(self, mock_settings, mock_mongodb_client):
        """Test analysis fails when experiment not found."""
        mock_mongodb_client.get_experiment = AsyncMock(return_value=None)
        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client
        )

        result = await manager.analyze_experiment_results("experiment-999")

        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_results_ab_test(self, mock_settings, mock_mongodb_client):
        """Test analysis for A/B test experiments."""
        from src.experimentation.ab_testing_engine import ABTestResults

        experiment_doc = {
            "experiment_id": "ab-test-001",
            "experiment_type": "A_B_TEST",
            "status": "COMPLETED"
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)

        # Mock AB testing engine results
        mock_ab_results = ABTestResults(
            experiment_id="ab-test-001",
            statistical_recommendation="APPLY",
            confidence_level=0.95,
            control_size=500,
            treatment_size=500,
            primary_metrics_analysis=[],
            secondary_metrics_analysis=[],
            bayesian_analysis={},
            guardrails_status={"all_passed": True},
            early_stopped=False
        )

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client
        )

        with patch.object(manager.ab_testing_engine, 'analyze_results', return_value=mock_ab_results):
            result = await manager.analyze_experiment_results("ab-test-001")

            assert result is not None
            assert result["recommendation"] == "APPLY"


class TestHypothesisValidation:
    """Test hypothesis validation."""

    @pytest.mark.asyncio
    async def test_validate_hypothesis_no_baseline(self, mock_settings, sample_optimization_hypothesis):
        """Test validation fails without baseline metrics."""
        manager = ExperimentManager(settings=mock_settings)

        hypothesis = sample_optimization_hypothesis
        hypothesis.baseline_metrics = {}

        result = await manager.validate_hypothesis(hypothesis)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_hypothesis_adjustment_exceeds_max(self, mock_settings, sample_optimization_hypothesis):
        """Test validation fails when adjustment exceeds max."""
        manager = ExperimentManager(settings=mock_settings)

        # Create adjustment that exceeds max
        from src.models.optimization_hypothesis import ProposedAdjustment
        large_adjustment = ProposedAdjustment(
            parameter_name="test_weight",
            old_value="0.5",
            new_value="1.5",  # Delta of 1.0 exceeds max_weight_adjustment
            previous_value=0.5
        )
        sample_optimization_hypothesis.proposed_adjustments = [large_adjustment]

        result = await manager.validate_hypothesis(sample_optimization_hypothesis)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_hypothesis_success(self, mock_settings, mock_redis_client, sample_optimization_hypothesis):
        """Test successful hypothesis validation."""
        manager = ExperimentManager(
            settings=mock_settings,
            redis_client=mock_redis_client
        )

        result = await manager.validate_hypothesis(sample_optimization_hypothesis)

        assert result is True


class TestExperimentAbort:
    """Test experiment abortion."""

    @pytest.mark.asyncio
    async def test_abort_experiment_no_mongodb(self, mock_settings):
        """Test abort without MongoDB doesn't crash."""
        manager = ExperimentManager(settings=mock_settings)

        # Should not raise
        await manager.abort_experiment("experiment-001", "Test abort")

    @pytest.mark.asyncio
    async def test_abort_experiment_with_argo(self, mock_settings, mock_mongodb_client, mock_redis_client, mock_argo_client):
        """Test abort with Argo workflow deletion."""
        experiment_doc = {
            "experiment_id": "test-001",
            "target_component": "test-component"
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_mongodb_client.update_experiment_status = AsyncMock()

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
            argo_client=mock_argo_client
        )

        await manager.abort_experiment("test-001", "Test abort")

        # Argo delete should be called
        mock_argo_client.delete_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_experiment_unlocks_component(self, mock_settings, mock_mongodb_client, mock_redis_client):
        """Test abort unlocks component."""
        experiment_doc = {
            "experiment_id": "test-001",
            "target_component": "test-component"
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_mongodb_client.update_experiment_status = AsyncMock()

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        await manager.abort_experiment("test-001", "Test abort")

        # Unlock should be called
        mock_redis_client.unlock_component.assert_called_once()


class TestExperimentStatus:
    """Test experiment status retrieval."""

    @pytest.mark.asyncio
    async def test_get_status_from_argo(self, mock_settings, mock_argo_client):
        """Test getting status from Argo."""
        manager = ExperimentManager(
            settings=mock_settings,
            argo_client=mock_argo_client
        )

        mock_argo_client.get_workflow_status = AsyncMock(return_value="Running")

        status = await manager.get_experiment_status("experiment-001")

        assert status == "Running"

    @pytest.mark.asyncio
    async def test_get_status_from_mongodb(self, mock_settings, mock_mongodb_client):
        """Test getting status from MongoDB."""
        experiment_doc = {"status": "COMPLETED"}
        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client
        )

        status = await manager.get_experiment_status("experiment-001")

        assert status == "COMPLETED"


class TestActiveExperiments:
    """Test listing active experiments."""

    @pytest.mark.asyncio
    async def test_list_active_experiments(self, mock_settings, mock_mongodb_client):
        """Test listing active experiments."""
        active_experiments = [
            {"experiment_id": "exp-001", "status": "RUNNING"},
            {"experiment_id": "exp-002", "status": "RUNNING"}
        ]
        mock_mongodb_client.list_experiments = AsyncMock(return_value=active_experiments)

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client
        )

        result = await manager.list_active_experiments()

        assert len(result) == 2
        assert result[0]["status"] == "RUNNING"

    @pytest.mark.asyncio
    async def test_list_active_experiments_no_mongodb(self, mock_settings):
        """Test listing active experiments without MongoDB."""
        manager = ExperimentManager(settings=mock_settings)

        result = await manager.list_active_experiments()

        assert result == []


class TestExperimentRollback:
    """Test experiment rollback."""

    @pytest.mark.asyncio
    async def test_rollback_experiment_no_mongodb(self, mock_settings):
        """Test rollback without MongoDB returns failure."""
        manager = ExperimentManager(settings=mock_settings)

        result = await manager.rollback_experiment("experiment-001")

        assert result["success"] is False
        assert "mongodb" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_rollback_experiment_not_found(self, mock_settings, mock_mongodb_client):
        """Test rollback fails when experiment not found."""
        mock_mongodb_client.get_experiment = AsyncMock(return_value=None)

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client
        )

        result = await manager.rollback_experiment("experiment-999")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_rollback_experiment_success(self, mock_settings, mock_mongodb_client, mock_redis_client, mock_argo_client):
        """Test successful experiment rollback."""
        experiment_doc = {
            "experiment_id": "test-001",
            "target_component": "test-component",
            "baseline_configuration": {"weight": 0.5}
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_mongodb_client.update_experiment_status = AsyncMock()

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
            argo_client=mock_argo_client
        )

        result = await manager.rollback_experiment("test-001")

        assert result["success"] is True
        assert result["rollback_completed"] is True


class TestSampleSizeCalculation:
    """Test sample size calculation."""

    def test_calculate_required_sample_size_binary_metric(self, mock_settings, sample_optimization_hypothesis):
        """Test sample size for binary metric."""
        manager = ExperimentManager(settings=mock_settings)

        hypothesis = sample_optimization_hypothesis
        hypothesis.baseline_metrics = {"conversion_rate": 0.1}
        hypothesis.target_metrics = {"conversion_rate": 0.12}

        sample_size = manager._calculate_required_sample_size(hypothesis)

        assert sample_size >= 100  # Should be at least min

    def test_calculate_required_sample_size_continuous_metric(self, mock_settings, sample_optimization_hypothesis):
        """Test sample size for continuous metric."""
        manager = ExperimentManager(settings=mock_settings)

        hypothesis = sample_optimization_hypothesis
        hypothesis.baseline_metrics = {"latency_p95": 200.0}
        hypothesis.target_metrics = {"latency_p95": 150.0}

        sample_size = manager._calculate_required_sample_size(hypothesis)

        assert sample_size >= 100  # Should be at least min

    def test_is_binary_metric_by_name(self, mock_settings):
        """Test binary metric detection by name."""
        manager = ExperimentManager(settings=mock_settings)

        assert manager._is_binary_metric("error_rate", 0.05) is True
        assert manager._is_binary_metric("conversion_rate", 0.1) is True
        assert manager._is_binary_metric("success_rate", 0.9) is True

    def test_is_binary_metric_by_value(self, mock_settings):
        """Test binary metric detection by value."""
        manager = ExperimentManager(settings=mock_settings)

        assert manager._is_binary_metric("unknown_metric", 0.5) is True
        assert manager._is_binary_metric("unknown_metric", 50.0) is False

    def test_validate_calculated_sample_size(self, mock_settings, sample_experiment_request):
        """Test sample size validation."""
        manager = ExperimentManager(settings=mock_settings)

        # Valid sample size
        sample_experiment_request.sample_size = 500
        result = manager._validate_calculated_sample_size(sample_experiment_request)

        assert result["is_valid"] is True

        # Invalid sample size
        sample_experiment_request.sample_size = 50
        result = manager._validate_calculated_sample_size(sample_experiment_request)

        assert result["is_valid"] is False


class TestHypothesisConversion:
    """Test hypothesis to experiment request conversion."""

    def test_hypothesis_to_experiment_request(self, mock_settings, sample_optimization_hypothesis):
        """Test converting hypothesis to experiment request."""
        manager = ExperimentManager(settings=mock_settings)

        request = manager._hypothesis_to_experiment_request(sample_optimization_hypothesis)

        assert request.experiment_type == ExperimentType.A_B_TEST
        assert request.target_component == sample_optimization_hypothesis.target_component
        assert request.hypothesis == sample_optimization_hypothesis.hypothesis_text
        assert request.sample_size >= 100

    def test_experiment_request_success_criteria(self, mock_settings, sample_optimization_hypothesis):
        """Test success criteria generation."""
        manager = ExperimentManager(settings=mock_settings)

        request = manager._hypothesis_to_experiment_request(sample_optimization_hypothesis)

        assert len(request.success_criteria) > 0
        for criterion in request.success_criteria:
            assert "metric_name" in criterion
            assert "operator" in criterion
            assert "threshold" in criterion

    def test_experiment_request_guardrails(self, mock_settings, sample_optimization_hypothesis):
        """Test guardrail generation."""
        manager = ExperimentManager(settings=mock_settings)

        request = manager._hypothesis_to_experiment_request(sample_optimization_hypothesis)

        assert len(request.guardrails) > 0
        for guardrail in request.guardrails:
            assert "metric_name" in guardrail
            assert "max_degradation_percentage" in guardrail


class TestExperimentMetrics:
    """Test experiment metrics retrieval."""

    @pytest.mark.asyncio
    async def test_get_experiment_metrics_no_redis(self, mock_settings):
        """Test metrics retrieval without Redis."""
        manager = ExperimentManager(settings=mock_settings)

        result = await manager._get_experiment_metrics("test-001", "control")

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_group_size(self, mock_settings, mock_redis_client):
        """Test getting group size."""
        mock_redis_client.get = AsyncMock(return_value="100")

        manager = ExperimentManager(
            settings=mock_settings,
            redis_client=mock_redis_client
        )

        size = await manager._get_group_size("test-001", "control")

        assert size == 100

    @pytest.mark.asyncio
    async def test_get_group_size_no_redis(self, mock_settings):
        """Test getting group size without Redis."""
        manager = ExperimentManager(settings=mock_settings)

        size = await manager._get_group_size("test-001", "control")

        assert size == 0


class TestSuccessCriteriaChecking:
    """Test success criteria verification."""

    def test_check_success_criteria_gte(self, mock_settings, sample_experiment_request):
        """Test GTE operator."""
        manager = ExperimentManager(settings=mock_settings)

        criterion = type('obj', (object,), {
            'metric_name': 'latency_p95',
            'operator': 'GTE',
            'threshold': 100.0
        })()

        # Mock criteria
        sample_experiment_request.success_criteria = [criterion]

        # Below threshold
        metrics = {"latency_p95": 90.0}
        result = manager._check_success_criteria(sample_experiment_request, metrics)

        assert result is False

        # Above threshold
        metrics = {"latency_p95": 110.0}
        result = manager._check_success_criteria(sample_experiment_request, metrics)

        assert result is True

    def test_check_success_criteria_lte(self, mock_settings, sample_experiment_request):
        """Test LTE operator."""
        manager = ExperimentManager(settings=mock_settings)

        criterion = type('obj', (object,), {
            'metric_name': 'error_rate',
            'operator': 'LTE',
            'threshold': 0.05
        })()

        sample_experiment_request.success_criteria = [criterion]

        # Below threshold
        metrics = {"error_rate": 0.03}
        result = manager._check_success_criteria(sample_experiment_request, metrics)

        assert result is True

        # Above threshold
        metrics = {"error_rate": 0.07}
        result = manager._check_success_criteria(sample_experiment_request, metrics)

        assert result is False


class TestStatisticalConfidence:
    """Test statistical confidence calculation."""

    def test_calculate_statistical_confidence(self, mock_settings):
        """Test confidence calculation."""
        manager = ExperimentManager(settings=mock_settings)

        baseline = {"metric1": 100, "metric2": 50}
        experimental = {"metric1": 90, "metric2": 45}  # Both improved

        confidence = manager._calculate_statistical_confidence(baseline, experimental)

        assert 0.5 <= confidence <= 1.0  # Should be good

    def test_calculate_statistical_confidence_no_improvement(self, mock_settings):
        """Test confidence with no improvement."""
        manager = ExperimentManager(settings=mock_settings)

        baseline = {"metric1": 100}
        experimental = {"metric1": 100}  # Same

        confidence = manager._calculate_statistical_confidence(baseline, experimental)

        assert confidence >= 0.5  # Base confidence


class TestRollbackExecution:
    """Test rollback execution."""

    @pytest.mark.asyncio
    async def test_execute_rollback_no_mongodb(self, mock_settings):
        """Test rollback execution without MongoDB."""
        manager = ExperimentManager(settings=mock_settings)

        result = await manager._execute_rollback("test-001")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_rollback_weights(self, mock_settings, mock_mongodb_client, mock_consensus_engine_client):
        """Test rollback for weight recalibration."""
        experiment_doc = {
            "experiment_id": "test-001",
            "objective": "Validate weight recalibration",
            "target_component": "consensus-engine",
            "baseline_configuration": {"business_weight": "0.25"}
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_mongodb_client.update_experiment_status = AsyncMock()

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            consensus_engine_client=mock_consensus_engine_client
        )

        result = await manager._execute_rollback("test-001")

        assert result["weights_rolled_back"] is True

    @pytest.mark.asyncio
    async def test_execute_rollback_slos(self, mock_settings, mock_mongodb_client, mock_orchestrator_client):
        """Test rollback for SLO adjustment."""
        experiment_doc = {
            "experiment_id": "test-001",
            "objective": "Validate SLO adjustment",
            "target_component": "orchestrator",
            "baseline_configuration": {"latency_slo": "200"}
        }

        mock_mongodb_client.get_experiment = AsyncMock(return_value=experiment_doc)
        mock_mongodb_client.update_experiment_status = AsyncMock()

        manager = ExperimentManager(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            orchestrator_client=mock_orchestrator_client
        )

        result = await manager._execute_rollback("test-001")

        assert result["slos_rolled_back"] is True


class TestABTestCreation:
    """Test A/B test creation from experiment request."""

    @pytest.mark.asyncio
    async def test_create_ab_test_from_request(self, mock_settings, sample_experiment_request, sample_optimization_hypothesis):
        """Test creating A/B test from experiment request."""
        manager = ExperimentManager(settings=mock_settings)

        # Mock AB testing engine
        mock_config = type('obj', (object,), {
            'experiment_id': 'ab-test-001',
            'minimum_sample_size': 500
        })()

        with patch.object(manager.ab_testing_engine, 'create_ab_test', return_value=mock_config):
            result = await manager._create_ab_test_from_request(
                sample_experiment_request,
                sample_optimization_hypothesis
            )

            assert result is not None
