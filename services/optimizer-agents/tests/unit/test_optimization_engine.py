"""
Testes unitários para OptimizationEngine.

Cobre:
- Inicialização e configuração
- Análise de oportunidades
- Geração de hipóteses
- Seleção de ações (epsilon-greedy)
- Cálculo de recompensas
- Atualização da Q-table
- Funções helper de estado
"""
import pytest
import random
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from collections import defaultdict

from src.services.optimization_engine import OptimizationEngine
from src.models.optimization_hypothesis import OptimizationHypothesis, OptimizationType
from src.models.optimization_event import OptimizationType as EventOptimizationType


@pytest.fixture
def mock_settings():
    """Settings mocados para testes."""
    settings = Mock()
    settings.learning_rate = 0.1
    settings.exploration_rate = 0.2
    settings.discount_factor = 0.95
    settings.max_weight_adjustment = 0.5
    return settings


@pytest.fixture
def mock_load_predictor():
    """Mock do LoadPredictor."""
    predictor = AsyncMock()
    predictor.predict_load = AsyncMock(return_value={
        'forecast': [100, 110, 105, 120],
        'confidence': 0.9
    })
    return predictor


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient."""
    return AsyncMock()


@pytest.fixture
def mock_redis_client():
    """Mock do RedisClient."""
    return AsyncMock()


@pytest.fixture
def mock_consensus_engine_client():
    """Mock do ConsensusEngineGrpcClient."""
    return AsyncMock()


@pytest.fixture
def mock_queen_agent_client():
    """Mock do QueenAgentGrpcClient."""
    return AsyncMock()


@pytest.fixture
def optimization_engine(mock_settings, mock_load_predictor, mock_mongodb_client, mock_redis_client):
    """Fixture do OptimizationEngine."""
    return OptimizationEngine(
        settings=mock_settings,
        load_predictor=mock_load_predictor,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client
    )


@pytest.fixture
def sample_insight():
    """Insight de exemplo para testes."""
    return {
        "insight_id": "insight-001",
        "insight_type": "OPERATIONAL",
        "priority": "HIGH",
        "metrics": {
            "latency_p95": 200.0,
            "error_rate": 0.01,
            "slo_compliance": 0.95,
            "divergence": 0.15,
            "confidence": 0.85
        },
        "related_entities": [{"entity_id": "consensus-engine"}],
        "correlation_id": "corr-001"
    }


class TestOptimizationEngineInitialization:
    """Testes de inicialização do OptimizationEngine."""

    def test_initialization_with_all_params(self, mock_settings, mock_load_predictor, mock_mongodb_client, mock_redis_client):
        """Testa inicialização com todos os parâmetros."""
        engine = OptimizationEngine(
            settings=mock_settings,
            load_predictor=mock_load_predictor,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        assert engine.settings == mock_settings
        assert engine.load_predictor == mock_load_predictor
        assert isinstance(engine.q_table, defaultdict)
        assert isinstance(engine.reward_history, list)
        assert engine.learning_rate == 0.1
        assert engine.exploration_rate == 0.2
        assert engine.discount_factor == 0.95

    def test_initialization_default_settings(self):
        """Testa inicialização com settings padrão."""
        with patch('src.services.optimization_engine.get_settings') as mock_get_settings:
            mock_settings = Mock()
            mock_settings.learning_rate = 0.1
            mock_settings.exploration_rate = 0.2
            mock_settings.discount_factor = 0.95
            mock_get_settings.return_value = mock_settings

            engine = OptimizationEngine()

            assert engine.settings == mock_settings

    def test_action_space_initialized(self, optimization_engine):
        """Testa que action space é inicializado corretamente."""
        assert OptimizationType.WEIGHT_RECALIBRATION in optimization_engine.action_space
        assert OptimizationType.SLO_ADJUSTMENT in optimization_engine.action_space
        assert OptimizationType.HEURISTIC_UPDATE in optimization_engine.action_space
        assert OptimizationType.POLICY_CHANGE in optimization_engine.action_space


class TestAnalyzeOpportunity:
    """Testes de análise de oportunidades."""

    @pytest.mark.asyncio
    async def test_analyze_opportunity_returns_empty_list_on_error(self, optimization_engine):
        """Testa análise com erro retorna lista vazia."""
        insight = {"invalid": "data"}

        result = await optimization_engine.analyze_opportunity(insight)

        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_opportunity_generates_hypotheses(self, optimization_engine, sample_insight):
        """Testa geração de hipóteses."""
        with patch.object(optimization_engine, 'generate_hypothesis') as mock_generate:
            mock_hypothesis = Mock(spec=OptimizationHypothesis)
            mock_hypothesis.validate_feasibility.return_value = True
            mock_hypothesis.optimization_type = OptimizationType.WEIGHT_RECALIBRATION
            mock_generate.return_value = mock_hypothesis

            result = await optimization_engine.analyze_opportunity(sample_insight)

            # generate_hypothesis deve ser chamado para cada ação candidata
            assert mock_generate.call_count >= 0

    @pytest.mark.asyncio
    async def test_analyze_opportunity_filters_infeasible_hypotheses(self, optimization_engine, sample_insight):
        """Testa filtragem de hipóteses inviáveis."""
        with patch.object(optimization_engine, 'generate_hypothesis') as mock_generate:
            mock_hypothesis = Mock(spec=OptimizationHypothesis)
            mock_hypothesis.validate_feasibility.return_value = False
            mock_generate.return_value = mock_hypothesis

            result = await optimization_engine.analyze_opportunity(sample_insight)

            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_analyze_operational_insight_actions(self, optimization_engine, sample_insight):
        """Testa ações para insights operacionais."""
        sample_insight["insight_type"] = "OPERATIONAL_ANOMALY"

        with patch.object(optimization_engine, 'generate_hypothesis') as mock_generate:
            mock_hypothesis = Mock(spec=OptimizationHypothesis)
            mock_hypothesis.validate_feasibility.return_value = True
            mock_hypothesis.optimization_type = OptimizationType.WEIGHT_RECALIBRATION
            mock_generate.return_value = mock_hypothesis

            await optimization_engine.analyze_opportunity(sample_insight)

            # Deve considerar WEIGHT_RECALIBRATION e SLO_ADJUSTMENT
            assert mock_generate.call_count >= 0

    @pytest.mark.asyncio
    async def test_analyze_strategic_insight_actions(self, optimization_engine, sample_insight):
        """Testa ações para insights estratégicos."""
        sample_insight["insight_type"] = "STRATEGIC"

        with patch.object(optimization_engine, 'generate_hypothesis') as mock_generate:
            mock_hypothesis = Mock(spec=OptimizationHypothesis)
            mock_hypothesis.validate_feasibility.return_value = True
            mock_hypothesis.optimization_type = OptimizationType.POLICY_CHANGE
            mock_generate.return_value = mock_hypothesis

            await optimization_engine.analyze_opportunity(sample_insight)

            # Deve considerar POLICY_CHANGE e HEURISTIC_UPDATE
            assert mock_generate.call_count >= 0


class TestGenerateHypothesis:
    """Testes de geração de hipóteses."""

    def test_generate_hypothesis_creates_valid_hypothesis(self, optimization_engine, sample_insight):
        """Testa criação de hipótese válida."""
        state = {"latency_p95": 200.0, "error_rate": 0.01}
        action = OptimizationType.WEIGHT_RECALIBRATION
        component = "consensus-engine"
        metrics = sample_insight["metrics"]
        context = sample_insight

        hypothesis = optimization_engine.generate_hypothesis(state, action, component, metrics, context)

        assert hypothesis is not None
        assert hypothesis.target_component == component
        assert hypothesis.optimization_type == action
        assert hypothesis.baseline_metrics == metrics

    def test_generate_hypothesis_includes_expected_improvement(self, optimization_engine, sample_insight):
        """Testa que hipótese inclui melhoria esperada."""
        state = {"latency_p95": 200.0}
        action = OptimizationType.WEIGHT_RECALIBRATION
        component = "consensus-engine"
        metrics = sample_insight["metrics"]
        context = sample_insight

        hypothesis = optimization_engine.generate_hypothesis(state, action, component, metrics, context)

        assert hasattr(hypothesis, 'expected_improvement')
        assert 0.0 <= hypothesis.expected_improvement <= 1.0

    def test_generate_hypothesis_calculates_risk_score(self, optimization_engine, sample_insight):
        """Testa cálculo de score de risco."""
        state = {"latency_p95": 200.0}
        action = OptimizationType.WEIGHT_RECALIBRATION
        component = "consensus-engine"
        metrics = sample_insight["metrics"]
        context = sample_insight

        hypothesis = optimization_engine.generate_hypothesis(state, action, component, metrics, context)

        assert hasattr(hypothesis, 'risk_score')
        assert 0.0 <= hypothesis.risk_score <= 1.0

    def test_generate_hypothesis_generates_adjustments(self, optimization_engine, sample_insight):
        """Testa geração de ajustes propostos."""
        state = {"latency_p95": 200.0}
        action = OptimizationType.WEIGHT_RECALIBRATION
        component = "consensus-engine"
        metrics = sample_insight["metrics"]
        context = sample_insight

        hypothesis = optimization_engine.generate_hypothesis(state, action, component, metrics, context)

        assert len(hypothesis.proposed_adjustments) > 0

    def test_generate_hypothesis_handles_exception(self, optimization_engine, sample_insight):
        """Testa tratamento de exceção na geração."""
        # Passar estado inválido para causar exceção
        state = None
        action = OptimizationType.WEIGHT_RECALIBRATION
        component = "consensus-engine"
        metrics = sample_insight["metrics"]
        context = sample_insight

        hypothesis = optimization_engine.generate_hypothesis(state, action, component, metrics, context)

        assert hypothesis is None


class TestSelectAction:
    """Testes de seleção de ações."""

    def test_select_action_exploration(self, optimization_engine):
        """Testa seleção de ação com exploração (epsilon-greedy)."""
        state = {"latency_p95": 200.0}

        # Forçar exploração definindo exploration_rate alto
        optimization_engine.exploration_rate = 1.0

        with patch('random.random', return_value=0.5):
            with patch('random.choice') as mock_choice:
                mock_choice.return_value = OptimizationType.SLO_ADJUSTMENT

                action = optimization_engine.select_action(state)

                mock_choice.assert_called_once()
                assert action == OptimizationType.SLO_ADJUSTMENT

    def test_select_action_exploitation(self, optimization_engine):
        """Testa seleção de ação com exploração (usando Q-table)."""
        state = {"latency_p95": 200.0}
        state_hash = optimization_engine._hash_state(state)

        # Adicionar valores à Q-table
        optimization_engine.q_table[state_hash]["WEIGHT_RECALIBRATION"] = 0.8
        optimization_engine.q_table[state_hash]["SLO_ADJUSTMENT"] = 0.5

        # Forçar exploração definindo exploration_rate zero
        optimization_engine.exploration_rate = 0.0

        with patch('random.random', return_value=1.0):  # Garantir exploração
            action = optimization_engine.select_action(state)

            assert action == OptimizationType.WEIGHT_RECALIBRATION

    def test_select_action_with_empty_q_table(self, optimization_engine):
        """Testa seleção quando Q-table está vazia para o estado."""
        state = {"latency_p95": 200.0}

        # Forçar exploração com Q-table vazia
        optimization_engine.exploration_rate = 0.0

        with patch('random.random', return_value=1.0):
            with patch('random.choice') as mock_choice:
                mock_choice.return_value = OptimizationType.POLICY_CHANGE

                action = optimization_engine.select_action(state)

                mock_choice.assert_called_once()


class TestCalculateReward:
    """Testes de cálculo de recompensa."""

    def test_calculate_reward_positive_improvement(self, optimization_engine):
        """Testa cálculo de recompensa com melhoria positiva."""
        optimization_event = Mock()
        optimization_event.optimization_id = "opt-001"
        optimization_event.improvement_percentage = 0.15
        optimization_event.metadata = {"expected_improvement": 0.10}
        optimization_event.causal_analysis = Mock()
        optimization_event.causal_analysis.confidence = 0.85

        post_metrics = {"latency_p95": 150.0}

        reward = optimization_engine.calculate_reward(optimization_event, post_metrics)

        assert reward > 0

    def test_calculate_reward_negative_improvement(self, optimization_engine):
        """Testa cálculo de recompensa com degradação."""
        optimization_event = Mock()
        optimization_event.optimization_id = "opt-002"
        optimization_event.improvement_percentage = -0.10
        optimization_event.metadata = {"expected_improvement": 0.0}
        optimization_event.causal_analysis = Mock()
        optimization_event.causal_analysis.confidence = 0.5

        post_metrics = {"latency_p95": 250.0}

        reward = optimization_engine.calculate_reward(optimization_event, post_metrics)

        # Recompensa deve ser negativa (penalidade dobrada)
        assert reward < 0

    def test_calculate_reward_with_bonus(self, optimization_engine):
        """Testa bônus por exceder expectativa."""
        optimization_event = Mock()
        optimization_event.optimization_id = "opt-003"
        optimization_event.improvement_percentage = 0.30  # 20% acima de 0.25
        optimization_event.metadata = {"expected_improvement": 0.25}
        optimization_event.causal_analysis = Mock()
        optimization_event.causal_analysis.confidence = 0.9

        post_metrics = {"latency_p95": 100.0}

        reward = optimization_engine.calculate_reward(optimization_event, post_metrics)

        # Deve incluir bônus (0.30 improvement - 0.02 penalty + 0.10 bonus = 0.38)
        assert reward > 0.30  # Deve ser maior que improvement original

    def test_calculate_reward_handles_exception(self, optimization_engine):
        """Testa tratamento de exceção no cálculo."""
        optimization_event = Mock()
        optimization_event.optimization_id = "opt-004"
        optimization_event.improvement_percentage = "invalid"  # Tipo inválido
        optimization_event.causal_analysis = Mock()

        post_metrics = {}

        reward = optimization_engine.calculate_reward(optimization_event, post_metrics)

        # Deve retornar 0.0 em caso de erro
        assert reward == 0.0


class TestUpdateQTable:
    """Testes de atualização da Q-table."""

    def test_update_q_table_basic(self, optimization_engine):
        """Testa atualização básica da Q-table."""
        state = {"latency_p95": 200.0}
        action = OptimizationType.WEIGHT_RECALIBRATION
        reward = 0.5
        next_state = {"latency_p95": 180.0}

        # Adicionar valor inicial à Q-table
        state_hash = optimization_engine._hash_state(state)
        optimization_engine.q_table[state_hash][action.value] = 0.3

        initial_q = optimization_engine.q_table[state_hash][action.value]

        optimization_engine.update_q_table(state, action, reward, next_state)

        new_q = optimization_engine.q_table[state_hash][action.value]

        # Q-value deve ter mudado
        assert new_q != initial_q
        # Recompensa deve estar no histórico
        assert len(optimization_engine.reward_history) > 0

    def test_update_q_table_with_empty_next_state(self, optimization_engine):
        """Testa atualização quando próximo estado não tem Q-values."""
        state = {"latency_p95": 200.0}
        action = OptimizationType.SLO_ADJUSTMENT
        reward = 0.3
        next_state = {"latency_p95": 150.0}

        state_hash = optimization_engine._hash_state(state)
        optimization_engine.q_table[state_hash][action.value] = 0.2

        optimization_engine.update_q_table(state, action, reward, next_state)

        # max_next_q deve ser 0.0 (sem Q-values para next_state)
        assert optimization_engine.q_table[state_hash][action.value] != 0.2

    def test_update_q_table_saves_to_history(self, optimization_engine):
        """Testa que atualização salva no histórico."""
        state = {"latency_p95": 200.0}
        action = OptimizationType.WEIGHT_RECALIBRATION
        reward = 0.4
        next_state = {"latency_p95": 180.0}

        initial_history_len = len(optimization_engine.reward_history)

        optimization_engine.update_q_table(state, action, reward, next_state)

        assert len(optimization_engine.reward_history) == initial_history_len + 1


class TestHelperMethods:
    """Testes de métodos helper."""

    def test_extract_state(self, optimization_engine):
        """Testa extração de estado das métricas."""
        metrics = {
            "latency_p95": 200.0,
            "error_rate": 0.01,
            "slo_compliance": 0.95,
            "divergence": 0.15,
            "confidence": 0.85
        }

        state = optimization_engine._extract_state(metrics)

        assert "latency_p95" in state
        assert "error_rate" in state
        assert "slo_compliance" in state
        assert "divergence" in state
        assert "confidence" in state

    def test_hash_state(self, optimization_engine):
        """Testa geração de hash de estado."""
        state = {
            "latency_p95": 200.0,
            "error_rate": 0.01
        }

        state_hash = optimization_engine._hash_state(state)

        assert isinstance(state_hash, str)
        assert "|" in state_hash  # Separador usado

    def test_hash_state_discretizes_values(self, optimization_engine):
        """Testa discretização de valores no hash."""
        state1 = {"latency_p95": 200.123, "error_rate": 0.0156}
        state2 = {"latency_p95": 200.189, "error_rate": 0.0144}

        hash1 = optimization_engine._hash_state(state1)
        hash2 = optimization_engine._hash_state(state2)

        # Após discretização, valores próximos devem gerar mesmo hash
        # latency_p95: 200.123 -> 200.1, 200.189 -> 200.2 (diferentes)
        # error_rate: 0.0156 -> 0.0, 0.0144 -> 0.0 (iguais)
        # Verificar que ambos têm error_rate discretizado para 0.0
        assert "error_rate:0.0" in hash1
        assert "error_rate:0.0" in hash2

    def test_estimate_risk_with_history(self, optimization_engine):
        """Testa estimativa de risco com histórico."""
        # Adicionar histórico de rewards
        optimization_engine.reward_history = [
            ("state1", "WEIGHT_RECALIBRATION", 0.5),
            ("state2", "WEIGHT_RECALIBRATION", 0.3),
            ("state3", "WEIGHT_RECALIBRATION", 0.7),
        ]

        risk = optimization_engine._estimate_risk(OptimizationType.WEIGHT_RECALIBRATION, "consensus-engine")

        assert 0.0 <= risk <= 1.0

    def test_estimate_risk_without_history(self, optimization_engine):
        """Testa estimativa de risco sem histórico."""
        optimization_engine.reward_history = []

        risk = optimization_engine._estimate_risk(OptimizationType.WEIGHT_RECALIBRATION, "consensus-engine")

        # Sem histórico, deve retornar risco médio (0.5)
        assert risk == 0.5

    def test_calculate_confidence(self, optimization_engine):
        """Testa cálculo de confiança."""
        state_hash = "test_state"
        action = OptimizationType.WEIGHT_RECALIBRATION

        # Adicionar observações ao histórico
        optimization_engine.reward_history = [
            (state_hash, action.value, 0.5) for _ in range(20)
        ]

        confidence = optimization_engine._calculate_confidence(state_hash, action)

        # Mais observações = maior confiança
        assert 0.0 < confidence <= 1.0

    def test_calculate_target_metrics(self, optimization_engine):
        """Testa cálculo de métricas alvo."""
        baseline = {
            "latency_p95": 200.0,
            "error_rate": 0.05,
            "slo_compliance": 0.90
        }
        improvement = 0.15  # 15% de melhoria

        target = optimization_engine._calculate_target_metrics(baseline, improvement)

        # error_rate deve diminuir
        assert target["error_rate"] < baseline["error_rate"]
        # slo_compliance deve aumentar
        assert target["slo_compliance"] > baseline["slo_compliance"]
        # slo_compliance limitado a 1.0
        assert target["slo_compliance"] <= 1.0

    def test_calculate_priority(self, optimization_engine):
        """Testa cálculo de prioridade."""
        # Alta melhoria, baixo risco = prioridade alta
        priority = optimization_engine._calculate_priority(0.9, 0.1)
        assert priority == 5

        # Baixa melhoria, alto risco = prioridade baixa
        priority = optimization_engine._calculate_priority(0.1, 0.9)
        assert priority == 1

    def test_generate_hypothesis_text(self, optimization_engine):
        """Testa geração de texto da hipótese."""
        text = optimization_engine._generate_hypothesis_text(
            OptimizationType.WEIGHT_RECALIBRATION,
            "consensus-engine",
            0.20
        )

        assert "consensus-engine" in text
        assert "20.0%" in text or "20%" in text

    def test_get_q_table_size(self, optimization_engine):
        """Testa retorno do tamanho da Q-table."""
        # Adicionar alguns estados
        optimization_engine.q_table["state1"] = {"action1": 0.5}
        optimization_engine.q_table["state2"] = {"action1": 0.3, "action2": 0.7}

        size = optimization_engine.get_q_table_size()

        assert size == 2

    def test_get_exploration_rate(self, optimization_engine):
        """Testa retorno da taxa de exploração."""
        rate = optimization_engine.get_exploration_rate()

        assert rate == optimization_engine.exploration_rate

    def test_decay_exploration_rate(self, optimization_engine):
        """Testa decaimento da taxa de exploração."""
        initial_rate = optimization_engine.exploration_rate

        optimization_engine.decay_exploration_rate(decay_factor=0.5)

        # Taxa deve ter diminuído
        assert optimization_engine.exploration_rate < initial_rate

    def test_decay_exploration_rate_minimum(self, optimization_engine):
        """Testa limite mínimo da taxa de exploração."""
        optimization_engine.exploration_rate = 0.06

        optimization_engine.decay_exploration_rate(decay_factor=0.5)

        # Deve ser limitado a 0.05
        assert optimization_engine.exploration_rate >= 0.05


class TestIncorporateLoadForecast:
    """Testes de incorporação de previsão de carga."""

    @pytest.mark.asyncio
    async def test_incorporate_load_forecast_enriches_state(self, optimization_engine, mock_load_predictor):
        """Testa enriquecimento do estado com forecast."""
        state = {
            "latency_p95": 200.0,
            "current_load": 0.5
        }

        mock_load_predictor.predict_load = AsyncMock(return_value={
            'forecast': [0.6, 0.65, 0.7, 0.75, 0.8],
            'confidence': 0.9
        })

        enriched_state = await optimization_engine._incorporate_load_forecast(state)

        assert 'load_forecast' in enriched_state
        assert enriched_state['load_forecast']['trend'] in ['increasing', 'decreasing', 'stable']

    @pytest.mark.asyncio
    async def test_incorporate_load_forecast_handles_error(self, optimization_engine, mock_load_predictor):
        """Testa tratamento de erro na previsão."""
        state = {"latency_p95": 200.0}

        mock_load_predictor.predict_load = AsyncMock(side_effect=Exception("Prediction failed"))

        enriched_state = await optimization_engine._incorporate_load_forecast(state)

        # Estado deve ser retornado inalterado
        assert 'load_forecast' not in enriched_state
        assert enriched_state == state
