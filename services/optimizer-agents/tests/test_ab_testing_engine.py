# -*- coding: utf-8 -*-
"""
Testes unitarios para o ABTestingEngine.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

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
