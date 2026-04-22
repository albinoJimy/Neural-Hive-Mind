"""
Testes unitários para WeightRecalibrator.

Cobre:
- Inicialização e configuração
- Aplicação de recalibração de pesos
- Cálculo de pesos propostos
- Validação de ajustes
- Criação de eventos de otimização
- Rollback de recalibração
- Tratamento de erros
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.models.optimization_event import (
    Adjustment,
    OptimizationEvent,
)
from src.models.optimization_event import (
    OptimizationType as EventOptimizationType,
)
from src.models.optimization_hypothesis import OptimizationHypothesis, OptimizationType
from src.services.weight_recalibrator import WeightRecalibrator


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock()
    settings.max_weight_adjustment = 0.3
    settings.kafka_bootstrap_servers = "localhost:9092"
    return settings


@pytest.fixture
def mock_consensus_client():
    """Mock do ConsensusEngineGrpcClient."""
    client = AsyncMock()
    client.get_current_weights = AsyncMock(
        return_value={"business": 0.25, "technical": 0.25, "architecture": 0.25, "behavior": 0.25}
    )
    client.validate_weight_adjustment = AsyncMock(return_value=True)
    client.update_weights = AsyncMock(return_value=True)
    client.rollback_weights = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient."""
    client = AsyncMock()
    client.save_optimization = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do RedisClient."""
    client = AsyncMock()
    client.lock_component = AsyncMock(return_value=True)
    client.unlock_component = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_optimization_producer():
    """Mock do OptimizationProducer."""
    producer = AsyncMock()
    producer.publish_optimization = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def mock_metrics():
    """Mock de métricas."""
    metrics = Mock()
    metrics.increment_counter = Mock()
    return metrics


@pytest.fixture
def weight_recalibrator(
    mock_settings,
    mock_consensus_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_optimization_producer,
    mock_metrics,
):
    """Fixture do WeightRecalibrator."""
    return WeightRecalibrator(
        settings=mock_settings,
        consensus_client=mock_consensus_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        optimization_producer=mock_optimization_producer,
        metrics=mock_metrics,
    )


@pytest.fixture
def sample_weight_hypothesis():
    """Hipótese de recalibração de pesos."""
    return OptimizationHypothesis(
        hypothesis_id="hyp-weight-001",
        hypothesis_text="Increase technical specialist weight to improve consensus",
        optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
        target_component="consensus-engine",
        baseline_metrics={"divergence": 0.15, "confidence": 0.80},
        target_metrics={"divergence": 0.10, "confidence": 0.85},
        proposed_adjustments=[
            Adjustment(
                parameter="technical",
                previous_value=0.25,
                new_value="0.30",
                justification="Technical specialist showing improved accuracy",
            )
        ],
        expected_improvement=0.15,
        confidence_score=0.85,
        risk_score=0.2,
        priority=4,
        metadata={"state_hash": "abc123"},
    )


class TestWeightRecalibratorInitialization:
    """Testes de inicialização do WeightRecalibrator."""

    def test_initialization_with_all_dependencies(
        self, mock_settings, mock_consensus_client, mock_mongodb_client, mock_redis_client
    ):
        """Testa inicialização com todas as dependências."""
        recalibrator = WeightRecalibrator(
            settings=mock_settings,
            consensus_client=mock_consensus_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client,
        )

        assert recalibrator.settings == mock_settings
        assert recalibrator.consensus_client == mock_consensus_client
        assert recalibrator.mongodb_client == mock_mongodb_client
        assert recalibrator.redis_client == mock_redis_client

    def test_initialization_with_optional_dependencies(self, mock_settings):
        """Testa inicialização com dependências opcionais."""
        recalibrator = WeightRecalibrator(
            settings=mock_settings,
            consensus_client=None,
            mongodb_client=None,
            redis_client=None,
            optimization_producer=None,
            metrics=None,
        )

        assert recalibrator.settings == mock_settings
        assert recalibrator.consensus_client is None
        assert recalibrator.mongodb_client is None
        assert recalibrator.redis_client is None
        assert recalibrator.optimization_producer is None
        assert recalibrator.metrics is None


class TestApplyWeightRecalibration:
    """Testes de aplicação de recalibração de pesos."""

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_success(
        self,
        weight_recalibrator,
        sample_weight_hypothesis,
        mock_consensus_client,
        mock_mongodb_client,
        mock_redis_client,
        mock_optimization_producer,
    ):
        """Testa aplicação bem-sucedida de recalibração."""
        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is not None
        assert isinstance(result, OptimizationEvent)
        assert result.optimization_type == EventOptimizationType.WEIGHT_RECALIBRATION

        # Verificar chamadas aos clients
        mock_consensus_client.get_current_weights.assert_called_once()
        mock_consensus_client.validate_weight_adjustment.assert_called_once()
        mock_consensus_client.update_weights.assert_called_once()
        mock_redis_client.lock_component.assert_called_once_with("consensus-engine")
        mock_redis_client.unlock_component.assert_called_once_with("consensus-engine")
        mock_mongodb_client.save_optimization.assert_called_once()
        mock_optimization_producer.publish_optimization.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_invalid_type(
        self, weight_recalibrator, sample_weight_hypothesis
    ):
        """Testa rejeição de tipo de otimização inválido."""
        sample_weight_hypothesis.optimization_type = OptimizationType.SLO_ADJUSTMENT

        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_failed_to_get_weights(
        self, weight_recalibrator, sample_weight_hypothesis, mock_consensus_client
    ):
        """Testa falha ao obter pesos atuais."""
        mock_consensus_client.get_current_weights = AsyncMock(return_value=None)

        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_validation_failed(
        self, weight_recalibrator, sample_weight_hypothesis, mock_consensus_client
    ):
        """Testa falha na validação de ajuste."""
        mock_consensus_client.validate_weight_adjustment = AsyncMock(return_value=False)

        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_lock_failed(
        self, weight_recalibrator, sample_weight_hypothesis, mock_redis_client
    ):
        """Testa falha ao adquirir lock."""
        mock_redis_client.lock_component = AsyncMock(return_value=False)

        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_update_failed(
        self, weight_recalibrator, sample_weight_hypothesis, mock_consensus_client
    ):
        """Testa falha ao atualizar pesos."""
        mock_consensus_client.update_weights = AsyncMock(return_value=False)

        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_unlocks_on_error(
        self,
        weight_recalibrator,
        sample_weight_hypothesis,
        mock_consensus_client,
        mock_redis_client,
    ):
        """Testa que lock é liberado mesmo em caso de erro."""
        mock_consensus_client.update_weights = AsyncMock(side_effect=Exception("Update failed"))

        result = await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        assert result is None
        mock_redis_client.unlock_component.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_weight_recalibration_records_metrics(
        self, weight_recalibrator, sample_weight_hypothesis, mock_metrics
    ):
        """Testa registro de métricas."""
        await weight_recalibrator.apply_weight_recalibration(sample_weight_hypothesis)

        mock_metrics.increment_counter.assert_called_once_with(
            "weight_recalibrations_applied_total"
        )


class TestCalculateProposedWeights:
    """Testes de cálculo de pesos propostos."""

    def test_calculate_proposed_weights_basic(self, weight_recalibrator):
        """Testa cálculo básico de pesos propostos."""
        current_weights = {
            "business": 0.25,
            "technical": 0.25,
            "architecture": 0.25,
            "behavior": 0.25,
        }
        adjustments = [{"parameter": "technical", "new_value": 0.05}]  # Aumentar em 0.05

        proposed = weight_recalibrator._calculate_proposed_weights(current_weights, adjustments)

        assert proposed["technical"] > current_weights["technical"]
        assert abs(sum(proposed.values()) - 1.0) < 0.001  # Deve somar ~1.0

    def test_calculate_proposed_weights_clamps_delta(self, weight_recalibrator):
        """Testa que delta é limitado pelo max_weight_adjustment."""
        current_weights = {"business": 0.5, "technical": 0.5}
        adjustments = [{"parameter": "technical", "new_value": 1.0}]  # Tentar aumentar muito

        proposed = weight_recalibrator._calculate_proposed_weights(current_weights, adjustments)

        # Delta deve ser limitado a max_weight_adjustment (0.3)
        assert proposed["technical"] <= 0.8

    def test_calculate_proposed_weights_bounds(self, weight_recalibrator):
        """Testa limites de peso (0.0 a 1.0)."""
        current_weights = {"business": 1.0}
        adjustments = [{"parameter": "business", "new_value": -2.0}]  # Tentar diminuir muito

        proposed = weight_recalibrator._calculate_proposed_weights(current_weights, adjustments)

        # Peso deve estar entre 0.0 e 1.0
        assert 0.0 <= proposed["business"] <= 1.0

    def test_calculate_proposed_weights_normalizes(self, weight_recalibrator):
        """Testa normalização de pesos."""
        current_weights = {
            "business": 0.25,
            "technical": 0.25,
            "architecture": 0.25,
            "behavior": 0.25,
        }
        adjustments = [{"parameter": "technical", "new_value": 0.5}]

        proposed = weight_recalibrator._calculate_proposed_weights(current_weights, adjustments)

        # Soma deve ser exatamente 1.0 após normalização
        assert abs(sum(proposed.values()) - 1.0) < 0.0001

    def test_calculate_proposed_weights_unknown_parameter(self, weight_recalibrator):
        """Testa parâmetro desconhecido."""
        current_weights = {"business": 0.5, "technical": 0.5}
        adjustments = [{"parameter": "unknown", "new_value": 0.1}]

        proposed = weight_recalibrator._calculate_proposed_weights(current_weights, adjustments)

        # Parâmetro desconhecido não deve ser adicionado
        assert "unknown" not in proposed
        assert len(proposed) == 2


class TestCreateOptimizationEvent:
    """Testes de criação de evento de otimização."""

    def test_create_optimization_event_basic(self, weight_recalibrator, sample_weight_hypothesis):
        """Testa criação básica de evento."""
        baseline_weights = {
            "business": 0.25,
            "technical": 0.25,
            "architecture": 0.25,
            "behavior": 0.25,
        }
        optimized_weights = {
            "business": 0.20,
            "technical": 0.35,
            "architecture": 0.25,
            "behavior": 0.20,
        }

        event = weight_recalibrator._create_optimization_event(
            hypothesis=sample_weight_hypothesis,
            baseline_weights=baseline_weights,
            optimized_weights=optimized_weights,
        )

        assert event.optimization_id == sample_weight_hypothesis.hypothesis_id
        assert event.optimization_type == EventOptimizationType.WEIGHT_RECALIBRATION
        assert event.target_component == sample_weight_hypothesis.target_component
        assert event.improvement_percentage == sample_weight_hypothesis.expected_improvement
        assert len(event.adjustments) > 0

    def test_create_optimization_event_includes_adjustments(
        self, weight_recalibrator, sample_weight_hypothesis
    ):
        """Testa que evento inclui ajustes."""
        baseline_weights = {"business": 0.25, "technical": 0.25}
        optimized_weights = {"business": 0.20, "technical": 0.30}

        event = weight_recalibrator._create_optimization_event(
            hypothesis=sample_weight_hypothesis,
            baseline_weights=baseline_weights,
            optimized_weights=optimized_weights,
        )

        # Deve ter ajustes para pesos que mudaram
        assert len(event.adjustments) > 0
        # Verificar que ajuste tem estrutura correta
        adjustment = event.adjustments[0]
        assert hasattr(adjustment, "parameter")
        assert hasattr(adjustment, "previous_value")
        assert hasattr(adjustment, "new_value")

    def test_create_optimization_event_includes_causal_analysis(
        self, weight_recalibrator, sample_weight_hypothesis
    ):
        """Testa que evento inclui análise causal."""
        baseline_weights = {"business": 0.25, "technical": 0.25}
        optimized_weights = {"business": 0.20, "technical": 0.30}

        event = weight_recalibrator._create_optimization_event(
            hypothesis=sample_weight_hypothesis,
            baseline_weights=baseline_weights,
            optimized_weights=optimized_weights,
        )

        assert event.causal_analysis is not None
        assert event.causal_analysis.root_cause is not None
        assert len(event.causal_analysis.contributing_factors) > 0

    def test_create_optimization_event_includes_rollback_plan(
        self, weight_recalibrator, sample_weight_hypothesis
    ):
        """Testa que evento inclui plano de rollback."""
        baseline_weights = {"business": 0.25, "technical": 0.25}
        optimized_weights = {"business": 0.20, "technical": 0.30}

        event = weight_recalibrator._create_optimization_event(
            hypothesis=sample_weight_hypothesis,
            baseline_weights=baseline_weights,
            optimized_weights=optimized_weights,
        )

        assert event.rollback_plan is not None
        assert event.rollback_plan.rollback_strategy is not None
        assert len(event.rollback_plan.rollback_steps) > 0
        assert len(event.rollback_plan.validation_criteria) > 0


class TestRollbackWeightRecalibration:
    """Testes de rollback de recalibração."""

    @pytest.mark.asyncio
    async def test_rollback_weight_recalibration_success(
        self, weight_recalibrator, mock_consensus_client, mock_metrics
    ):
        """Testa rollback bem-sucedido."""
        optimization_id = "opt-001"

        result = await weight_recalibrator.rollback_weight_recalibration(optimization_id)

        assert result is True
        mock_consensus_client.rollback_weights.assert_called_once_with(optimization_id)
        mock_metrics.increment_counter.assert_called_once_with(
            "weight_recalibrations_rolled_back_total"
        )

    @pytest.mark.asyncio
    async def test_rollback_weight_recalibration_failure(
        self, weight_recalibrator, mock_consensus_client
    ):
        """Testa rollback com falha."""
        mock_consensus_client.rollback_weights = AsyncMock(return_value=False)
        optimization_id = "opt-002"

        result = await weight_recalibrator.rollback_weight_recalibration(optimization_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_rollback_weight_recalibration_exception(
        self, weight_recalibrator, mock_consensus_client
    ):
        """Testa rollback com exceção."""
        mock_consensus_client.rollback_weights = AsyncMock(side_effect=Exception("Rollback failed"))
        optimization_id = "opt-003"

        result = await weight_recalibrator.rollback_weight_recalibration(optimization_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_rollback_without_metrics(self, weight_recalibrator, mock_consensus_client):
        """Testa rollback sem métricas configuradas."""
        weight_recalibrator.metrics = None
        optimization_id = "opt-004"

        result = await weight_recalibrator.rollback_weight_recalibration(optimization_id)

        assert result is True
        # Não deve tentar chamar increment_counter
