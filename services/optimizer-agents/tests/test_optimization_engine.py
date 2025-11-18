"""
Testes unitários para OptimizationEngine.

Cobre:
- Inicialização
- Geração de hipóteses
- Política epsilon-greedy
- Cálculo de recompensa
- Atualização da Q-table
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.services.optimization_engine import OptimizationEngine
from src.models.optimization_event import OptimizationType
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock(spec=Settings)
    settings.learning_rate = 0.1
    settings.exploration_rate = 0.2
    settings.discount_factor = 0.95
    settings.min_improvement_threshold = 0.05
    settings.min_confidence_threshold = 0.7
    return settings


@pytest.fixture
def optimization_engine(mock_settings):
    """Fixture do OptimizationEngine."""
    return OptimizationEngine(settings=mock_settings)


class TestOptimizationEngineInitialization:
    """Testes de inicialização do OptimizationEngine."""

    def test_initialization_with_default_settings(self):
        """Testa inicialização com settings default."""
        engine = OptimizationEngine()
        assert engine.q_table is not None
        assert engine.reward_history == []
        assert len(engine.action_space) == 4

    def test_initialization_with_custom_settings(self, mock_settings):
        """Testa inicialização com settings customizados."""
        engine = OptimizationEngine(settings=mock_settings)
        assert engine.learning_rate == 0.1
        assert engine.exploration_rate == 0.2
        assert engine.discount_factor == 0.95

    def test_action_space_contains_all_types(self, optimization_engine):
        """Testa se action space contém todos os tipos de otimização."""
        assert OptimizationType.WEIGHT_RECALIBRATION in optimization_engine.action_space
        assert OptimizationType.SLO_ADJUSTMENT in optimization_engine.action_space
        assert OptimizationType.HEURISTIC_UPDATE in optimization_engine.action_space
        assert OptimizationType.POLICY_CHANGE in optimization_engine.action_space


class TestHypothesisGeneration:
    """Testes de geração de hipóteses."""

    def test_analyze_opportunity_operational_insight(self, optimization_engine):
        """Testa geração de hipóteses para insight operacional."""
        insight = {
            "insight_id": "test-insight-1",
            "insight_type": "OPERATIONAL_BOTTLENECK",
            "metrics": {
                "latency_p95": 1200,
                "error_rate": 0.05,
                "throughput": 100
            },
            "related_entities": [{"entity_id": "consensus-engine"}],
        }

        hypotheses = optimization_engine.analyze_opportunity(insight)

        assert len(hypotheses) > 0
        # Para insights operacionais, deve considerar WEIGHT_RECALIBRATION ou SLO_ADJUSTMENT
        optimization_types = [h.optimization_type for h in hypotheses]
        assert any(t in [OptimizationType.WEIGHT_RECALIBRATION, OptimizationType.SLO_ADJUSTMENT]
                   for t in optimization_types)

    def test_analyze_opportunity_strategic_insight(self, optimization_engine):
        """Testa geração de hipóteses para insight estratégico."""
        insight = {
            "insight_id": "test-insight-2",
            "insight_type": "STRATEGIC_IMPROVEMENT",
            "metrics": {
                "compliance_rate": 0.92,
                "cost_efficiency": 0.85
            },
            "related_entities": [{"entity_id": "orchestrator-dynamic"}],
        }

        hypotheses = optimization_engine.analyze_opportunity(insight)

        assert len(hypotheses) > 0
        # Para insights estratégicos, deve considerar POLICY_CHANGE ou HEURISTIC_UPDATE
        optimization_types = [h.optimization_type for h in hypotheses]
        assert any(t in [OptimizationType.POLICY_CHANGE, OptimizationType.HEURISTIC_UPDATE]
                   for t in optimization_types)

    def test_analyze_opportunity_filters_infeasible_hypotheses(self, optimization_engine):
        """Testa que hipóteses inviáveis são filtradas."""
        insight = {
            "insight_id": "test-insight-3",
            "insight_type": "OPERATIONAL_BOTTLENECK",
            "metrics": {},  # Métricas vazias podem gerar hipóteses inviáveis
            "related_entities": [{"entity_id": "test-component"}],
        }

        with patch.object(optimization_engine, 'generate_hypothesis') as mock_generate:
            # Simular hipótese inviável
            mock_hypothesis = Mock()
            mock_hypothesis.validate_feasibility.return_value = False
            mock_generate.return_value = mock_hypothesis

            hypotheses = optimization_engine.analyze_opportunity(insight)

            # Hipóteses inviáveis devem ser filtradas
            assert len(hypotheses) == 0


class TestEpsilonGreedyPolicy:
    """Testes da política epsilon-greedy."""

    def test_select_action_exploration(self, optimization_engine):
        """Testa seleção de ação durante exploração."""
        state = {"latency": 1000, "error_rate": 0.01}

        # Com exploration_rate = 0.2, deve explorar ~20% das vezes
        with patch('random.random', return_value=0.1):  # < exploration_rate
            action = optimization_engine.select_action(state)
            assert action in optimization_engine.action_space

    def test_select_action_exploitation(self, optimization_engine):
        """Testa seleção de ação durante exploitation (usa Q-table)."""
        state = {"latency": 1000, "error_rate": 0.01}
        state_hash = optimization_engine._hash_state(state)

        # Pre-popular Q-table com valores conhecidos
        optimization_engine.q_table[state_hash][OptimizationType.WEIGHT_RECALIBRATION] = 10.0
        optimization_engine.q_table[state_hash][OptimizationType.SLO_ADJUSTMENT] = 5.0

        # Com random > exploration_rate, deve escolher melhor ação
        with patch('random.random', return_value=0.9):  # > exploration_rate
            action = optimization_engine.select_action(state)
            assert action == OptimizationType.WEIGHT_RECALIBRATION

    def test_select_action_returns_valid_action(self, optimization_engine):
        """Testa que sempre retorna uma ação válida."""
        state = {"latency": 500, "error_rate": 0.005}

        for _ in range(10):  # Testar múltiplas vezes
            action = optimization_engine.select_action(state)
            assert action in optimization_engine.action_space


class TestRewardCalculation:
    """Testes de cálculo de recompensa."""

    def test_calculate_reward_positive_improvement(self, optimization_engine):
        """Testa recompensa para melhoria positiva."""
        baseline = {"latency_p95": 1000, "error_rate": 0.05}
        achieved = {"latency_p95": 800, "error_rate": 0.03}

        reward = optimization_engine.calculate_reward(baseline, achieved)

        # Melhoria em latência e error_rate deve resultar em recompensa positiva
        assert reward > 0

    def test_calculate_reward_negative_degradation(self, optimization_engine):
        """Testa recompensa para degradação."""
        baseline = {"latency_p95": 800, "error_rate": 0.03}
        achieved = {"latency_p95": 1200, "error_rate": 0.08}

        reward = optimization_engine.calculate_reward(baseline, achieved)

        # Degradação deve resultar em recompensa negativa
        assert reward < 0

    def test_calculate_reward_no_change(self, optimization_engine):
        """Testa recompensa quando não há mudança significativa."""
        baseline = {"latency_p95": 1000, "error_rate": 0.05}
        achieved = {"latency_p95": 1000, "error_rate": 0.05}

        reward = optimization_engine.calculate_reward(baseline, achieved)

        # Sem mudança deve resultar em recompensa próxima de zero
        assert abs(reward) < 0.1


class TestQTableUpdate:
    """Testes de atualização da Q-table."""

    def test_update_q_value_increases_for_positive_reward(self, optimization_engine):
        """Testa que Q-value aumenta para recompensa positiva."""
        state = {"latency": 1000, "error_rate": 0.05}
        state_hash = optimization_engine._hash_state(state)
        action = OptimizationType.WEIGHT_RECALIBRATION

        # Valor inicial
        initial_q_value = optimization_engine.q_table[state_hash][action]

        # Atualizar com recompensa positiva
        optimization_engine.update_q_value(state, action, reward=5.0, next_state=state)

        # Q-value deve ter aumentado
        assert optimization_engine.q_table[state_hash][action] > initial_q_value

    def test_update_q_value_decreases_for_negative_reward(self, optimization_engine):
        """Testa que Q-value diminui para recompensa negativa."""
        state = {"latency": 1000, "error_rate": 0.05}
        state_hash = optimization_engine._hash_state(state)
        action = OptimizationType.SLO_ADJUSTMENT

        # Definir valor inicial positivo
        optimization_engine.q_table[state_hash][action] = 10.0
        initial_q_value = optimization_engine.q_table[state_hash][action]

        # Atualizar com recompensa negativa
        optimization_engine.update_q_value(state, action, reward=-5.0, next_state=state)

        # Q-value deve ter diminuído
        assert optimization_engine.q_table[state_hash][action] < initial_q_value

    def test_update_q_value_records_in_history(self, optimization_engine):
        """Testa que atualização é registrada no histórico."""
        state = {"latency": 1000, "error_rate": 0.05}
        action = OptimizationType.WEIGHT_RECALIBRATION
        reward = 3.5

        initial_history_len = len(optimization_engine.reward_history)

        optimization_engine.update_q_value(state, action, reward, next_state=state)

        # Histórico deve ter crescido
        assert len(optimization_engine.reward_history) == initial_history_len + 1
        # Último registro deve conter estado, ação e recompensa
        last_record = optimization_engine.reward_history[-1]
        assert last_record[2] == reward


class TestStateExtraction:
    """Testes de extração e hashing de estado."""

    def test_extract_state_from_metrics(self, optimization_engine):
        """Testa extração de estado a partir de métricas."""
        metrics = {
            "latency_p95": 1200,
            "error_rate": 0.05,
            "throughput": 100,
            "cpu_usage": 0.75,
        }

        state = optimization_engine._extract_state(metrics)

        assert "latency" in state
        assert "error_rate" in state
        assert state["latency"] == 1200
        assert state["error_rate"] == 0.05

    def test_hash_state_is_deterministic(self, optimization_engine):
        """Testa que hash de estado é determinístico."""
        state = {"latency": 1000, "error_rate": 0.05}

        hash1 = optimization_engine._hash_state(state)
        hash2 = optimization_engine._hash_state(state)

        assert hash1 == hash2

    def test_hash_state_differs_for_different_states(self, optimization_engine):
        """Testa que estados diferentes geram hashes diferentes."""
        state1 = {"latency": 1000, "error_rate": 0.05}
        state2 = {"latency": 1500, "error_rate": 0.08}

        hash1 = optimization_engine._hash_state(state1)
        hash2 = optimization_engine._hash_state(state2)

        assert hash1 != hash2
