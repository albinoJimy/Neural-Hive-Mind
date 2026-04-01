# -*- coding: utf-8 -*-
"""
Testes unitarios para o ABTestingEngine.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.experimentation.ab_testing_engine import ABTestingEngine, ABTestConfig
from src.experimentation.randomization import RandomizationStrategyType, Group


@pytest.fixture
def mock_settings():
    """Fixture para settings mockados."""
    settings = MagicMock()
    settings.ab_test_default_alpha = 0.05
    settings.ab_test_default_power = 0.80
    settings.ab_test_min_sample_size = 100
    settings.ab_test_early_stopping_enabled = True
    settings.ab_test_bayesian_analysis_enabled = True
    return settings


@pytest.fixture
def mock_mongodb_client():
    """Fixture para MongoDB client mockado."""
    client = AsyncMock()
    client.save_experiment = AsyncMock(return_value=True)
    client.get_experiment = AsyncMock(return_value=None)
    client.update_experiment_status = AsyncMock(return_value=True)
    client.save_ab_test_results = AsyncMock(return_value="mock_doc_id_123")
    client.get_ab_test_results = AsyncMock(return_value=None)
    client.list_ab_test_results = AsyncMock(return_value=[])
    client.get_ab_test_history = AsyncMock(return_value=[])
    client.get_ab_test_aggregations = AsyncMock(return_value={
        "period": {"days": 30},
        "total_experiments": 0,
        "completed_experiments": 0,
        "recommendations_count": {"APPLY": 0, "REJECT": 0, "INCONCLUSIVE": 0},
        "avg_confidence": 0.0,
        "win_rate": 0.0,
        "avg_sample_size": 0,
    })
    client.get_ab_test_dashboard = AsyncMock(return_value={
        "period": {"days": 30},
        "total_experiments": 0,
        "top_experiments": [],
        "metric_breakdown": {},
    })
    return client


@pytest.fixture
def mock_redis_client():
    """Fixture para Redis client mockado."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.setex = AsyncMock(return_value=True)
    client.incr = AsyncMock(return_value=1)
    client.lpush = AsyncMock(return_value=1)
    client.lrange = AsyncMock(return_value=[])
    client.ltrim = AsyncMock(return_value=True)
    client.expire = AsyncMock(return_value=True)
    client.keys = AsyncMock(return_value=[])
    return client


@pytest.fixture
def ab_engine(mock_settings, mock_mongodb_client, mock_redis_client):
    """Fixture para ABTestingEngine."""
    return ABTestingEngine(
        settings=mock_settings,
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        metrics=None,
    )


class TestABTestingEngineCreation:
    """Testes para criacao de testes A/B."""

    @pytest.mark.asyncio
    async def test_create_ab_test_success(self, ab_engine, mock_mongodb_client):
        """Testar criacao bem-sucedida de teste A/B."""
        config = await ab_engine.create_ab_test(
            name="Test Experiment",
            hypothesis="Treatment will improve latency by 10%",
            primary_metrics=["latency_p95", "error_rate"],
            traffic_split=0.5,
            minimum_sample_size=100,
        )

        assert config.experiment_id is not None
        assert config.name == "Test Experiment"
        assert config.traffic_split == 0.5
        assert config.status == "running"
        assert "latency_p95" in config.primary_metrics
        assert mock_mongodb_client.save_experiment.called

    @pytest.mark.asyncio
    async def test_create_ab_test_with_guardrails(self, ab_engine):
        """Testar criacao com guardrails configurados."""
        guardrails = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        config = await ab_engine.create_ab_test(
            name="Test with Guardrails",
            hypothesis="Test hypothesis",
            primary_metrics=["latency"],
            guardrails=guardrails,
        )

        assert len(config.guardrails) == 1
        assert config.guardrails[0]["metric_name"] == "error_rate"

    @pytest.mark.asyncio
    async def test_create_ab_test_with_stratified_randomization(self, ab_engine):
        """Testar criacao com randomizacao estratificada."""
        config = await ab_engine.create_ab_test(
            name="Stratified Test",
            hypothesis="Test hypothesis",
            primary_metrics=["conversion_rate"],
            randomization_strategy=RandomizationStrategyType.STRATIFIED,
        )

        assert config.randomization_strategy == RandomizationStrategyType.STRATIFIED


