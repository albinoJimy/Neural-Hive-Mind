"""
Testes unitários para SchedulingOptimizer.

Testa Q-learning, epsilon-greedy, geração de hipóteses, atualização de política,
e persistência de Q-table.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import numpy as np

from src.ml.scheduling_optimizer import SchedulingOptimizer, SchedulingAction


# Fixtures

@pytest.fixture
def mock_config():
    """Mock de configuração."""
    return {
        'ml_scheduling_epsilon': 0.1,
        'ml_scheduling_learning_rate': 0.01,
        'ml_scheduling_discount_factor': 0.95,
    }


@pytest.fixture
def mock_optimization_engine():
    """Mock de OptimizationEngine."""
    return Mock()


@pytest.fixture
def mock_experiment_manager():
    """Mock de ExperimentManager."""
    manager = AsyncMock()
    manager.run_experiment = AsyncMock(return_value={'success': True, 'metrics': {}})
    return manager


@pytest.fixture
def mock_orchestrator_client():
    """Mock de OrchestratorClient."""
    return AsyncMock()


@pytest.fixture
def mock_mongodb():
    """Mock de MongoDB client."""
    client = AsyncMock()
    client.db = {'scheduling_policies': AsyncMock()}
    client.db['scheduling_policies'].update_one = AsyncMock()
    return client


@pytest.fixture
def mock_redis():
    """Mock de Redis client."""
    return AsyncMock()


@pytest.fixture
def mock_model_registry():
    """Mock de ModelRegistry."""
    registry = AsyncMock()
    registry.load_scheduling_policy = AsyncMock(return_value=None)
    registry.save_scheduling_policy = AsyncMock()
    return registry


@pytest.fixture
def mock_metrics():
    """Mock de métricas."""
    metrics = Mock()
    metrics.record_scheduling_optimization = Mock()
    metrics.record_policy_update = Mock()
    return metrics


@pytest.fixture
def sample_state():
    """Estado de exemplo."""
    return {
        'current_load': 100,
        'worker_utilization': 0.75,
        'queue_depth': 25,
        'sla_compliance': 0.92
    }


@pytest.fixture
def sample_load_forecast():
    """Previsão de carga de exemplo."""
    return {
        'forecast': [
            {
                'timestamp': datetime.utcnow().isoformat(),
                'ticket_count': 120 + i,
                'resource_demand': {'cpu_cores': 12, 'memory_mb': 12000}
            }
            for i in range(60)
        ],
        'metadata': {}
    }


# Tests - Inicialização

@pytest.mark.asyncio
class TestSchedulingOptimizerInitialization:
    """Testes de inicialização."""

    async def test_initialize_without_policy(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa inicialização sem política pré-existente."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        await optimizer.initialize()

        assert optimizer._initialized
        assert len(optimizer.q_table) == 0  # Q-table vazia

    async def test_initialize_with_existing_policy(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa inicialização carregando política do MLflow."""
        # Mock Q-table existente
        existing_q_table = {
            'high_medium_low_good_stable': {
                SchedulingAction.NO_ACTION: 0.5,
                SchedulingAction.INCREASE_WORKER_POOL: 0.2
            }
        }
        mock_model_registry.load_scheduling_policy = AsyncMock(return_value={
            'q_table': existing_q_table
        })

        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        await optimizer.initialize()

        assert optimizer._initialized
        assert len(optimizer.q_table) > 0
        assert optimizer.q_table == existing_q_table


# Tests - Otimização de Scheduling

