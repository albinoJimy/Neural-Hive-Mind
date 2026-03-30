"""
Testes unitários para SLOAdjuster.

Cobre:
- Inicialização e configuração
- Aplicação de ajuste de SLO
- Cálculo de SLOs propostos
- Validação de ajustes
- Verificação de error budget
- Criação de eventos de otimização
- Rollback de ajuste de SLO
- Tratamento de erros
"""
import pytest
from unittest.mock import AsyncMock, Mock
from datetime import datetime

from src.services.slo_adjuster import SLOAdjuster
from src.models.optimization_hypothesis import OptimizationHypothesis, OptimizationType
from src.models.optimization_event import OptimizationEvent, OptimizationType as EventOptimizationType, Adjustment


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock()
    settings.max_weight_adjustment = 0.3
    settings.kafka_bootstrap_servers = "localhost:9092"
    return settings


@pytest.fixture
def mock_orchestrator_client():
    """Mock do OrchestratorGrpcClient."""
    client = AsyncMock()
    client.get_current_slos = AsyncMock(return_value={
        "consensus-engine": {
            "target_latency_ms": 1000,
            "target_availability": 0.99,
            "target_error_rate": 0.01
        }
    })
    client.get_error_budget = AsyncMock(return_value={
        "remaining_budget_percentage": 0.80
    })
    client.validate_slo_adjustment = AsyncMock(return_value=True)
    client.update_slos = AsyncMock(return_value=True)
    client.rollback_slos = AsyncMock(return_value=True)
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
def slo_adjuster(mock_settings, mock_orchestrator_client, mock_mongodb_client, mock_redis_client, mock_optimization_producer, mock_metrics):
    """Fixture do SLOAdjuster."""
    return SLOAdjuster(
        settings=mock_settings,
        orchestrator_client=mock_orchestrator_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        optimization_producer=mock_optimization_producer,
        metrics=mock_metrics
    )


@pytest.fixture
def sample_slo_hypothesis():
    """Hipótese de ajuste de SLO."""
    return OptimizationHypothesis(
        hypothesis_id="hyp-slo-001",
        hypothesis_text="Reduce latency SLO to improve user experience",
        optimization_type=OptimizationType.SLO_ADJUSTMENT,
        target_component="consensus-engine",
        baseline_metrics={"latency_p95": 1000, "availability": 0.99},
        target_metrics={"latency_p95": 900, "availability": 0.99},
        proposed_adjustments=[
            Adjustment(
                parameter="target_latency_ms",
                previous_value=1000,
                new_value="900",
                justification="Infrastructure optimization allows lower latency"
            )
        ],
        expected_improvement=0.10,
        confidence_score=0.80,
        risk_score=0.3,
        priority=3,
        metadata={"state_hash": "def456"}
    )


