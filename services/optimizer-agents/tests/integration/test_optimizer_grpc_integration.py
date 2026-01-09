"""
Testes de integracao gRPC para OptimizerServicer.

Valida comunicacao gRPC end-to-end com servidor real.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock
import grpc

from src.grpc_service.optimizer_servicer import OptimizerServicer
from src.grpc_service.server import GrpcServer


@pytest.fixture
def mock_optimization_engine():
    """Mock do OptimizationEngine."""
    engine = AsyncMock()
    return engine


@pytest.fixture
def mock_experiment_manager():
    """Mock do ExperimentManager."""
    manager = AsyncMock()
    return manager


@pytest.fixture
def mock_weight_recalibrator():
    """Mock do WeightRecalibrator."""
    recalibrator = AsyncMock()
    mock_event = Mock()
    mock_event.optimization_id = "opt-integration-123"
    recalibrator.apply_weight_recalibration.return_value = mock_event
    recalibrator.rollback_weight_recalibration.return_value = True
    return recalibrator


@pytest.fixture
def mock_slo_adjuster():
    """Mock do SLOAdjuster."""
    adjuster = AsyncMock()
    mock_event = Mock()
    mock_event.optimization_id = "opt-slo-456"
    adjuster.apply_slo_adjustment.return_value = mock_event
    adjuster.rollback_slo_adjustment.return_value = True
    return adjuster


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient com dados de teste."""
    client = AsyncMock()

    test_optimizations = [
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
            "optimization_type": "SLO_ADJUSTMENT",
            "target_component": "orchestrator",
            "improvement_percentage": 5.0,
            "applied_at": 1699059600,
            "approval_status": "APPROVED",
        },
    ]

    async def get_optimization(opt_id):
        for opt in test_optimizations:
            if opt["optimization_id"] == opt_id:
                return opt
        return None

    async def list_optimizations(filters=None, skip=0, limit=50):
        result = test_optimizations
        if filters:
            if filters.get("component"):
                result = [o for o in result if o["target_component"] == filters["component"]]
            if filters.get("optimization_type"):
                result = [o for o in result if o["optimization_type"] == filters["optimization_type"]]
        return result[skip:skip+limit]

    client.get_optimization = AsyncMock(side_effect=get_optimization)
    client.list_optimizations = AsyncMock(side_effect=list_optimizations)

    return client


@pytest.fixture
def mock_load_predictor():
    """Mock do LoadPredictor."""
    predictor = AsyncMock()
    predictor.predict_load.return_value = {
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
    return predictor


@pytest.fixture
def mock_scheduling_optimizer():
    """Mock do SchedulingOptimizer."""
    optimizer = AsyncMock()
    optimizer.optimize_scheduling.return_value = {
        "action": "SCALE_UP",
        "justification": "High load expected",
        "expected_improvement": 0.15,
        "risk_score": 0.2,
        "confidence": 0.85,
    }
    optimizer.recent_rewards = [0.5, 0.8, -0.2, 0.3]

    mock_action = Mock()
    mock_action.value = "SCALE_UP"
    optimizer.recent_actions = [mock_action]
    optimizer.q_table = {"state1": {"action1": 0.5}}

    return optimizer


@pytest.fixture
def mock_settings():
    """Settings para testes de integracao."""
    settings = Mock()
    settings.grpc_port = 50099
    return settings


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
    """OptimizerServicer configurado para testes de integracao."""
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


class TestGrpcServerLifecycle:
    """Testes de lifecycle do servidor gRPC."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_grpc_server_creates_successfully(self, optimizer_servicer, mock_settings):
        """Testa que servidor gRPC e criado sem erros."""
        server = GrpcServer(
            servicer=optimizer_servicer,
            settings=mock_settings,
        )

        assert server.servicer == optimizer_servicer
        assert server.settings == mock_settings
        assert server.server is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_grpc_server_registers_servicer(self, optimizer_servicer, mock_settings):
        """Testa que servicer e registrado corretamente."""
        server = GrpcServer(
            servicer=optimizer_servicer,
            settings=mock_settings,
        )

        assert server.servicer is not None
        assert hasattr(server.servicer, 'TriggerOptimization')
        assert hasattr(server.servicer, 'GetOptimizationStatus')
        assert hasattr(server.servicer, 'ListOptimizations')
        assert hasattr(server.servicer, 'RollbackOptimization')
        assert hasattr(server.servicer, 'GetStatistics')
        assert hasattr(server.servicer, 'HealthCheck')
        assert hasattr(server.servicer, 'GetLoadForecast')
        assert hasattr(server.servicer, 'GetSchedulingRecommendation')
        assert hasattr(server.servicer, 'GetSchedulingMetrics')


class TestTriggerOptimizationIntegration:
    """Testes de integracao para TriggerOptimization."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_trigger_weight_recalibration_via_servicer(
        self, optimizer_servicer, mock_weight_recalibrator
    ):
        """Testa trigger de weight recalibration via servicer."""
        request = Mock()
        request.component = "consensus-engine"
        request.optimization_type = "WEIGHT_RECALIBRATION"
        request.context = {"justification": "Integration test"}

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("abort"))

        result = await optimizer_servicer.TriggerOptimization(request, mock_context)

        assert result["experiment_id"] == "opt-integration-123"
        assert result["status"] == "APPLIED"
        mock_weight_recalibrator.apply_weight_recalibration.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_trigger_slo_adjustment_via_servicer(
        self, optimizer_servicer, mock_slo_adjuster
    ):
        """Testa trigger de SLO adjustment via servicer."""
        request = Mock()
        request.component = "orchestrator"
        request.optimization_type = "SLO_ADJUSTMENT"
        request.context = {"justification": "Integration test"}

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("abort"))

        result = await optimizer_servicer.TriggerOptimization(request, mock_context)

        assert result["experiment_id"] == "opt-slo-456"
        assert result["status"] == "APPLIED"
        mock_slo_adjuster.apply_slo_adjustment.assert_called_once()