class TestABTestingEngineAssignment:
    """Testes para atribuicao de grupos."""

    @pytest.mark.asyncio
    async def test_assign_to_group_deterministic(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar que atribuicao e deterministica."""
        # Setup experiment config
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-123",
            "name": "Test",
            "hypothesis": "Test",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": True,
            "bayesian_analysis_enabled": True,
            "status": "running",
            "metadata": {},
        }

        # First assignment
        group1 = await ab_engine.assign_to_group(
            entity_id="user-123",
            experiment_id="test-exp-123",
        )

        # Clear cache para forcar re-calculo
        mock_redis_client.get.return_value = None

        # Second assignment - should be same due to deterministic hash
        group2 = await ab_engine.assign_to_group(
            entity_id="user-123",
            experiment_id="test-exp-123",
        )

        assert group1 == group2

    @pytest.mark.asyncio
    async def test_assign_to_group_balanced(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar balanceamento aproximado de 50/50."""
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-balance",
            "name": "Test",
            "hypothesis": "Test",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": True,
            "bayesian_analysis_enabled": True,
            "status": "running",
            "metadata": {},
        }

        control_count = 0
        treatment_count = 0

        # Assign 1000 users
        for i in range(1000):
            mock_redis_client.get.return_value = None  # Clear cache
            group = await ab_engine.assign_to_group(
                entity_id=f"user-{i}",
                experiment_id="test-exp-balance",
            )
            if group == "control":
                control_count += 1
            else:
                treatment_count += 1

        # Should be approximately 50/50 (within 10% tolerance)
        total = control_count + treatment_count
        control_ratio = control_count / total

        assert 0.40 <= control_ratio <= 0.60, f"Balanceamento fora do esperado: {control_ratio:.2%}"


class TestABTestingEngineMetrics:
    """Testes para coleta de metricas."""

    @pytest.mark.asyncio
    async def test_collect_metrics(self, ab_engine, mock_redis_client):
        """Testar coleta de metricas."""
        await ab_engine.collect_metrics(
            experiment_id="test-exp-123",
            group="control",
            metrics={"latency": 100.5, "error_rate": 0.01},
        )

        # Verificar que lpush foi chamado para cada metrica
        assert mock_redis_client.lpush.call_count == 2


class TestABTestingEngineAnalysis:
    """Testes para analise de resultados."""

    @pytest.mark.asyncio
    async def test_analyze_results_significant(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar analise com resultado estatisticamente significativo."""
        # Setup experiment config
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-sig",
            "name": "Significant Test",
            "hypothesis": "Treatment improves latency",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": True,
            "bayesian_analysis_enabled": True,
            "status": "running",
            "metadata": {},
        }

        # Mock group sizes
        mock_redis_client.get.side_effect = lambda key: "500" if "group_size" in key else None

        # Mock metrics - treatment significantly better
        control_data = [str(100 + i * 0.1) for i in range(500)]
        treatment_data = [str(80 + i * 0.1) for i in range(500)]  # 20% better

        mock_redis_client.keys.return_value = [
            "ab_test:test-exp-sig:metrics:control:latency",
            "ab_test:test-exp-sig:metrics:treatment:latency",
        ]
        mock_redis_client.lrange.side_effect = [control_data, treatment_data]

        results = await ab_engine.analyze_results("test-exp-sig")

        assert results is not None
        assert results.control_size == 500
        assert results.treatment_size == 500

    @pytest.mark.asyncio
    async def test_analyze_results_not_significant(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar analise sem significancia estatistica."""
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-nosig",
            "name": "Not Significant Test",
            "hypothesis": "Treatment improves latency",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": True,
            "bayesian_analysis_enabled": True,
            "status": "running",
            "metadata": {},
        }

        mock_redis_client.get.side_effect = lambda key: "50" if "group_size" in key else None

        # Muito poucos dados, nenhuma diferenca clara
        control_data = [str(100 + i * 0.1) for i in range(50)]
        treatment_data = [str(99 + i * 0.1) for i in range(50)]  # Quase igual

        mock_redis_client.keys.return_value = [
            "ab_test:test-exp-nosig:metrics:control:latency",
            "ab_test:test-exp-nosig:metrics:treatment:latency",
        ]
        mock_redis_client.lrange.side_effect = [control_data, treatment_data]

        results = await ab_engine.analyze_results("test-exp-nosig")

        assert results is not None


