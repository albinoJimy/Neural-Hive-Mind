"""
Testes unitarios para OptimizerServicer.

Testa os metodos gRPC do servicer principal do Optimizer Agent.
"""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime

from src.grpc_service.optimizer_servicer import OptimizerServicer
from src.models.optimization_event import OptimizationType
from src.models.optimization_hypothesis import OptimizationHypothesis


@pytest.fixture
def mock_optimization_engine():
    """Mock do OptimizationEngine."""
    engine = AsyncMock()
    engine.apply_optimization = AsyncMock()
    return engine


@pytest.fixture
def mock_experiment_manager():
    """Mock do ExperimentManager."""
    manager = AsyncMock()
    manager.create_experiment = AsyncMock()
    manager.get_experiment = AsyncMock()
    return manager


@pytest.fixture
def mock_weight_recalibrator():
    """Mock do WeightRecalibrator."""
    recalibrator = AsyncMock()
    recalibrator.apply_weight_recalibration = AsyncMock()
    recalibrator.rollback_weight_recalibration = AsyncMock()
    return recalibrator


@pytest.fixture
def mock_slo_adjuster():
    """Mock do SLOAdjuster."""
    adjuster = AsyncMock()
    adjuster.apply_slo_adjustment = AsyncMock()
    adjuster.rollback_slo_adjustment = AsyncMock()
    return adjuster


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient."""
    client = AsyncMock()
    client.get_optimization = AsyncMock()
    client.list_optimizations = AsyncMock()
    return client


@pytest.fixture
def mock_load_predictor():
    """Mock do LoadPredictor."""
    predictor = AsyncMock()
    predictor.predict_load = AsyncMock()
    return predictor


@pytest.fixture
def mock_scheduling_optimizer():
    """Mock do SchedulingOptimizer."""
    optimizer = AsyncMock()
    optimizer.optimize_scheduling = AsyncMock()
    optimizer.recent_rewards = []
    optimizer.recent_actions = []
    optimizer.q_table = {}
    return optimizer


@pytest.fixture
def mock_settings():
    """Mock das Settings."""
    settings = Mock()
    settings.grpc_port = 50051
    return settings


@pytest.fixture
def mock_grpc_context():
    """Mock do gRPC context."""
    context = Mock()
    context.abort = Mock(side_effect=Exception("gRPC abort called"))
    context.set_code = Mock()
    context.set_details = Mock()
    return context


@pytest.fixture
def optimizer_servicer(
    mock_optimization_engine,
    mock_experiment_manager,
    mock_weight_recalibrator,
    mock_slo_adjuster,
    mock_mongodb_client,
    mock_load_predictor,
    mock_scheduling_optimizer,
    mock_settings,
):
    """Fixture do OptimizerServicer com todas as dependencias mockadas."""
    return OptimizerServicer(
        optimization_engine=mock_optimization_engine,
        experiment_manager=mock_experiment_manager,
        weight_recalibrator=mock_weight_recalibrator,
        slo_adjuster=mock_slo_adjuster,
        mongodb_client=mock_mongodb_client,
        load_predictor=mock_load_predictor,
        scheduling_optimizer=mock_scheduling_optimizer,
        settings=mock_settings,
    )


class TestTriggerOptimization:
    """Testes para TriggerOptimization."""

    @pytest.mark.asyncio
    async def test_trigger_optimization_weight_recalibration_success(
        self, optimizer_servicer, mock_weight_recalibrator, mock_grpc_context
    ):
        """Testa trigger de weight recalibration com sucesso."""
        request = Mock()
        request.component = "consensus-engine"
        request.optimization_type = "WEIGHT_RECALIBRATION"
        request.context = {"justification": "Test optimization"}

        mock_optimization_event = Mock()
        mock_optimization_event.optimization_id = "opt-123"
        mock_weight_recalibrator.apply_weight_recalibration.return_value = mock_optimization_event

        result = await optimizer_servicer.TriggerOptimization(request, mock_grpc_context)

        assert result["experiment_id"] == "opt-123"
        assert result["status"] == "APPLIED"
        mock_weight_recalibrator.apply_weight_recalibration.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_optimization_slo_adjustment_success(
        self, optimizer_servicer, mock_slo_adjuster, mock_grpc_context
    ):
        """Testa trigger de SLO adjustment com sucesso."""
        request = Mock()
        request.component = "orchestrator"
        request.optimization_type = "SLO_ADJUSTMENT"
        request.context = {"justification": "SLO optimization"}

        mock_optimization_event = Mock()
        mock_optimization_event.optimization_id = "opt-456"
        mock_slo_adjuster.apply_slo_adjustment.return_value = mock_optimization_event

        result = await optimizer_servicer.TriggerOptimization(request, mock_grpc_context)

        assert result["experiment_id"] == "opt-456"
        assert result["status"] == "APPLIED"
        mock_slo_adjuster.apply_slo_adjustment.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_optimization_unavailable_recalibrator(
        self, mock_optimization_engine, mock_experiment_manager,
        mock_slo_adjuster, mock_mongodb_client, mock_grpc_context
    ):
        """Testa erro quando WeightRecalibrator nao esta disponivel."""
        servicer = OptimizerServicer(
            optimization_engine=mock_optimization_engine,
            experiment_manager=mock_experiment_manager,
            weight_recalibrator=None,
            slo_adjuster=mock_slo_adjuster,
            mongodb_client=mock_mongodb_client,
        )

        request = Mock()
        request.component = "consensus-engine"
        request.optimization_type = "WEIGHT_RECALIBRATION"
        request.context = {}

        with pytest.raises(Exception) as excinfo:
            await servicer.TriggerOptimization(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)
        mock_grpc_context.abort.assert_called()

    @pytest.mark.asyncio
    async def test_trigger_optimization_application_failure(
        self, optimizer_servicer, mock_weight_recalibrator, mock_grpc_context
    ):
        """Testa tratamento de falha na aplicacao da otimizacao."""
        request = Mock()
        request.component = "consensus-engine"
        request.optimization_type = "WEIGHT_RECALIBRATION"
        request.context = {}

        mock_weight_recalibrator.apply_weight_recalibration.return_value = None

        with pytest.raises(Exception) as excinfo:
            await optimizer_servicer.TriggerOptimization(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)


class TestGetOptimizationStatus:
    """Testes para GetOptimizationStatus."""

    @pytest.mark.asyncio
    async def test_get_optimization_status_success(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa recuperacao de status de otimizacao com sucesso."""
        request = Mock()
        request.optimization_id = "opt-123"

        mock_mongodb_client.get_optimization.return_value = {
            "optimization_id": "opt-123",
            "approval_status": "APPROVED",
            "improvement_percentage": 15.5,
            "baseline_metrics": {"latency_p99": 100},
            "achieved_metrics": {"latency_p99": 85},
        }

        result = await optimizer_servicer.GetOptimizationStatus(request, mock_grpc_context)

        assert result["optimization_id"] == "opt-123"
        assert result["approval_status"] == "APPROVED"
        mock_mongodb_client.get_optimization.assert_called_once_with("opt-123")

    @pytest.mark.asyncio
    async def test_get_optimization_status_not_found(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa erro 404 quando otimizacao nao existe."""
        request = Mock()
        request.optimization_id = "opt-not-found"

        mock_mongodb_client.get_optimization.return_value = None

        with pytest.raises(Exception) as excinfo:
            await optimizer_servicer.GetOptimizationStatus(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_get_optimization_status_mongodb_unavailable(
        self, mock_optimization_engine, mock_grpc_context
    ):
        """Testa erro quando MongoDB nao esta disponivel."""
        servicer = OptimizerServicer(
            optimization_engine=mock_optimization_engine,
            mongodb_client=None,
        )

        request = Mock()
        request.optimization_id = "opt-123"

        with pytest.raises(Exception) as excinfo:
            await servicer.GetOptimizationStatus(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)


class TestListOptimizations:
    """Testes para ListOptimizations."""

    @pytest.mark.asyncio
    async def test_list_optimizations_success(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa listagem de otimizacoes com filtros."""
        request = Mock()
        request.component = "consensus-engine"
        request.optimization_type = "WEIGHT_RECALIBRATION"
        request.page_size = 10

        mock_mongodb_client.list_optimizations.return_value = [
            {
                "optimization_id": "opt-1",
                "optimization_type": "WEIGHT_RECALIBRATION",
                "target_component": "consensus-engine",
                "improvement_percentage": 10.0,
                "applied_at": 1699056000,
                "approval_status": "APPROVED",
            },
            {
                "optimization_id": "opt-2",
                "optimization_type": "WEIGHT_RECALIBRATION",
                "target_component": "consensus-engine",
                "improvement_percentage": 5.0,
                "applied_at": 1699059600,
                "approval_status": "APPROVED",
            },
        ]

        result = await optimizer_servicer.ListOptimizations(request, mock_grpc_context)

        assert result["total"] == 2
        assert len(result["optimizations"]) == 2
        mock_mongodb_client.list_optimizations.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_optimizations_empty(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa resposta vazia quando nao ha otimizacoes."""
        request = Mock()
        request.component = ""
        request.optimization_type = ""
        request.page_size = 50

        mock_mongodb_client.list_optimizations.return_value = []

        result = await optimizer_servicer.ListOptimizations(request, mock_grpc_context)

        assert result["total"] == 0
        assert result["optimizations"] == []

    @pytest.mark.asyncio
    async def test_list_optimizations_pagination(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa paginacao de otimizacoes."""
        request = Mock()
        request.component = ""
        request.optimization_type = ""
        request.page_size = 5

        mock_mongodb_client.list_optimizations.return_value = [
            {"optimization_id": f"opt-{i}", "optimization_type": "WEIGHT_RECALIBRATION",
             "target_component": "test", "improvement_percentage": 0.0,
             "applied_at": 0, "approval_status": "APPROVED"}
            for i in range(5)
        ]

        result = await optimizer_servicer.ListOptimizations(request, mock_grpc_context)

        assert result["total"] == 5
        mock_mongodb_client.list_optimizations.assert_called_with(
            filters={}, skip=0, limit=5
        )


class TestRollbackOptimization:
    """Testes para RollbackOptimization."""

    @pytest.mark.asyncio
    async def test_rollback_optimization_weight_recalibration_success(
        self, optimizer_servicer, mock_mongodb_client, mock_weight_recalibrator, mock_grpc_context
    ):
        """Testa rollback de weight recalibration com sucesso."""
        request = Mock()
        request.optimization_id = "opt-123"

        mock_mongodb_client.get_optimization.return_value = {
            "optimization_id": "opt-123",
            "optimization_type": "WEIGHT_RECALIBRATION",
        }
        mock_weight_recalibrator.rollback_weight_recalibration.return_value = True

        result = await optimizer_servicer.RollbackOptimization(request, mock_grpc_context)

        assert result["status"] == "ROLLED_BACK"
        mock_weight_recalibrator.rollback_weight_recalibration.assert_called_once_with("opt-123")

    @pytest.mark.asyncio
    async def test_rollback_optimization_slo_adjustment_success(
        self, optimizer_servicer, mock_mongodb_client, mock_slo_adjuster, mock_grpc_context
    ):
        """Testa rollback de SLO adjustment com sucesso."""
        request = Mock()
        request.optimization_id = "opt-456"

        mock_mongodb_client.get_optimization.return_value = {
            "optimization_id": "opt-456",
            "optimization_type": "SLO_ADJUSTMENT",
        }
        mock_slo_adjuster.rollback_slo_adjustment.return_value = True

        result = await optimizer_servicer.RollbackOptimization(request, mock_grpc_context)

        assert result["status"] == "ROLLED_BACK"
        mock_slo_adjuster.rollback_slo_adjustment.assert_called_once_with("opt-456")

    @pytest.mark.asyncio
    async def test_rollback_optimization_not_found(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa erro 404 quando otimizacao nao existe."""
        request = Mock()
        request.optimization_id = "opt-not-found"

        mock_mongodb_client.get_optimization.return_value = None

        with pytest.raises(Exception) as excinfo:
            await optimizer_servicer.RollbackOptimization(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)


class TestGetStatistics:
    """Testes para GetStatistics."""

    @pytest.mark.asyncio
    async def test_get_statistics_success(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa calculo de estatisticas com sucesso."""
        request = Mock()

        mock_mongodb_client.list_optimizations.return_value = [
            {"optimization_type": "WEIGHT_RECALIBRATION", "target_component": "consensus", "improvement_percentage": 10.0},
            {"optimization_type": "WEIGHT_RECALIBRATION", "target_component": "consensus", "improvement_percentage": 15.0},
            {"optimization_type": "SLO_ADJUSTMENT", "target_component": "orchestrator", "improvement_percentage": 5.0},
            {"optimization_type": "SLO_ADJUSTMENT", "target_component": "orchestrator", "improvement_percentage": -2.0},
        ]

        result = await optimizer_servicer.GetStatistics(request, mock_grpc_context)

        assert result["total_optimizations"] == 4
        assert result["success_rate"] == 0.75
        assert result["average_improvement"] == 7.0
        assert result["by_type"]["WEIGHT_RECALIBRATION"] == 2
        assert result["by_type"]["SLO_ADJUSTMENT"] == 2
        assert result["by_component"]["consensus"] == 2
        assert result["by_component"]["orchestrator"] == 2

    @pytest.mark.asyncio
    async def test_get_statistics_empty_database(
        self, optimizer_servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa resposta com banco vazio."""
        request = Mock()

        mock_mongodb_client.list_optimizations.return_value = []

        result = await optimizer_servicer.GetStatistics(request, mock_grpc_context)

        assert result["total_optimizations"] == 0
        assert result["success_rate"] == 0.0
        assert result["average_improvement"] == 0.0


class TestHealthCheck:
    """Testes para HealthCheck."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(
        self, optimizer_servicer, mock_grpc_context
    ):
        """Testa resposta healthy quando tudo esta ok."""
        request = Mock()

        result = await optimizer_servicer.HealthCheck(request, mock_grpc_context)

        assert result["healthy"] is True
        assert result["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_no_engine(
        self, mock_mongodb_client, mock_grpc_context
    ):
        """Testa unhealthy quando engine ausente."""
        servicer = OptimizerServicer(
            optimization_engine=None,
            mongodb_client=mock_mongodb_client,
        )

        request = Mock()

        result = await servicer.HealthCheck(request, mock_grpc_context)

        assert result["healthy"] is False
        assert "OptimizationEngine" in result["message"]

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_no_mongodb(
        self, mock_optimization_engine, mock_grpc_context
    ):
        """Testa unhealthy quando MongoDB ausente."""
        servicer = OptimizerServicer(
            optimization_engine=mock_optimization_engine,
            mongodb_client=None,
        )

        request = Mock()

        result = await servicer.HealthCheck(request, mock_grpc_context)

        assert result["healthy"] is False
        assert "MongoDB" in result["message"]


class TestGetLoadForecast:
    """Testes para GetLoadForecast."""

    @pytest.mark.asyncio
    async def test_get_load_forecast_success(
        self, optimizer_servicer, mock_load_predictor, mock_grpc_context
    ):
        """Testa forecast com confidence intervals."""
        request = Mock()
        request.horizon_minutes = 60
        request.include_confidence_intervals = True

        mock_load_predictor.predict_load.return_value = {
            "forecast": [
                {"timestamp": 1699056000, "predicted_load": 100, "lower_bound": 80, "upper_bound": 120},
                {"timestamp": 1699056600, "predicted_load": 110, "lower_bound": 90, "upper_bound": 130},
            ],
            "metadata": {
                "model_horizon": 60,
                "data_points_used": 100,
                "confidence_level": 0.95,
            },
        }

        result = await optimizer_servicer.GetLoadForecast(request, mock_grpc_context)

        assert "forecast" in result
        assert "metadata" in result
        mock_load_predictor.predict_load.assert_called_once_with(
            horizon_minutes=60, include_confidence_intervals=True
        )

    @pytest.mark.asyncio
    async def test_get_load_forecast_without_ci(
        self, optimizer_servicer, mock_load_predictor, mock_grpc_context
    ):
        """Testa forecast sem confidence intervals."""
        request = Mock()
        request.horizon_minutes = 30
        request.include_confidence_intervals = False

        mock_load_predictor.predict_load.return_value = {
            "forecast": [
                {"timestamp": 1699056000, "predicted_load": 100},
            ],
            "metadata": {"model_horizon": 30},
        }

        result = await optimizer_servicer.GetLoadForecast(request, mock_grpc_context)

        assert "forecast" in result
        mock_load_predictor.predict_load.assert_called_once_with(
            horizon_minutes=30, include_confidence_intervals=False
        )

    @pytest.mark.asyncio
    async def test_get_load_forecast_predictor_unavailable(
        self, mock_optimization_engine, mock_grpc_context
    ):
        """Testa erro quando LoadPredictor nao esta disponivel."""
        servicer = OptimizerServicer(
            optimization_engine=mock_optimization_engine,
            load_predictor=None,
        )

        request = Mock()
        request.horizon_minutes = 60
        request.include_confidence_intervals = True

        with pytest.raises(Exception) as excinfo:
            await servicer.GetLoadForecast(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_get_load_forecast_invalid_horizon(
        self, optimizer_servicer, mock_load_predictor, mock_grpc_context
    ):
        """Testa erro com horizon invalido."""
        request = Mock()
        request.horizon_minutes = -10
        request.include_confidence_intervals = False

        mock_load_predictor.predict_load.side_effect = ValueError("Invalid horizon")

        with pytest.raises(Exception) as excinfo:
            await servicer.GetLoadForecast(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)


class TestGetSchedulingRecommendation:
    """Testes para GetSchedulingRecommendation."""

    @pytest.mark.asyncio
    async def test_get_scheduling_recommendation_success(
        self, optimizer_servicer, mock_scheduling_optimizer, mock_load_predictor, mock_grpc_context
    ):
        """Testa recomendacao com forecast."""
        request = Mock()
        request.current_load = 80.0
        request.worker_utilization = 0.75
        request.queue_depth = 50
        request.sla_compliance = 0.98

        mock_load_predictor.predict_load.return_value = {
            "forecast": [{"timestamp": 1699056000, "predicted_load": 100}],
            "metadata": {},
        }

        mock_scheduling_optimizer.optimize_scheduling.return_value = {
            "action": "SCALE_UP",
            "justification": "High load expected",
            "expected_improvement": 0.15,
            "risk_score": 0.2,
            "confidence": 0.85,
        }

        result = await optimizer_servicer.GetSchedulingRecommendation(request, mock_grpc_context)

        assert result["action"] == "SCALE_UP"
        assert result["justification"] == "High load expected"
        assert result["expected_improvement"] == 0.15
        mock_scheduling_optimizer.optimize_scheduling.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_scheduling_recommendation_without_forecast(
        self, optimizer_servicer, mock_scheduling_optimizer, mock_load_predictor, mock_grpc_context
    ):
        """Testa recomendacao sem forecast (predictor falha)."""
        request = Mock()
        request.current_load = 50.0
        request.worker_utilization = 0.5
        request.queue_depth = 10
        request.sla_compliance = 0.99

        mock_load_predictor.predict_load.side_effect = Exception("Predictor error")

        mock_scheduling_optimizer.optimize_scheduling.return_value = {
            "action": "NO_ACTION",
            "justification": "System stable",
            "expected_improvement": 0.0,
            "risk_score": 0.1,
            "confidence": 0.9,
        }

        result = await optimizer_servicer.GetSchedulingRecommendation(request, mock_grpc_context)

        assert result["action"] == "NO_ACTION"
        mock_scheduling_optimizer.optimize_scheduling.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_scheduling_recommendation_optimizer_unavailable(
        self, mock_optimization_engine, mock_grpc_context
    ):
        """Testa erro quando SchedulingOptimizer nao esta disponivel."""
        servicer = OptimizerServicer(
            optimization_engine=mock_optimization_engine,
            scheduling_optimizer=None,
        )

        request = Mock()
        request.current_load = 80.0
        request.worker_utilization = 0.75
        request.queue_depth = 50
        request.sla_compliance = 0.98

        with pytest.raises(Exception) as excinfo:
            await servicer.GetSchedulingRecommendation(request, mock_grpc_context)

        assert "gRPC abort called" in str(excinfo.value)


class TestGetSchedulingMetrics:
    """Testes para GetSchedulingMetrics."""

    @pytest.mark.asyncio
    async def test_get_scheduling_metrics_success(
        self, optimizer_servicer, mock_scheduling_optimizer, mock_grpc_context
    ):
        """Testa metricas de scheduling com sucesso."""
        request = Mock()
        request.time_range_hours = 24

        mock_action1 = Mock()
        mock_action1.value = "SCALE_UP"
        mock_action2 = Mock()
        mock_action2.value = "SCALE_UP"
        mock_action3 = Mock()
        mock_action3.value = "SCALE_DOWN"

        mock_scheduling_optimizer.recent_rewards = [0.5, 0.8, -0.2, 0.3]
        mock_scheduling_optimizer.recent_actions = [mock_action1, mock_action2, mock_action3]
        mock_scheduling_optimizer.q_table = {
            "state1": {"action1": 0.5},
            "state2": {"action1": 0.3, "action2": 0.7},
        }

        result = await optimizer_servicer.GetSchedulingMetrics(request, mock_grpc_context)

        assert result["average_reward"] == 0.35
        assert result["policy_success_rate"] == 0.75
        assert result["action_counts"]["SCALE_UP"] == 2
        assert result["action_counts"]["SCALE_DOWN"] == 1
        assert result["states_explored"] == 2

    @pytest.mark.asyncio
    async def test_get_scheduling_metrics_no_data(
        self, optimizer_servicer, mock_scheduling_optimizer, mock_grpc_context
    ):
        """Testa resposta sem dados historicos."""
        request = Mock()
        request.time_range_hours = 24

        mock_scheduling_optimizer.recent_rewards = []
        mock_scheduling_optimizer.recent_actions = []
        mock_scheduling_optimizer.q_table = {}

        result = await optimizer_servicer.GetSchedulingMetrics(request, mock_grpc_context)

        assert result["average_reward"] == 0.0
        assert result["policy_success_rate"] == 0.0
        assert result["states_explored"] == 0