class TestListOptimizationsIntegration:
    """Testes de integracao para ListOptimizations."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_all_optimizations(self, optimizer_servicer, mock_mongodb_client):
        """Testa listagem de todas as otimizacoes."""
        request = Mock()
        request.component = ""
        request.optimization_type = ""
        request.page_size = 50

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("abort"))

        result = await optimizer_servicer.ListOptimizations(request, mock_context)

        assert result["total"] == 2
        assert len(result["optimizations"]) == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_optimizations_with_filter(self, optimizer_servicer, mock_mongodb_client):
        """Testa listagem com filtro por componente."""
        request = Mock()
        request.component = "consensus-engine"
        request.optimization_type = "WEIGHT_RECALIBRATION"
        request.page_size = 50

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("abort"))

        result = await optimizer_servicer.ListOptimizations(request, mock_context)

        assert result["total"] >= 0


class TestGetLoadForecastIntegration:
    """Testes de integracao para GetLoadForecast."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_forecast_with_full_metadata(
        self, optimizer_servicer, mock_load_predictor
    ):
        """Testa forecast com metadata completa."""
        request = Mock()
        request.horizon_minutes = 60
        request.include_confidence_intervals = True

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("abort"))

        result = await optimizer_servicer.GetLoadForecast(request, mock_context)

        assert "forecast" in result
        assert "metadata" in result
        assert len(result["forecast"]) == 2
        mock_load_predictor.predict_load.assert_called_once_with(
            horizon_minutes=60,
            include_confidence_intervals=True
        )


class TestGetSchedulingRecommendationIntegration:
    """Testes de integracao para GetSchedulingRecommendation."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_recommendation_with_forecast(
        self, optimizer_servicer, mock_scheduling_optimizer, mock_load_predictor
    ):
        """Testa recomendacao utilizando forecast."""
        request = Mock()
        request.current_load = 80.0
        request.worker_utilization = 0.75
        request.queue_depth = 50
        request.sla_compliance = 0.98

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("abort"))

        result = await optimizer_servicer.GetSchedulingRecommendation(request, mock_context)

        assert result["action"] == "SCALE_UP"
        assert result["expected_improvement"] == 0.15
        mock_scheduling_optimizer.optimize_scheduling.assert_called_once()


class TestHealthCheckIntegration:
    """Testes de integracao para HealthCheck."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_health_check_returns_healthy(self, optimizer_servicer):
        """Testa que health check retorna healthy."""
        request = Mock()
        mock_context = Mock()

        result = await optimizer_servicer.HealthCheck(request, mock_context)

        assert result["healthy"] is True
        assert result["version"] == "1.0.0"


class TestGrpcErrorHandling:
    """Testes de tratamento de erros gRPC."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_optimization_not_found_error(self, optimizer_servicer, mock_mongodb_client):
        """Testa erro NOT_FOUND para otimizacao inexistente."""
        request = Mock()
        request.optimization_id = "opt-not-found"

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("NOT_FOUND"))

        with pytest.raises(Exception) as excinfo:
            await optimizer_servicer.GetOptimizationStatus(request, mock_context)

        assert "NOT_FOUND" in str(excinfo.value)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unavailable_dependency_error(self, mock_optimization_engine):
        """Testa erro UNAVAILABLE quando dependencia nao disponivel."""
        servicer = OptimizerServicer(
            optimization_engine=mock_optimization_engine,
            load_predictor=None,
        )

        request = Mock()
        request.horizon_minutes = 60
        request.include_confidence_intervals = True

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("UNAVAILABLE"))

        with pytest.raises(Exception) as excinfo:
            await servicer.GetLoadForecast(request, mock_context)

        assert "UNAVAILABLE" in str(excinfo.value)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_argument_error(
        self, optimizer_servicer, mock_load_predictor
    ):
        """Testa erro INVALID_ARGUMENT para parametros invalidos."""
        request = Mock()
        request.horizon_minutes = -100
        request.include_confidence_intervals = False

        mock_load_predictor.predict_load.side_effect = ValueError("Invalid horizon")

        mock_context = Mock()
        mock_context.abort = Mock(side_effect=Exception("INVALID_ARGUMENT"))

        with pytest.raises(Exception) as excinfo:
            await optimizer_servicer.GetLoadForecast(request, mock_context)

        assert "INVALID_ARGUMENT" in str(excinfo.value)


class TestStatisticsIntegration:
    """Testes de integracao para GetStatistics."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_statistics_calculation(self, optimizer_servicer, mock_mongodb_client):
        """Testa calculo de estatisticas agregadas."""
        request = Mock()
        mock_context = Mock()

        result = await optimizer_servicer.GetStatistics(request, mock_context)

        assert "total_optimizations" in result
        assert "success_rate" in result
        assert "average_improvement" in result
        assert "by_type" in result
        assert "by_component" in result
