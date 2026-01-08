"""
Testes de integração para OrchestratorOptimizationServicer.

Testa os métodos gRPC para otimização de SLOs.
"""
import pytest
from unittest.mock import AsyncMock, Mock
import time

from src.grpc_service.orchestrator_optimization_servicer import OrchestratorOptimizationServicer
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock(spec=Settings)
    settings.redis_cache_ttl = 300
    return settings


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDB client."""
    client = AsyncMock()
    client.find_one = AsyncMock()
    client.find = AsyncMock()
    client.insert_one = AsyncMock()
    client.update_one = AsyncMock()
    client.update_many = AsyncMock()
    client.count = AsyncMock(return_value=0)
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do Redis client."""
    client = AsyncMock()
    client.get_json = AsyncMock(return_value=None)
    client.set_json = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def mock_clickhouse_client():
    """Mock do ClickHouse client."""
    client = AsyncMock()
    client.query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_orchestrator_client():
    """Mock do Orchestrator gRPC client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_load_predictor():
    """Mock do LoadPredictor."""
    predictor = AsyncMock()
    predictor.predict_load = AsyncMock(return_value={
        "forecast": [
            {"timestamp": 1699056000, "predicted_load": 100, "lower_bound": 80, "upper_bound": 120}
        ],
        "metadata": {"confidence_level": 0.95}
    })
    return predictor


@pytest.fixture
def mock_scheduling_optimizer():
    """Mock do SchedulingOptimizer."""
    optimizer = Mock()
    optimizer.get_q_values = Mock(return_value={"action1": 0.5, "action2": 0.3})
    optimizer.record_reward = Mock()
    return optimizer


@pytest.fixture
def mock_slo_adjuster():
    """Mock do SLOAdjuster."""
    adjuster = AsyncMock()
    return adjuster


@pytest.fixture
def mock_metrics():
    """Mock do metrics collector."""
    metrics = Mock()
    metrics.increment_counter = Mock()
    metrics.increment_cache_hit = Mock()
    metrics.increment_cache_miss = Mock()
    metrics.observe_histogram = Mock()
    return metrics


@pytest.fixture
def mock_grpc_context():
    """Mock do gRPC context."""
    context = Mock()
    context.set_code = Mock()
    context.set_details = Mock()
    context.code = Mock(return_value=None)
    return context


@pytest.fixture
def servicer(
    mock_slo_adjuster,
    mock_mongodb_client,
    mock_redis_client,
    mock_clickhouse_client,
    mock_orchestrator_client,
    mock_load_predictor,
    mock_scheduling_optimizer,
    mock_settings,
    mock_metrics,
):
    """Fixture do OrchestratorOptimizationServicer."""
    return OrchestratorOptimizationServicer(
        slo_adjuster=mock_slo_adjuster,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        clickhouse_client=mock_clickhouse_client,
        orchestrator_client=mock_orchestrator_client,
        load_predictor=mock_load_predictor,
        scheduling_optimizer=mock_scheduling_optimizer,
        settings=mock_settings,
        metrics=mock_metrics,
    )


class TestGetCurrentSLOs:
    """Testes para GetCurrentSLOs."""

    @pytest.mark.asyncio
    async def test_get_slos_from_cache(self, servicer, mock_redis_client, mock_grpc_context):
        """Testa obtenção de SLOs do cache Redis."""
        cached_slos = {
            "slos": {
                "consensus-engine": {
                    "target_latency_ms": 1000,
                    "target_availability": 0.999,
                    "target_error_rate": 0.01,
                }
            },
            "last_updated_at": 1699056000000,
        }
        mock_redis_client.get_json.return_value = cached_slos

        request = Mock()
        request.HasField = Mock(return_value=False)

        result = await servicer.GetCurrentSLOs(request, mock_grpc_context)

        assert "consensus-engine" in result["slos"]
        assert result["slos"]["consensus-engine"]["target_latency_ms"] == 1000

    @pytest.mark.asyncio
    async def test_get_slos_returns_defaults_when_empty(
        self, servicer, mock_redis_client, mock_mongodb_client, mock_grpc_context
    ):
        """Testa retorno de SLOs padrão quando não há registros."""
        mock_redis_client.get_json.return_value = None

        async def empty_cursor():
            return
            yield

        mock_mongodb_client.find.return_value = empty_cursor()

        request = Mock()
        request.HasField = Mock(return_value=False)

        result = await servicer.GetCurrentSLOs(request, mock_grpc_context)

        assert "consensus-engine" in result["slos"]
        assert "orchestrator-dynamic" in result["slos"]


class TestUpdateSLOs:
    """Testes para UpdateSLOs."""

    @pytest.mark.asyncio
    async def test_update_slos_success(
        self, servicer, mock_mongodb_client, mock_redis_client, mock_grpc_context
    ):
        """Testa atualização bem-sucedida de SLOs."""
        mock_mongodb_client.find_one.return_value = {
            "service": "consensus-engine",
            "target_latency_ms": 1000,
            "target_availability": 0.999,
            "target_error_rate": 0.01,
            "active": True,
        }

        # Criar mock de SLOConfig
        slo_config = Mock()
        slo_config.target_latency_ms = 800
        slo_config.target_availability = 0.9995
        slo_config.target_error_rate = 0.008
        slo_config.latency_percentile = 0.95
        slo_config.time_window_seconds = 60
        slo_config.HasField = Mock(return_value=False)
        slo_config.metadata = {}

        request = Mock()
        request.slo_updates = {"consensus-engine": slo_config}
        request.justification = "Ajuste para melhorar latência"
        request.optimization_id = "slo-opt-123"
        request.validate_before_apply = False
        request.HasField = Mock(return_value=False)

        result = await servicer.UpdateSLOs(request, mock_grpc_context)

        assert result["success"] is True
        mock_mongodb_client.insert_one.assert_called()
        mock_redis_client.delete.assert_called()

    @pytest.mark.asyncio
    async def test_update_slos_with_validation_failure(
        self, servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa falha na validação de SLOs (latência muito baixa)."""
        mock_mongodb_client.find_one.return_value = None
        mock_mongodb_client.count.return_value = 0

        # SLO com latência abaixo do mínimo
        slo_config = Mock()
        slo_config.target_latency_ms = 50  # Abaixo do mínimo de 100ms
        slo_config.target_availability = 0.999
        slo_config.target_error_rate = 0.01
        slo_config.latency_percentile = 0.95
        slo_config.time_window_seconds = 60
        slo_config.HasField = Mock(return_value=False)
        slo_config.metadata = {}

        request = Mock()
        request.slo_updates = {"test-service": slo_config}
        request.justification = "SLO inválido"
        request.optimization_id = "slo-invalid"
        request.validate_before_apply = True
        request.HasField = Mock(return_value=False)

        result = await servicer.UpdateSLOs(request, mock_grpc_context)

        assert result["success"] is False