class TestSLOAdjusterInitialization:
    """Testes de inicialização do SLOAdjuster."""

    def test_initialization_with_all_dependencies(self, mock_settings, mock_orchestrator_client, mock_mongodb_client, mock_redis_client):
        """Testa inicialização com todas as dependências."""
        adjuster = SLOAdjuster(
            settings=mock_settings,
            orchestrator_client=mock_orchestrator_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        assert adjuster.settings == mock_settings
        assert adjuster.orchestrator_client == mock_orchestrator_client
        assert adjuster.mongodb_client == mock_mongodb_client
        assert adjuster.redis_client == mock_redis_client

    def test_initialization_with_optional_dependencies(self, mock_settings):
        """Testa inicialização com dependências opcionais."""
        adjuster = SLOAdjuster(
            settings=mock_settings,
            orchestrator_client=None,
            mongodb_client=None,
            redis_client=None,
            optimization_producer=None,
            metrics=None
        )

        assert adjuster.settings == mock_settings
        assert adjuster.orchestrator_client is None
        assert adjuster.mongodb_client is None
        assert adjuster.redis_client is None
        assert adjuster.optimization_producer is None
        assert adjuster.metrics is None


class TestApplySLOAdjustment:
    """Testes de aplicação de ajuste de SLO."""

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_success(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client, mock_mongodb_client, mock_redis_client, mock_optimization_producer):
        """Testa aplicação bem-sucedida de ajuste de SLO."""
        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is not None
        assert isinstance(result, OptimizationEvent)
        assert result.optimization_type == EventOptimizationType.SLO_ADJUSTMENT

        # Verificar chamadas aos clients
        mock_orchestrator_client.get_current_slos.assert_called_once()
        mock_orchestrator_client.get_error_budget.assert_called_once()
        mock_orchestrator_client.validate_slo_adjustment.assert_called_once()
        mock_orchestrator_client.update_slos.assert_called_once()
        mock_redis_client.lock_component.assert_called_once()
        mock_redis_client.unlock_component.assert_called_once()
        mock_mongodb_client.save_optimization.assert_called_once()
        mock_optimization_producer.publish_optimization.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_invalid_type(self, slo_adjuster, sample_slo_hypothesis):
        """Testa rejeição de tipo de otimização inválido."""
        sample_slo_hypothesis.optimization_type = OptimizationType.WEIGHT_RECALIBRATION

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_failed_to_get_slos(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa falha ao obter SLOs atuais."""
        mock_orchestrator_client.get_current_slos = AsyncMock(return_value=None)

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_insufficient_error_budget(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa bloqueio por error budget insuficiente."""
        mock_orchestrator_client.get_error_budget = AsyncMock(return_value={
            "remaining_budget_percentage": 0.15  # Abaixo do threshold de 20%
        })

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_validation_failed(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa falha na validação de ajuste."""
        mock_orchestrator_client.validate_slo_adjustment = AsyncMock(return_value=False)

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_lock_failed(self, slo_adjuster, sample_slo_hypothesis, mock_redis_client):
        """Testa falha ao adquirir lock."""
        mock_redis_client.lock_component = AsyncMock(return_value=False)

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_update_failed(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa falha ao atualizar SLOs."""
        mock_orchestrator_client.update_slos = AsyncMock(return_value=False)

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_unlocks_on_error(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client, mock_redis_client):
        """Testa que lock é liberado mesmo em caso de erro."""
        mock_orchestrator_client.update_slos = AsyncMock(side_effect=Exception("Update failed"))

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None
        mock_redis_client.unlock_component.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_slo_adjustment_records_metrics(self, slo_adjuster, sample_slo_hypothesis, mock_metrics):
        """Testa registro de métricas."""
        await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        mock_metrics.increment_counter.assert_called_once_with("slo_adjustments_applied_total")


class TestCalculateProposedSLOs:
    """Testes de cálculo de SLOs propostos."""

    def test_calculate_proposed_slos_latency(self, slo_adjuster):
        """Testa cálculo de SLO de latência."""
        current_slos = {"target_latency_ms": 1000}
        adjustments = [
            {"parameter": "target_latency_ms", "new_value": 900}
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        assert proposed["target_latency_ms"] == 900

    def test_calculate_proposed_slos_latency_clamps_change(self, slo_adjuster):
        """Testa limitação de mudança de latência (max 30%)."""
        current_slos = {"target_latency_ms": 1000}
        adjustments = [
            {"parameter": "target_latency_ms", "new_value": 100}  # Tentar reduzir 90%
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        # Mudança deve ser limitada a 30%
        assert proposed["target_latency_ms"] >= 700  # 1000 * 0.7

    def test_calculate_proposed_slos_latency_minimum(self, slo_adjuster):
        """Testa limite mínimo de latência."""
        current_slos = {"target_latency_ms": 150}
        adjustments = [
            {"parameter": "target_latency_ms", "new_value": 50}
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        # Latência mínima é 100ms
        assert proposed["target_latency_ms"] >= 100

    def test_calculate_proposed_slos_availability(self, slo_adjuster):
        """Testa cálculo de SLO de disponibilidade."""
        current_slos = {"target_availability": 0.99}
        adjustments = [
            {"parameter": "target_availability", "new_value": 0.995}
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        # Disponibilidade deve estar entre 0.95 e 0.9999
        assert 0.95 <= proposed["target_availability"] <= 0.9999

    def test_calculate_proposed_slos_availability_upper_bound(self, slo_adjuster):
        """Testa limite superior de disponibilidade."""
        current_slos = {"target_availability": 0.99}
        adjustments = [
            {"parameter": "target_availability", "new_value": 0.99999}
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        # Deve ser limitado a 0.9999
        assert proposed["target_availability"] <= 0.9999

    def test_calculate_proposed_slos_error_rate(self, slo_adjuster):
        """Testa cálculo de SLO de error rate."""
        current_slos = {"target_error_rate": 0.01}
        adjustments = [
            {"parameter": "target_error_rate", "new_value": 0.005}
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        # Error rate deve estar entre 0.001 e 0.10
        assert 0.001 <= proposed["target_error_rate"] <= 0.10

    def test_calculate_proposed_slos_unknown_parameter(self, slo_adjuster):
        """Testa parâmetro desconhecido."""
        current_slos = {"target_latency_ms": 1000}
        adjustments = [
            {"parameter": "unknown_param", "new_value": 500}
        ]

        proposed = slo_adjuster._calculate_proposed_slos(current_slos, adjustments)

        # Parâmetro desconhecido não deve ser adicionado
        assert "unknown_param" not in proposed
        assert proposed["target_latency_ms"] == 1000


class TestCreateOptimizationEvent:
    """Testes de criação de evento de otimização."""

    def test_create_optimization_event_basic(self, slo_adjuster, sample_slo_hypothesis):
        """Testa criação básica de evento."""
        baseline_slos = {"target_latency_ms": 1000, "target_availability": 0.99}
        optimized_slos = {"target_latency_ms": 900, "target_availability": 0.99}

        event = slo_adjuster._create_optimization_event(
            hypothesis=sample_slo_hypothesis,
            baseline_slos=baseline_slos,
            optimized_slos=optimized_slos
        )

        assert event.optimization_id == sample_slo_hypothesis.hypothesis_id
        assert event.optimization_type == EventOptimizationType.SLO_ADJUSTMENT
        assert event.target_component == sample_slo_hypothesis.target_component
        assert event.improvement_percentage == sample_slo_hypothesis.expected_improvement

    def test_create_optimization_event_includes_adjustments(self, slo_adjuster, sample_slo_hypothesis):
        """Testa que evento inclui ajustes."""
        baseline_slos = {"target_latency_ms": 1000}
        optimized_slos = {"target_latency_ms": 900}

        event = slo_adjuster._create_optimization_event(
            hypothesis=sample_slo_hypothesis,
            baseline_slos=baseline_slos,
            optimized_slos=optimized_slos
        )

        # Deve ter ajustes para parâmetros que mudaram
        assert len(event.adjustments) > 0
        adjustment = event.adjustments[0]
        assert hasattr(adjustment, 'parameter')
        assert hasattr(adjustment, 'previous_value')
        assert hasattr(adjustment, 'new_value')

    def test_create_optimization_event_includes_causal_analysis(self, slo_adjuster, sample_slo_hypothesis):
        """Testa que evento inclui análise causal."""
        baseline_slos = {"target_latency_ms": 1000}
        optimized_slos = {"target_latency_ms": 900}

        event = slo_adjuster._create_optimization_event(
            hypothesis=sample_slo_hypothesis,
            baseline_slos=baseline_slos,
            optimized_slos=optimized_slos
        )

        assert event.causal_analysis is not None
        assert event.causal_analysis.root_cause is not None
        assert len(event.causal_analysis.contributing_factors) > 0

    def test_create_optimization_event_includes_rollback_plan(self, slo_adjuster, sample_slo_hypothesis):
        """Testa que evento inclui plano de rollback."""
        baseline_slos = {"target_latency_ms": 1000}
        optimized_slos = {"target_latency_ms": 900}

        event = slo_adjuster._create_optimization_event(
            hypothesis=sample_slo_hypothesis,
            baseline_slos=baseline_slos,
            optimized_slos=optimized_slos
        )

        assert event.rollback_plan is not None
        assert event.rollback_plan.rollback_strategy is not None
        assert len(event.rollback_plan.rollback_steps) > 0
        assert len(event.rollback_plan.validation_criteria) > 0


class TestRollbackSLOAdjustment:
    """Testes de rollback de ajuste de SLO."""

    @pytest.mark.asyncio
    async def test_rollback_slo_adjustment_success(self, slo_adjuster, mock_orchestrator_client, mock_metrics):
        """Testa rollback bem-sucedido."""
        optimization_id = "opt-001"

        result = await slo_adjuster.rollback_slo_adjustment(optimization_id)

        assert result is True
        mock_orchestrator_client.rollback_slos.assert_called_once_with(optimization_id)
        mock_metrics.increment_counter.assert_called_once_with("slo_adjustments_rolled_back_total")

    @pytest.mark.asyncio
    async def test_rollback_slo_adjustment_failure(self, slo_adjuster, mock_orchestrator_client):
        """Testa rollback com falha."""
        mock_orchestrator_client.rollback_slos = AsyncMock(return_value=False)
        optimization_id = "opt-002"

        result = await slo_adjuster.rollback_slo_adjustment(optimization_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_rollback_slo_adjustment_exception(self, slo_adjuster, mock_orchestrator_client):
        """Testa rollback com exceção."""
        mock_orchestrator_client.rollback_slos = AsyncMock(side_effect=Exception("Rollback failed"))
        optimization_id = "opt-003"

        result = await slo_adjuster.rollback_slo_adjustment(optimization_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_rollback_without_metrics(self, slo_adjuster, mock_orchestrator_client):
        """Testa rollback sem métricas configuradas."""
        slo_adjuster.metrics = None
        optimization_id = "opt-004"

        result = await slo_adjuster.rollback_slo_adjustment(optimization_id)

        assert result is True
        # Não deve tentar chamar increment_counter


class TestErrorBudgetValidation:
    """Testes de validação de error budget."""

    @pytest.mark.asyncio
    async def test_sufficient_error_budget(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa aprovação com error budget suficiente."""
        mock_orchestrator_client.get_error_budget = AsyncMock(return_value={
            "remaining_budget_percentage": 0.50  # Acima do threshold de 20%
        })

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        # Deve permitir a operação (retornar evento, não None)
        assert result is not None

    @pytest.mark.asyncio
    async def test_insufficient_error_budget_blocks(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa bloqueio com error budget insuficiente."""
        mock_orchestrator_client.get_error_budget = AsyncMock(return_value={
            "remaining_budget_percentage": 0.10  # Abaixo do threshold de 20%
        })

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        assert result is None

    @pytest.mark.asyncio
    async def test_exact_threshold_error_budget(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa comportamento no limite exato do threshold."""
        mock_orchestrator_client.get_error_budget = AsyncMock(return_value={
            "remaining_budget_percentage": 0.20  # Exatamente no threshold
        })

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        # Deve bloquear (verificação é < 0.2, não <=)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_error_budget_response(self, slo_adjuster, sample_slo_hypothesis, mock_orchestrator_client):
        """Testa comportamento quando não há resposta de error budget."""
        mock_orchestrator_client.get_error_budget = AsyncMock(return_value=None)

        result = await slo_adjuster.apply_slo_adjustment(sample_slo_hypothesis)

        # Deve permitir (None significa que não há dados de error budget)
        assert result is not None