@pytest.mark.asyncio
class TestSchedulingOptimization:
    """Testes de geração de recomendações."""

    async def test_optimize_scheduling_basic(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state
    ):
        """Testa geração de recomendação básica."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        optimizer._initialized = True

        result = await optimizer.optimize_scheduling(sample_state)

        assert 'action' in result
        assert 'justification' in result
        assert 'expected_improvement' in result
        assert 'risk_score' in result
        assert 'confidence' in result
        assert result['action'] in [a.value for a in SchedulingAction]
        assert 0 <= result['risk_score'] <= 1
        assert 0 <= result['confidence'] <= 1

    async def test_optimize_scheduling_with_forecast(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state,
        sample_load_forecast
    ):
        """Testa recomendação enriquecida com forecast."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        optimizer._initialized = True

        result = await optimizer.optimize_scheduling(sample_state, sample_load_forecast)

        assert 'action' in result
        # Forecast indica tendência crescente, deve recomendar scaling
        assert result['action'] in [
            SchedulingAction.PREEMPTIVE_SCALING.value,
            SchedulingAction.INCREASE_WORKER_POOL.value,
            SchedulingAction.NO_ACTION.value  # Possível se estado atual é bom
        ]

    async def test_optimize_scheduling_high_load(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa recomendação com carga alta."""
        high_load_state = {
            'current_load': 250,  # Critical
            'worker_utilization': 0.95,
            'queue_depth': 150,
            'sla_compliance': 0.75
        }

        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        optimizer._initialized = True

        result = await optimizer.optimize_scheduling(high_load_state)

        # Deve recomendar aumento de workers ou scaling preemptivo
        assert result['action'] in [
            SchedulingAction.INCREASE_WORKER_POOL.value,
            SchedulingAction.PREEMPTIVE_SCALING.value,
            SchedulingAction.LOAD_BALANCING_RECONFIG.value
        ]
        assert result['risk_score'] > 0.3  # Alta carga = mais risco


# Tests - Seleção de Ação (Epsilon-Greedy)

class TestActionSelection:
    """Testes de seleção de ação."""

    def test_select_action_exploitation(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa exploração (escolha gulosa)."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Q-table com valores conhecidos
        state_hash = "test_state"
        optimizer.q_table[state_hash] = {
            SchedulingAction.NO_ACTION: 0.1,
            SchedulingAction.INCREASE_WORKER_POOL: 0.8,  # Maior Q-value
            SchedulingAction.DECREASE_WORKER_POOL: -0.2
        }

        # Forçar exploitation (sem random)
        with patch('numpy.random.random', return_value=0.2):  # > epsilon (0.1)
            action = optimizer._select_action(state_hash)

        assert action == SchedulingAction.INCREASE_WORKER_POOL

    def test_select_action_exploration(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa exploração (escolha aleatória)."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        state_hash = "test_state"

        # Forçar exploration
        with patch('numpy.random.random', return_value=0.05):  # < epsilon (0.1)
            action = optimizer._select_action(state_hash)

        # Ação deve ser uma das válidas
        assert action in list(SchedulingAction)

    def test_select_action_unseen_state(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa ação para estado nunca visto."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Estado não presente na Q-table
        state_hash = "unseen_state"

        # Forçar exploitation
        with patch('numpy.random.random', return_value=0.2):
            action = optimizer._select_action(state_hash)

        # Deve retornar NO_ACTION para estados novos
        assert action == SchedulingAction.NO_ACTION


# Tests - Atualização de Política (Q-learning)

@pytest.mark.asyncio
class TestPolicyUpdate:
    """Testes de atualização da Q-table."""

    async def test_update_policy_basic(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state
    ):
        """Testa atualização básica de Q-value."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        optimizer._initialized = True

        # Simular estado e ação anteriores
        optimizer.recent_states = [sample_state]
        optimizer.recent_actions = [SchedulingAction.INCREASE_WORKER_POOL]

        # Atualizar com recompensa positiva
        next_state = {**sample_state, 'sla_compliance': 0.98}
        await optimizer.update_policy(reward=0.5, next_state=next_state)

        # Q-table deve ter sido atualizada
        state_hash = optimizer._hash_state(sample_state)
        assert state_hash in optimizer.q_table
        assert SchedulingAction.INCREASE_WORKER_POOL in optimizer.q_table[state_hash]
        assert optimizer.q_table[state_hash][SchedulingAction.INCREASE_WORKER_POOL] > 0

    async def test_update_policy_negative_reward(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state
    ):
        """Testa atualização com recompensa negativa."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        optimizer._initialized = True

        optimizer.recent_states = [sample_state]
        optimizer.recent_actions = [SchedulingAction.DECREASE_WORKER_POOL]

        # Atualizar com recompensa negativa
        next_state = {**sample_state, 'sla_compliance': 0.70}  # SLA piorou
        await optimizer.update_policy(reward=-0.3, next_state=next_state)

        # Q-value deve ter diminuído
        state_hash = optimizer._hash_state(sample_state)
        assert optimizer.q_table[state_hash][SchedulingAction.DECREASE_WORKER_POOL] < 0

    async def test_update_policy_snapshot_triggered(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state
    ):
        """Testa snapshot automático após N updates."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )
        optimizer._initialized = True
        optimizer.snapshot_interval = 10

        optimizer.recent_states = [sample_state]
        optimizer.recent_actions = [SchedulingAction.NO_ACTION]

        # Atualizar 10 vezes
        for i in range(10):
            await optimizer.update_policy(reward=0.1, next_state=sample_state)

        # Snapshot deve ter sido chamado
        assert optimizer.update_counter == 10
        mock_model_registry.save_scheduling_policy.assert_called()


# Tests - Geração de Hipóteses

@pytest.mark.asyncio
class TestHypothesisGeneration:
    """Testes de geração de hipóteses para A/B testing."""

    async def test_generate_scheduling_hypothesis(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state
    ):
        """Testa geração de hipótese."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        hypothesis = await optimizer.generate_scheduling_hypothesis(
            sample_state,
            SchedulingAction.INCREASE_WORKER_POOL
        )

        assert 'optimization_type' in hypothesis
        assert hypothesis['optimization_type'] == 'scheduling'
        assert 'action' in hypothesis
        assert hypothesis['action'] == SchedulingAction.INCREASE_WORKER_POOL.value
        assert 'predicted_metrics' in hypothesis
        assert 'implementation_details' in hypothesis
        assert 'rollback_criteria' in hypothesis


# Tests - Helpers

class TestHelpers:
    """Testes de métodos auxiliares."""

    def test_hash_state_discretization(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa discretização de estado."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        state1 = {'current_load': 30, 'worker_utilization': 0.4, 'queue_depth': 5, 'sla_compliance': 0.99}
        state2 = {'current_load': 45, 'worker_utilization': 0.45, 'queue_depth': 8, 'sla_compliance': 0.97}

        hash1 = optimizer._hash_state(state1)
        hash2 = optimizer._hash_state(state2)

        # Estados similares devem ter mesmo hash (bins)
        assert hash1 == hash2  # Ambos low_low_low_good_stable

    def test_enrich_state_with_forecast(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state,
        sample_load_forecast
    ):
        """Testa enriquecimento de estado com forecast."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        enriched = optimizer._enrich_state_with_forecast(sample_state, sample_load_forecast)

        assert 'load_trend' in enriched
        assert enriched['load_trend'] in ['increasing', 'decreasing', 'stable']
        assert 'predicted_peak' in enriched

    def test_calculate_scheduling_reward(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa cálculo de recompensa."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        metrics_before = {
            'sla_compliance': 0.90,
            'throughput': 100,
            'utilization': 0.75
        }
        metrics_after = {
            'sla_compliance': 0.95,
            'throughput': 120,
            'utilization': 0.70
        }

        reward = optimizer._calculate_scheduling_reward(metrics_before, metrics_after)

        # Recompensa deve ser positiva (melhorou SLA, throughput e eficiência)
        assert reward > 0
        assert -1.0 <= reward <= 1.0  # Normalizada

    def test_calculate_action_risk(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics,
        sample_state
    ):
        """Testa cálculo de risco."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        risk_increase = optimizer._calculate_action_risk(sample_state, SchedulingAction.INCREASE_WORKER_POOL)
        risk_decrease = optimizer._calculate_action_risk(sample_state, SchedulingAction.DECREASE_WORKER_POOL)
        risk_no_action = optimizer._calculate_action_risk(sample_state, SchedulingAction.NO_ACTION)

        # Decrease deve ser mais arriscado que increase
        assert risk_decrease > risk_increase
        # NO_ACTION deve ter risco zero
        assert risk_no_action == 0.0

    def test_calculate_confidence(
        self,
        mock_config,
        mock_optimization_engine,
        mock_experiment_manager,
        mock_orchestrator_client,
        mock_mongodb,
        mock_redis,
        mock_model_registry,
        mock_metrics
    ):
        """Testa cálculo de confiança."""
        optimizer = SchedulingOptimizer(
            mock_optimization_engine,
            mock_experiment_manager,
            mock_orchestrator_client,
            mock_mongodb,
            mock_redis,
            mock_model_registry,
            mock_metrics,
            mock_config
        )

        # Estado nunca visto
        confidence_new = optimizer._calculate_confidence("never_seen_state")
        assert confidence_new == 0.1  # Baixa confiança

        # Estado visto muitas vezes
        state_hash = "well_known_state"
        optimizer.q_table[state_hash] = {
            SchedulingAction.NO_ACTION: 2.0,
            SchedulingAction.INCREASE_WORKER_POOL: 3.5
        }
        confidence_known = optimizer._calculate_confidence(state_hash)
        assert confidence_known > confidence_new


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