class TestValidateSLOAdjustment:
    """Testes para ValidateSLOAdjustment."""

    @pytest.mark.asyncio
    async def test_validate_valid_slos(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa validação de SLOs válidos."""
        mock_mongodb_client.find_one.return_value = None
        mock_mongodb_client.count.return_value = 0

        slo_config = Mock()
        slo_config.target_latency_ms = 1000
        slo_config.target_availability = 0.999
        slo_config.target_error_rate = 0.01
        slo_config.latency_percentile = 0.95
        slo_config.time_window_seconds = 60

        request = Mock()
        request.proposed_slos = {"consensus-engine": slo_config}
        request.check_error_budget = False

        result = await servicer.ValidateSLOAdjustment(request, mock_grpc_context)

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_invalid_availability(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa validação com disponibilidade inválida."""
        mock_mongodb_client.find_one.return_value = None
        mock_mongodb_client.count.return_value = 0

        slo_config = Mock()
        slo_config.target_latency_ms = 1000
        slo_config.target_availability = 0.80  # Abaixo do mínimo de 0.95
        slo_config.target_error_rate = 0.01
        slo_config.latency_percentile = 0.95
        slo_config.time_window_seconds = 60

        request = Mock()
        request.proposed_slos = {"test-service": slo_config}
        request.check_error_budget = False

        result = await servicer.ValidateSLOAdjustment(request, mock_grpc_context)

        assert result["is_valid"] is False
        assert any("disponibilidade" in e["description"].lower() or "availability" in e["description"].lower()
                   for e in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_invalid_error_rate(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa validação com error rate inválido."""
        mock_mongodb_client.find_one.return_value = None
        mock_mongodb_client.count.return_value = 0

        slo_config = Mock()
        slo_config.target_latency_ms = 1000
        slo_config.target_availability = 0.999
        slo_config.target_error_rate = 0.15  # Acima do máximo de 0.10
        slo_config.latency_percentile = 0.95
        slo_config.time_window_seconds = 60

        request = Mock()
        request.proposed_slos = {"test-service": slo_config}
        request.check_error_budget = False

        result = await servicer.ValidateSLOAdjustment(request, mock_grpc_context)

        assert result["is_valid"] is False
        assert any("error" in e["field"].lower() for e in result["errors"])


class TestRollbackSLOs:
    """Testes para RollbackSLOs."""

    @pytest.mark.asyncio
    async def test_rollback_success(self, servicer, mock_mongodb_client, mock_redis_client, mock_grpc_context):
        """Testa rollback bem-sucedido de SLOs."""

        async def mock_cursor():
            yield {
                "optimization_id": "slo-123",
                "service": "consensus-engine",
                "slo_before": {
                    "target_latency_ms": 1000,
                    "target_availability": 0.999,
                    "target_error_rate": 0.01,
                },
                "slo_after": {
                    "target_latency_ms": 800,
                    "target_availability": 0.9995,
                    "target_error_rate": 0.008,
                },
                "was_rolled_back": False,
            }

        mock_mongodb_client.find.return_value = mock_cursor()

        request = Mock()
        request.optimization_id = "slo-123"
        request.services = []
        request.force = False

        result = await servicer.RollbackSLOs(request, mock_grpc_context)

        assert result["success"] is True
        assert "consensus-engine" in result["restored_slos"]
        mock_mongodb_client.update_one.assert_called()
        mock_redis_client.delete.assert_called()

    @pytest.mark.asyncio
    async def test_rollback_not_found(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa rollback quando otimização não existe."""

        async def empty_cursor():
            return
            yield

        mock_mongodb_client.find.return_value = empty_cursor()

        request = Mock()
        request.optimization_id = "slo-not-found"
        request.services = []
        request.force = False

        with pytest.raises(Exception) as excinfo:
            await servicer.RollbackSLOs(request, mock_grpc_context)

        assert "não encontrada" in str(excinfo.value)


class TestGetSLOComplianceMetrics:
    """Testes para GetSLOComplianceMetrics."""

    @pytest.mark.asyncio
    async def test_get_compliance_metrics_success(
        self, servicer, mock_clickhouse_client, mock_mongodb_client, mock_grpc_context
    ):
        """Testa obtenção de métricas de compliance."""
        mock_clickhouse_client.query.return_value = [
            {
                "avg_latency": 850,
                "p95_latency": 1100,
                "p99_latency": 1500,
                "availability": 0.9998,
                "error_rate": 0.005,
                "avg_throughput": 1200,
                "slo_violations": 2,
            }
        ]
        mock_mongodb_client.find_one.return_value = {
            "service": "consensus-engine",
            "target_latency_ms": 1000,
            "target_availability": 0.999,
            "target_error_rate": 0.01,
            "active": True,
        }

        request = Mock()
        request.service = "consensus-engine"
        request.time_range = "1h"

        result = await servicer.GetSLOComplianceMetrics(request, mock_grpc_context)

        assert result["service"] == "consensus-engine"
        assert "compliance_percentage" in result
        assert "average_latency_ms" in result
        assert "metric_compliance" in result


class TestGetErrorBudget:
    """Testes para GetErrorBudget."""

    @pytest.mark.asyncio
    async def test_get_error_budget_success(
        self, servicer, mock_mongodb_client, mock_clickhouse_client, mock_grpc_context
    ):
        """Testa obtenção de error budget."""
        mock_mongodb_client.find_one.return_value = {
            "service": "consensus-engine",
            "target_availability": 0.999,
            "active": True,
        }
        mock_mongodb_client.count.return_value = 5  # 5 violations
        mock_clickhouse_client.query.return_value = [{"burn_rate": 0.002}]

        request = Mock()
        request.service = "consensus-engine"

        result = await servicer.GetErrorBudget(request, mock_grpc_context)

        assert result["service"] == "consensus-engine"
        assert "remaining_budget_percentage" in result
        assert "consumed_budget" in result
        assert "burn_rate_per_hour" in result


class TestGetSLOHistory:
    """Testes para GetSLOHistory."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa obtenção de histórico de ajustes."""

        async def mock_cursor():
            yield {
                "optimization_id": "slo-1",
                "adjusted_at": 1699056000000,
                "service": "consensus-engine",
                "slo_before": {"target_latency_ms": 1000},
                "slo_after": {"target_latency_ms": 900},
                "justification": "Test adjustment",
                "was_rolled_back": False,
            }
            yield {
                "optimization_id": "slo-2",
                "adjusted_at": 1699059600000,
                "service": "consensus-engine",
                "slo_before": {"target_latency_ms": 900},
                "slo_after": {"target_latency_ms": 850},
                "justification": "Another adjustment",
                "was_rolled_back": False,
            }

        mock_mongodb_client.count.return_value = 2
        mock_mongodb_client.find.return_value = mock_cursor()

        request = Mock()
        request.HasField = Mock(return_value=False)
        request.limit = 10
        request.offset = 0

        result = await servicer.GetSLOHistory(request, mock_grpc_context)

        assert result["total"] == 2
        assert len(result["adjustments"]) == 2
        assert result["adjustments"][0]["optimization_id"] == "slo-1"