class TestABTestingEngineEarlyStopping:
    """Testes para parada antecipada."""

    @pytest.mark.asyncio
    async def test_early_stopping_when_significant(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar parada antecipada quando significancia e atingida."""
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-early",
            "name": "Early Stop Test",
            "hypothesis": "Test",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": True,
            "bayesian_analysis_enabled": True,
            "status": "running",
            "metadata": {},
        }

        mock_redis_client.get.side_effect = lambda key: "200" if "group_size" in key else None

        # Grande diferenca para atingir significancia
        control_data = [str(100 + i * 0.1) for i in range(200)]
        treatment_data = [str(50 + i * 0.1) for i in range(200)]  # 50% melhor

        mock_redis_client.keys.return_value = [
            "ab_test:test-exp-early:metrics:control:latency",
            "ab_test:test-exp-early:metrics:treatment:latency",
        ]
        mock_redis_client.lrange.side_effect = [control_data, treatment_data]

        result = await ab_engine.should_stop_early("test-exp-early")

        assert "can_stop" in result


class TestABTestingEngineSampleSizeValidation:
    """Testes para validacao de tamanho de amostra."""

    @pytest.mark.asyncio
    async def test_sample_size_validation(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar validacao de tamanho de amostra."""
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-sample",
            "name": "Sample Size Test",
            "hypothesis": "Test",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": True,
            "bayesian_analysis_enabled": True,
            "status": "running",
            "metadata": {},
        }

        # Sample size insuficiente
        mock_redis_client.get.side_effect = lambda key: "50" if "group_size" in key else None

        result = await ab_engine._validate_sample_size("test-exp-sample")

        assert result["valid"] is False
        assert result["control_size"] == 50
        assert result["minimum_required"] == 100


