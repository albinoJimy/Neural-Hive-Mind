"""
Testes de integração para ConsensusOptimizationServicer.

Testa os métodos gRPC para otimização de pesos de especialistas.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
import time

from src.grpc_service.consensus_optimization_servicer import ConsensusOptimizationServicer
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock(spec=Settings)
    settings.redis_cache_ttl = 300
    settings.max_weight_adjustment = 0.15
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
def mock_scheduling_optimizer():
    """Mock do SchedulingOptimizer."""
    optimizer = Mock()
    optimizer.get_q_values = Mock(return_value={"action1": 0.5, "action2": 0.3})
    optimizer.record_reward = Mock()
    return optimizer


@pytest.fixture
def mock_weight_recalibrator():
    """Mock do WeightRecalibrator."""
    recalibrator = AsyncMock()
    return recalibrator


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
    mock_weight_recalibrator,
    mock_mongodb_client,
    mock_redis_client,
    mock_clickhouse_client,
    mock_scheduling_optimizer,
    mock_settings,
    mock_metrics,
):
    """Fixture do ConsensusOptimizationServicer."""
    return ConsensusOptimizationServicer(
        weight_recalibrator=mock_weight_recalibrator,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        clickhouse_client=mock_clickhouse_client,
        scheduling_optimizer=mock_scheduling_optimizer,
        settings=mock_settings,
        metrics=mock_metrics,
    )


class TestGetCurrentWeights:
    """Testes para GetCurrentWeights."""

    @pytest.mark.asyncio
    async def test_get_weights_from_cache(self, servicer, mock_redis_client, mock_grpc_context):
        """Testa obtenção de pesos do cache Redis."""
        cached_weights = {
            "weights": {"technical": 0.20, "safety": 0.25, "business": 0.20, "ethical": 0.20, "legal": 0.15},
            "last_updated_at": 1699056000000,
            "optimization_id": "opt-123",
        }
        mock_redis_client.get_json.return_value = cached_weights

        request = Mock()
        request.HasField = Mock(return_value=False)

        result = await servicer.GetCurrentWeights(request, mock_grpc_context)

        assert result["weights"]["technical"] == 0.20
        assert result["weights"]["safety"] == 0.25
        assert result["optimization_id"] == "opt-123"

    @pytest.mark.asyncio
    async def test_get_weights_from_mongodb_on_cache_miss(
        self, servicer, mock_redis_client, mock_mongodb_client, mock_grpc_context
    ):
        """Testa obtenção de pesos do MongoDB quando cache está vazio."""
        mock_redis_client.get_json.return_value = None
        mock_mongodb_client.find_one.return_value = {
            "weights": {"technical": 0.22, "safety": 0.18, "business": 0.20, "ethical": 0.20, "legal": 0.20},
            "last_updated_at": 1699056000000,
            "optimization_id": "opt-456",
            "active": True,
        }

        request = Mock()
        request.HasField = Mock(return_value=False)

        result = await servicer.GetCurrentWeights(request, mock_grpc_context)

        assert result["weights"]["technical"] == 0.22
        mock_redis_client.set_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_weights_returns_defaults_when_empty(
        self, servicer, mock_redis_client, mock_mongodb_client, mock_grpc_context
    ):
        """Testa retorno de pesos padrão quando não há registros."""
        mock_redis_client.get_json.return_value = None
        mock_mongodb_client.find_one.return_value = None

        request = Mock()
        request.HasField = Mock(return_value=False)

        result = await servicer.GetCurrentWeights(request, mock_grpc_context)

        assert result["weights"]["technical"] == 0.20
        assert result["weights"]["safety"] == 0.20


class TestUpdateWeights:
    """Testes para UpdateWeights."""

    @pytest.mark.asyncio
    async def test_update_weights_success(
        self, servicer, mock_mongodb_client, mock_redis_client, mock_grpc_context
    ):
        """Testa atualização bem-sucedida de pesos."""
        mock_mongodb_client.find_one.return_value = {
            "weights": {"technical": 0.20, "safety": 0.20, "business": 0.20, "ethical": 0.20, "legal": 0.20},
            "active": True,
        }

        request = Mock()
        request.weights = {"technical": 0.25, "safety": 0.20, "business": 0.20, "ethical": 0.18, "legal": 0.17}
        request.justification = "Ajuste baseado em RL"
        request.optimization_id = "opt-789"
        request.validate_before_apply = False
        request.metadata = {}

        result = await servicer.UpdateWeights(request, mock_grpc_context)

        assert result["success"] is True
        assert result["applied_weights"]["technical"] == 0.25
        mock_mongodb_client.insert_one.assert_called()
        mock_redis_client.set_json.assert_called()

    @pytest.mark.asyncio
    async def test_update_weights_with_validation_failure(
        self, servicer, mock_mongodb_client, mock_grpc_context
    ):
        """Testa falha na validação de pesos (soma != 1.0)."""
        mock_mongodb_client.find_one.return_value = None

        request = Mock()
        request.weights = {"technical": 0.50, "safety": 0.50, "business": 0.50, "ethical": 0.20, "legal": 0.20}
        request.justification = "Pesos inválidos"
        request.optimization_id = "opt-invalid"
        request.validate_before_apply = True
        request.metadata = {}

        result = await servicer.UpdateWeights(request, mock_grpc_context)

        assert result["success"] is False
        assert "Validação falhou" in result["message"]


class TestValidateWeightAdjustment:
    """Testes para ValidateWeightAdjustment."""

    @pytest.mark.asyncio
    async def test_validate_valid_weights(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa validação de pesos válidos."""
        mock_mongodb_client.find_one.return_value = None

        request = Mock()
        request.proposed_weights = {"technical": 0.20, "safety": 0.20, "business": 0.20, "ethical": 0.20, "legal": 0.20}

        result = await servicer.ValidateWeightAdjustment(request, mock_grpc_context)

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_invalid_sum(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa validação com soma inválida."""
        mock_mongodb_client.find_one.return_value = None

        request = Mock()
        request.proposed_weights = {"technical": 0.30, "safety": 0.30, "business": 0.30, "ethical": 0.20, "legal": 0.20}

        result = await servicer.ValidateWeightAdjustment(request, mock_grpc_context)

        assert result["is_valid"] is False
        assert any("soma" in e["description"].lower() for e in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_weight_out_of_range(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa validação com peso fora do range."""
        mock_mongodb_client.find_one.return_value = None

        request = Mock()
        request.proposed_weights = {"technical": -0.10, "safety": 0.30, "business": 0.30, "ethical": 0.25, "legal": 0.25}

        result = await servicer.ValidateWeightAdjustment(request, mock_grpc_context)

        assert result["is_valid"] is False
        assert any("0 e 1" in e["description"] for e in result["errors"])


class TestRollbackWeights:
    """Testes para RollbackWeights."""

    @pytest.mark.asyncio
    async def test_rollback_success(self, servicer, mock_mongodb_client, mock_redis_client, mock_grpc_context):
        """Testa rollback bem-sucedido."""
        mock_mongodb_client.find_one.return_value = {
            "optimization_id": "opt-123",
            "weights_before": {"technical": 0.20, "safety": 0.20, "business": 0.20, "ethical": 0.20, "legal": 0.20},
            "weights_after": {"technical": 0.25, "safety": 0.15, "business": 0.20, "ethical": 0.20, "legal": 0.20},
            "was_rolled_back": False,
        }

        request = Mock()
        request.optimization_id = "opt-123"
        request.force = False

        result = await servicer.RollbackWeights(request, mock_grpc_context)

        assert result["success"] is True
        assert result["restored_weights"]["technical"] == 0.20
        mock_mongodb_client.update_one.assert_called()
        mock_redis_client.delete.assert_called()

    @pytest.mark.asyncio
    async def test_rollback_not_found(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa rollback quando otimização não existe."""
        mock_mongodb_client.find_one.return_value = None

        request = Mock()
        request.optimization_id = "opt-not-found"
        request.force = False

        with pytest.raises(Exception) as excinfo:
            await servicer.RollbackWeights(request, mock_grpc_context)

        assert "não encontrada" in str(excinfo.value)


class TestGetConsensusMetrics:
    """Testes para GetConsensusMetrics."""

    @pytest.mark.asyncio
    async def test_get_metrics_success(
        self, servicer, mock_clickhouse_client, mock_mongodb_client, mock_grpc_context
    ):
        """Testa obtenção de métricas de consenso."""
        mock_clickhouse_client.query.return_value = [
            {
                "specialist_type": "technical",
                "avg_divergence": 0.10,
                "avg_confidence": 0.88,
                "avg_risk": 0.12,
                "accuracy": 0.90,
                "contributions": 100,
            }
        ]
        mock_mongodb_client.find_one.return_value = {
            "weights": {"technical": 0.20, "safety": 0.20, "business": 0.20, "ethical": 0.20, "legal": 0.20},
            "active": True,
        }

        request = Mock()
        request.time_range = "1h"

        result = await servicer.GetConsensusMetrics(request, mock_grpc_context)

        assert "average_divergence" in result
        assert "specialist_accuracy" in result
        assert result["total_decisions"] >= 0


class TestGetWeightHistory:
    """Testes para GetWeightHistory."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa obtenção de histórico de ajustes."""

        async def mock_cursor():
            yield {
                "optimization_id": "opt-1",
                "adjusted_at": 1699056000000,
                "weights_before": {"technical": 0.20},
                "weights_after": {"technical": 0.22},
                "justification": "Test adjustment",
                "was_rolled_back": False,
            }
            yield {
                "optimization_id": "opt-2",
                "adjusted_at": 1699059600000,
                "weights_before": {"technical": 0.22},
                "weights_after": {"technical": 0.24},
                "justification": "Another adjustment",
                "was_rolled_back": False,
            }

        mock_mongodb_client.count.return_value = 2
        mock_mongodb_client.find.return_value = mock_cursor()

        request = Mock()
        request.HasField = Mock(return_value=False)
        request.limit = 10
        request.offset = 0

        result = await servicer.GetWeightHistory(request, mock_grpc_context)

        assert result["total"] == 2
        assert len(result["adjustments"]) == 2
        assert result["adjustments"][0]["optimization_id"] == "opt-1"
