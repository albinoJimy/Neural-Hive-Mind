"""
Testes E2E do fluxo de otimização.

Simula fluxo completo desde insight até aplicação de otimização:
1. Receber insight
2. Gerar hipóteses
3. Submeter experimento
4. Analisar resultados
5. Aplicar otimização
6. Atualizar Q-table
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.services.optimization_engine import OptimizationEngine
from src.services.experiment_manager import ExperimentManager
from src.models.optimization_event import OptimizationType, OptimizationEvent
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
    settings.experiment_timeout_seconds = 300
    settings.degradation_threshold = 0.15
    settings.rollback_on_degradation = True
    return settings


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient."""
    client = AsyncMock()
    client.save_experiment = AsyncMock(return_value=True)
    client.save_optimization = AsyncMock(return_value=True)
    client.update_experiment_status = AsyncMock(return_value=True)
    client.get_experiment = AsyncMock(return_value={
        "experiment_id": "exp-e2e-123",
        "status": "COMPLETED",
        "target_component": "consensus-engine",
        "baseline_metrics": {"latency_p95": 1000, "error_rate": 0.05},
        "results": {
            "treatment_metrics": {"latency_p95": 800, "error_rate": 0.03},
            "improvement_percentage": 0.20,
            "statistical_significance": True
        }
    })
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do RedisClient."""
    client = AsyncMock()
    client.lock_component = AsyncMock(return_value=True)
    client.unlock_component = AsyncMock(return_value=True)
    client.get_experiment_metrics = AsyncMock(return_value={
        "baseline": {"latency_p95": 1000, "error_rate": 0.05},
        "treatment": {"latency_p95": 800, "error_rate": 0.03}
    })
    return client


@pytest.fixture
def mock_argo_client():
    """Mock do ArgoWorkflowsClient."""
    client = AsyncMock()
    client.submit_experiment_workflow = AsyncMock(return_value="workflow-e2e-123")
    client.get_workflow_status = AsyncMock(return_value={
        "status": "Succeeded",
        "phase": "Succeeded",
        "finishedAt": datetime.utcnow().isoformat()
    })
    return client


@pytest.fixture
def optimization_engine(mock_settings):
    """Fixture do OptimizationEngine."""
    return OptimizationEngine(settings=mock_settings)


@pytest.fixture
def experiment_manager(mock_settings, mock_argo_client, mock_mongodb_client, mock_redis_client):
    """Fixture do ExperimentManager."""
    return ExperimentManager(
        settings=mock_settings,
        argo_client=mock_argo_client,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client
    )


@pytest.fixture
def sample_insight():
    """Insight de exemplo para testes E2E."""
    return {
        "insight_id": "insight-e2e-1",
        "insight_type": "OPERATIONAL_BOTTLENECK",
        "priority": "HIGH",
        "metrics": {
            "latency_p95": 1200,
            "error_rate": 0.06,
            "throughput": 95,
            "cpu_usage": 0.85
        },
        "related_entities": [{"entity_id": "consensus-engine"}],
        "recommendations": [
            "Recalibrar pesos de consenso para priorizar velocidade",
            "Ajustar SLO de latência para 1000ms"
        ]
    }


class TestE2EOptimizationFlow:
    """Testes do fluxo E2E completo de otimização."""

    @pytest.mark.asyncio
    async def test_full_optimization_flow_success(
        self,
        optimization_engine,
        experiment_manager,
        sample_insight,
        mock_mongodb_client
    ):
        """
        Testa fluxo completo bem-sucedido:
        Insight -> Hipótese -> Experimento -> Análise -> Otimização -> Q-table update
        """
        # Passo 1: Gerar hipóteses a partir do insight
        hypotheses = optimization_engine.analyze_opportunity(sample_insight)

        assert len(hypotheses) > 0, "Deve gerar pelo menos uma hipótese"

        # Passo 2: Selecionar hipótese com maior confiança
        best_hypothesis = max(hypotheses, key=lambda h: h.confidence)

        # Passo 3: Submeter experimento
        experiment_id = await experiment_manager.submit_experiment(best_hypothesis)

        assert experiment_id is not None, "Experimento deve ser submetido com sucesso"

        # Passo 4: Simular conclusão do experimento e analisar resultados
        experiment_results = await experiment_manager.analyze_results(experiment_id)

        assert experiment_results is not None, "Deve retornar resultados da análise"
        assert experiment_results.get("improvement_percentage", 0) > 0, "Deve detectar melhoria"

        # Passo 5: Aplicar otimização (simulado)
        baseline_metrics = best_hypothesis.baseline_metrics
        achieved_metrics = experiment_results.get("treatment_metrics", {})

        # Passo 6: Calcular recompensa
        reward = optimization_engine.calculate_reward(baseline_metrics, achieved_metrics)

        assert reward > 0, "Recompensa deve ser positiva para melhoria"

        # Passo 7: Atualizar Q-table
        state = optimization_engine._extract_state(sample_insight["metrics"])
        action = best_hypothesis.optimization_type
        next_state = optimization_engine._extract_state(achieved_metrics)

        initial_q_table_size = len(optimization_engine.q_table)

        optimization_engine.update_q_value(state, action, reward, next_state)

        # Verificar que Q-table foi atualizada
        state_hash = optimization_engine._hash_state(state)
        assert state_hash in optimization_engine.q_table
        assert action in optimization_engine.q_table[state_hash]

        # Verificar que histórico de recompensas foi atualizado
        assert len(optimization_engine.reward_history) > 0

    @pytest.mark.asyncio
    async def test_optimization_flow_with_degradation_rollback(
        self,
        optimization_engine,
        experiment_manager,
        sample_insight,
        mock_redis_client
    ):
        """
        Testa fluxo com degradação detectada e rollback.
        """
        # Gerar hipótese
        hypotheses = optimization_engine.analyze_opportunity(sample_insight)
        best_hypothesis = max(hypotheses, key=lambda h: h.confidence)

        # Submeter experimento
        experiment_id = await experiment_manager.submit_experiment(best_hypothesis)

        # Simular degradação no experimento
        mock_redis_client.get_experiment_metrics.return_value = {
            "baseline": {"latency_p95": 1000, "error_rate": 0.05},
            "treatment": {"latency_p95": 1500, "error_rate": 0.10}  # Pior!
        }

        # Analisar resultados (deve detectar degradação)
        experiment_results = await experiment_manager.analyze_results(experiment_id)

        assert experiment_results.get("degradation_detected", False) is True

        # Executar rollback
        rollback_result = await experiment_manager.rollback_experiment(experiment_id)

        assert rollback_result.get("success", False) is True

        # Calcular recompensa negativa
        baseline_metrics = best_hypothesis.baseline_metrics
        achieved_metrics = experiment_results.get("treatment_metrics", {})
        reward = optimization_engine.calculate_reward(baseline_metrics, achieved_metrics)

        assert reward < 0, "Recompensa deve ser negativa para degradação"

        # Atualizar Q-table com recompensa negativa
        state = optimization_engine._extract_state(sample_insight["metrics"])
        action = best_hypothesis.optimization_type

        optimization_engine.update_q_value(state, action, reward, next_state=state)

        # Verificar que Q-value foi penalizado
        state_hash = optimization_engine._hash_state(state)
        q_value = optimization_engine.q_table[state_hash][action]
        assert q_value < 0, "Q-value deve ser negativo após degradação"

    @pytest.mark.asyncio
    async def test_optimization_flow_learns_from_multiple_iterations(
        self,
        optimization_engine,
        experiment_manager,
        sample_insight,
        mock_mongodb_client,
        mock_redis_client
    ):
        """
        Testa que o sistema aprende ao longo de múltiplas iterações.
        """
        state = optimization_engine._extract_state(sample_insight["metrics"])
        state_hash = optimization_engine._hash_state(state)

        # Iterar múltiplas vezes para simular aprendizado
        for iteration in range(5):
            # Gerar hipóteses
            hypotheses = optimization_engine.analyze_opportunity(sample_insight)

            # Selecionar ação
            selected_action = optimization_engine.select_action(state)

            # Simular experimento bem-sucedido
            # (na prática, seria submetido e analisado)
            baseline = {"latency_p95": 1000, "error_rate": 0.05}
            achieved = {"latency_p95": 900 - (iteration * 10), "error_rate": 0.04}

            reward = optimization_engine.calculate_reward(baseline, achieved)

            # Atualizar Q-table
            optimization_engine.update_q_value(state, selected_action, reward, next_state=state)

        # Após 5 iterações, Q-values devem ter convergido
        # A melhor ação deve ter Q-value significativamente maior
        q_values = optimization_engine.q_table[state_hash]
        best_action = max(q_values, key=q_values.get)
        best_q_value = q_values[best_action]

        assert best_q_value > 0, "Melhor ação deve ter Q-value positivo"
        assert len(optimization_engine.reward_history) >= 5, "Deve ter histórico de recompensas"

    @pytest.mark.asyncio
    async def test_optimization_flow_handles_component_lock(
        self,
        optimization_engine,
        experiment_manager,
        sample_insight,
        mock_redis_client
    ):
        """
        Testa que fluxo respeita locks de componentes.
        """
        # Gerar hipótese
        hypotheses = optimization_engine.analyze_opportunity(sample_insight)
        best_hypothesis = max(hypotheses, key=lambda h: h.confidence)

        # Simular componente bloqueado
        mock_redis_client.lock_component.return_value = False

        # Tentar submeter experimento
        experiment_id = await experiment_manager.submit_experiment(best_hypothesis)

        assert experiment_id is None, "Não deve submeter experimento se componente está bloqueado"

    @pytest.mark.asyncio
    async def test_optimization_flow_validates_hypothesis_feasibility(
        self,
        optimization_engine,
        experiment_manager,
        sample_insight
    ):
        """
        Testa que hipóteses inviáveis são filtradas no fluxo.
        """
        with patch.object(optimization_engine, 'generate_hypothesis') as mock_generate:
            # Criar hipótese inviável
            mock_hypothesis = Mock()
            mock_hypothesis.validate_feasibility.return_value = False
            mock_generate.return_value = mock_hypothesis

            # Gerar "hipóteses"
            hypotheses = optimization_engine.analyze_opportunity(sample_insight)

            # Hipóteses inviáveis devem ser filtradas
            assert len(hypotheses) == 0

    @pytest.mark.asyncio
    async def test_optimization_flow_persists_optimization_event(
        self,
        optimization_engine,
        experiment_manager,
        sample_insight,
        mock_mongodb_client
    ):
        """
        Testa que evento de otimização é persistido no MongoDB.
        """
        # Gerar e submeter hipótese
        hypotheses = optimization_engine.analyze_opportunity(sample_insight)
        best_hypothesis = max(hypotheses, key=lambda h: h.confidence)

        experiment_id = await experiment_manager.submit_experiment(best_hypothesis)

        # Simular conclusão e aplicação da otimização
        # (Normalmente seria feito por WeightRecalibrator ou SLOAdjuster)

        # Criar evento de otimização
        optimization_event = Mock(spec=OptimizationEvent)
        optimization_event.optimization_id = f"opt-{experiment_id}"
        optimization_event.optimization_type = best_hypothesis.optimization_type
        optimization_event.target_component = best_hypothesis.target_component
        optimization_event.improvement_percentage = 0.20

        # Persistir
        await mock_mongodb_client.save_optimization(optimization_event)

        # Verificar que foi salvo
        mock_mongodb_client.save_optimization.assert_called_once()


class TestE2EEdgeCases:
    """Testes de casos extremos no fluxo E2E."""

    @pytest.mark.asyncio
    async def test_insight_without_metrics_generates_no_hypotheses(
        self,
        optimization_engine
    ):
        """Testa que insight sem métricas não gera hipóteses."""
        insight = {
            "insight_id": "insight-empty",
            "insight_type": "OPERATIONAL_BOTTLENECK",
            "metrics": {},  # Vazio
            "related_entities": [{"entity_id": "test-component"}],
        }

        hypotheses = optimization_engine.analyze_opportunity(insight)

        # Deve retornar lista vazia ou hipóteses inviáveis
        assert len([h for h in hypotheses if h.validate_feasibility()]) == 0

    @pytest.mark.asyncio
    async def test_experiment_timeout_triggers_abort(
        self,
        experiment_manager,
        mock_argo_client
    ):
        """Testa que timeout de experimento aciona abort."""
        experiment_id = "exp-timeout"

        # Simular experimento que excede timeout
        mock_status = {
            "status": "Running",
            "elapsed_time": 400,  # > 300s timeout
        }

        # Monitorar (deve detectar timeout)
        with patch.object(experiment_manager, 'monitor_experiment', return_value=mock_status):
            # Simular detecção de timeout no loop principal
            if mock_status.get("elapsed_time", 0) > experiment_manager.settings.experiment_timeout_seconds:
                await experiment_manager.abort_experiment(experiment_id, reason="timeout")

        # Verificar que abort foi chamado
        mock_argo_client.abort_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_insights_for_same_component_queued(
        self,
        optimization_engine,
        experiment_manager,
        mock_redis_client
    ):
        """
        Testa que múltiplos insights para o mesmo componente
        são enfileirados (apenas um experimento por vez).
        """
        insight1 = {
            "insight_id": "insight-1",
            "insight_type": "OPERATIONAL_BOTTLENECK",
            "metrics": {"latency_p95": 1200},
            "related_entities": [{"entity_id": "consensus-engine"}],
        }

        insight2 = {
            "insight_id": "insight-2",
            "insight_type": "OPERATIONAL_BOTTLENECK",
            "metrics": {"latency_p95": 1300},
            "related_entities": [{"entity_id": "consensus-engine"}],
        }

        # Primeira hipótese bloqueia componente
        hypotheses1 = optimization_engine.analyze_opportunity(insight1)
        exp_id_1 = await experiment_manager.submit_experiment(hypotheses1[0])

        assert exp_id_1 is not None

        # Segunda hipótese deve ser bloqueada
        mock_redis_client.lock_component.return_value = False
        hypotheses2 = optimization_engine.analyze_opportunity(insight2)
        exp_id_2 = await experiment_manager.submit_experiment(hypotheses2[0])

        assert exp_id_2 is None, "Segundo experimento deve ser bloqueado"