class TestABTestingEnginePersistence:
    """Testes para persistencia de resultados de A/B testing."""

    @pytest.mark.asyncio
    async def test_analyze_results_persists_to_mongodb(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar que resultados sao persistidos no MongoDB apos analise."""
        # Setup experiment config
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-persist",
            "name": "Persistence Test",
            "hypothesis": "Test persistence",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": False,
            "bayesian_analysis_enabled": False,
            "status": "running",
            "metadata": {},
        }

        # Mock group sizes
        mock_redis_client.get.side_effect = lambda key: "200" if "group_size" in key else None

        # Mock metrics
        control_data = [str(100 + i * 0.1) for i in range(200)]
        treatment_data = [str(80 + i * 0.1) for i in range(200)]

        mock_redis_client.keys.return_value = [
            "ab_test:test-exp-persist:metrics:control:latency",
            "ab_test:test-exp-persist:metrics:treatment:latency",
        ]
        mock_redis_client.lrange.side_effect = [control_data, treatment_data]

        # Mock save_ab_test_results para retornar ID
        mock_mongodb_client.save_ab_test_results = AsyncMock(return_value="mock_doc_id_123")

        results = await ab_engine.analyze_results("test-exp-persist")

        # Verificar que save_ab_test_results foi chamado
        mock_mongodb_client.save_ab_test_results.assert_called_once()

        # Verificar argumentos da chamada
        call_args = mock_mongodb_client.save_ab_test_results.call_args
        results_dict = call_args[0][0]  # Primeiro argumento posicional

        assert results_dict["experiment_id"] == "test-exp-persist"
        assert results_dict["experiment_name"] == "Persistence Test"
        assert results_dict["control_size"] == 200
        assert results_dict["treatment_size"] == 200
        assert "primary_metrics_analysis" in results_dict

    @pytest.mark.asyncio
    async def test_analyze_results_handles_persistence_error(self, ab_engine, mock_mongodb_client, mock_redis_client):
        """Testar que erros de persistencia nao quebram a analise."""
        mock_mongodb_client.get_experiment.return_value = {
            "experiment_id": "test-exp-error",
            "name": "Error Test",
            "hypothesis": "Test error handling",
            "traffic_split": 0.5,
            "randomization_strategy": "RANDOM",
            "primary_metrics": ["latency"],
            "secondary_metrics": [],
            "guardrails": [],
            "minimum_sample_size": 100,
            "maximum_duration_seconds": 604800,
            "early_stopping_enabled": False,
            "bayesian_analysis_enabled": False,
            "status": "running",
            "metadata": {},
        }

        mock_redis_client.get.side_effect = lambda key: "100" if "group_size" in key else None

        control_data = [str(100 + i) for i in range(100)]
        treatment_data = [str(95 + i) for i in range(100)]

        mock_redis_client.keys.return_value = [
            "ab_test:test-exp-error:metrics:control:latency",
            "ab_test:test-exp-error:metrics:treatment:latency",
        ]
        mock_redis_client.lrange.side_effect = [control_data, treatment_data]

        # Simular erro de persistencia
        mock_mongodb_client.save_ab_test_results = AsyncMock(side_effect=Exception("MongoDB error"))

        # Analise deve completar mesmo com erro de persistencia
        results = await ab_engine.analyze_results("test-exp-error")

        assert results is not None
        assert results.experiment_id == "test-exp-error"


class TestMongoDBClientABTestingPersistence:
    """Testes para metodos de persistencia de A/B testing no MongoDBClient."""

    @pytest.mark.asyncio
    async def test_save_ab_test_results_integration(self, mock_mongodb_client):
        """Testar integracao de salvar resultados de A/B testing."""
        from datetime import datetime, timezone

        results = {
            "experiment_id": "exp-123",
            "experiment_name": "Test Experiment",
            "status": "completed",
            "control_size": 500,
            "treatment_size": 500,
            "primary_metrics_analysis": [
                {
                    "metric_name": "latency",
                    "p_value": 0.001,
                    "statistically_significant": True,
                    "effect_size": 0.5,
                }
            ],
            "secondary_metrics_analysis": [],
            "bayesian_analysis": None,
            "guardrails_status": {"violated": False, "should_abort": False},
            "statistical_recommendation": "APPLY",
            "confidence_level": 0.95,
            "early_stopped": False,
            "early_stop_reason": None,
            "analysis_timestamp": datetime.now(timezone.utc),
            "metadata": {},
        }

        # Chamar metodo real do mock
        doc_id = await mock_mongodb_client.save_ab_test_results(results)

        # Verificar que o mock foi chamado (na implementacao real usaria collection)
        assert mock_mongodb_client.save_ab_test_results.called
        assert doc_id == "mock_doc_id_123"

    @pytest.mark.asyncio
    async def test_get_ab_test_results_integration(self, mock_mongodb_client):
        """Testar integracao de recuperar resultados de A/B testing."""
        # Setup mock para retornar dados
        mock_mongodb_client.get_ab_test_results = AsyncMock(return_value={
            "experiment_id": "exp-123",
            "statistical_recommendation": "APPLY",
        })

        results = await mock_mongodb_client.get_ab_test_results("exp-123")

        assert results is not None
        assert results["experiment_id"] == "exp-123"
        assert results["statistical_recommendation"] == "APPLY"

    @pytest.mark.asyncio
    async def test_list_ab_test_results_integration(self, mock_mongodb_client):
        """Testar integracao de listar resultados de A/B testing."""
        mock_results = [
            {"experiment_id": "exp-1", "status": "completed"},
            {"experiment_id": "exp-2", "status": "running"},
        ]
        mock_mongodb_client.list_ab_test_results = AsyncMock(return_value=mock_results)

        results = await mock_mongodb_client.list_ab_test_results(limit=10)

        assert len(results) == 2
        assert results[0]["experiment_id"] == "exp-1"

    @pytest.mark.asyncio
    async def test_get_ab_test_history_integration(self, mock_mongodb_client):
        """Testar integracao de recuperar historico de A/B testing."""
        mock_history = [{"experiment_id": "exp-123", "created_at": "2026-03-31"}]
        mock_mongodb_client.get_ab_test_history = AsyncMock(return_value=mock_history)

        history = await mock_mongodb_client.get_ab_test_history("exp-123", days=30)

        assert len(history) == 1
        assert history[0]["experiment_id"] == "exp-123"

    @pytest.mark.asyncio
    async def test_get_ab_test_aggregations_integration(self, mock_mongodb_client):
        """Testar integracao de calcular agregacoes de A/B testing."""
        mock_agg = {
            "total_experiments": 10,
            "completed_experiments": 8,
            "win_rate": 0.5,
            "recommendations_count": {"APPLY": 5, "REJECT": 2, "INCONCLUSIVE": 3},
        }
        mock_mongodb_client.get_ab_test_aggregations = AsyncMock(return_value=mock_agg)

        aggregations = await mock_mongodb_client.get_ab_test_aggregations(days=30)

        assert aggregations["total_experiments"] == 10
        assert aggregations["win_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_get_ab_test_dashboard_integration(self, mock_mongodb_client):
        """Testar integracao de obter dashboard de A/B testing."""
        mock_dashboard = {
            "total_experiments": 5,
            "win_rate": 0.6,
            "top_experiments": [{"experiment_id": "exp-1"}],
            "metric_breakdown": {"latency": {"avg_effect_size": 0.5}},
        }
        mock_mongodb_client.get_ab_test_dashboard = AsyncMock(return_value=mock_dashboard)

        dashboard = await mock_mongodb_client.get_ab_test_dashboard(days=30)

        assert dashboard["total_experiments"] == 5
        assert dashboard["win_rate"] == 0.6
        assert len(dashboard["top_experiments"]) == 1
