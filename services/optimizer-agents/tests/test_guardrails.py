# -*- coding: utf-8 -*-
"""
Testes unitarios para o sistema de guardrails.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import numpy as np

from src.experimentation.guardrails import (
    GuardrailMonitor,
    GuardrailCheckResult,
    SequentialTestResult,
)


@pytest.fixture
def mock_redis_client():
    """Fixture para Redis client mockado."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_mongodb_client():
    """Fixture para MongoDB client mockado."""
    return AsyncMock()


@pytest.fixture
def guardrail_monitor(mock_mongodb_client, mock_redis_client):
    """Fixture para GuardrailMonitor."""
    return GuardrailMonitor(
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        min_sample_size=100,
    )


class TestGuardrailCheck:
    """Testes para verificacao de guardrails."""

    @pytest.mark.asyncio
    async def test_guardrail_not_violated(self, guardrail_monitor):
        """Testar quando guardrail NAO e violado."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        # Control e treatment com metricas similares
        control_metrics = {"error_rate": [0.01] * 100}
        treatment_metrics = {"error_rate": [0.011] * 100}  # 10% piora (< 5% degradacao)

        result = await guardrail_monitor.check_guardrails(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        assert isinstance(result, GuardrailCheckResult)
        assert result.violated is False
        assert len(result.violations) == 0
        assert result.should_abort is False

    @pytest.mark.asyncio
    async def test_guardrail_violated(self, guardrail_monitor):
        """Testar quando guardrail E violado."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        # Treatment com degradacao significativa
        control_metrics = {"error_rate": [0.01] * 100}
        treatment_metrics = {"error_rate": [0.015] * 100}  # 50% piora (> 5% degradacao)

        result = await guardrail_monitor.check_guardrails(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        assert result.violated is True
        assert len(result.violations) > 0
        assert result.violations[0].metric_name == "error_rate"

    @pytest.mark.asyncio
    async def test_abort_threshold_triggered(self, guardrail_monitor):
        """Testar quando abort threshold e atingido."""
        guardrails_config = [
            {
                "metric_name": "latency_p95",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        # Treatment com degradacao critica
        control_metrics = {"latency_p95": [100.0] * 100}
        treatment_metrics = {"latency_p95": [115.0] * 100}  # 15% piora (> 10% abort)

        result = await guardrail_monitor.check_guardrails(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        assert result.should_abort is True
        assert result.abort_reason is not None
        assert "abort" in result.violations[0].severity

    @pytest.mark.asyncio
    async def test_multiple_guardrails(self, guardrail_monitor):
        """Testar com multiplos guardrails."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            },
            {
                "metric_name": "latency_p95",
                "max_degradation_percentage": 0.10,
                "abort_threshold": 0.20,
            },
        ]

        control_metrics = {
            "error_rate": [0.01] * 100,
            "latency_p95": [100.0] * 100,
        }
        treatment_metrics = {
            "error_rate": [0.02] * 100,  # 100% piora (violado)
            "latency_p95": [105.0] * 100,  # 5% piora (OK)
        }

        result = await guardrail_monitor.check_guardrails(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        assert result.violated is True
        assert len(result.violations) == 1
        assert result.violations[0].metric_name == "error_rate"
        assert "latency_p95" in result.passed_metrics


class TestShouldAbort:
    """Testes para decisao de abort."""

    @pytest.mark.asyncio
    async def test_should_abort_insufficient_sample(self, guardrail_monitor):
        """Testar que NAO aborta com amostra insuficiente."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        # Mesmo com violacao, amostra insuficiente nao deve abortar
        control_metrics = {"error_rate": [0.01] * 50}
        treatment_metrics = {"error_rate": [0.05] * 50}  # Grande degradacao

        result = await guardrail_monitor.should_abort(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
            current_sample_size=50,  # Menor que min_sample_size (100)
        )

        assert result["should_abort"] is False
        assert "Amostra insuficiente" in result["reason"]

    @pytest.mark.asyncio
    async def test_should_abort_with_sufficient_sample(self, guardrail_monitor):
        """Testar abort com amostra suficiente."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        control_metrics = {"error_rate": [0.01] * 200}
        treatment_metrics = {"error_rate": [0.05] * 200}  # Grande degradacao

        result = await guardrail_monitor.should_abort(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
            current_sample_size=200,  # Maior que min_sample_size
        )

        assert result["should_abort"] is True
        assert "violations" in result


class TestSequentialTesting:
    """Testes para sequential testing (SPRT)."""

    @pytest.mark.asyncio
    async def test_sequential_testing_continue(self, guardrail_monitor):
        """Testar que sequential testing continua quando inconcluso."""
        np.random.seed(42)
        # Dados com pequena diferenca - inconcluso
        control_data = list(np.random.normal(100, 10, 150))
        treatment_data = list(np.random.normal(99, 10, 150))  # 1% diferenca

        result = await guardrail_monitor.apply_sequential_testing(
            experiment_id="test-exp",
            control_data=control_data,
            treatment_data=treatment_data,
        )

        assert isinstance(result, SequentialTestResult)
        assert result.minimum_samples_reached is True

    @pytest.mark.asyncio
    async def test_sequential_testing_insufficient_samples(self, guardrail_monitor):
        """Testar sequential testing com amostras insuficientes."""
        control_data = [100.0] * 50
        treatment_data = [50.0] * 50  # Grande diferenca mas poucos dados

        result = await guardrail_monitor.apply_sequential_testing(
            experiment_id="test-exp",
            control_data=control_data,
            treatment_data=treatment_data,
        )

        assert result.can_stop_early is False
        assert result.minimum_samples_reached is False

    @pytest.mark.asyncio
    async def test_sequential_testing_with_mde(self, guardrail_monitor):
        """Testar sequential testing com MDE especifico."""
        np.random.seed(42)
        control_data = list(np.random.normal(100, 10, 200))
        treatment_data = list(np.random.normal(85, 10, 200))  # 15% melhor

        result = await guardrail_monitor.apply_sequential_testing(
            experiment_id="test-exp",
            control_data=control_data,
            treatment_data=treatment_data,
            minimum_detectable_effect=0.10,  # 10% MDE
        )

        assert result.samples_analyzed == 200


class TestGuardrailStatus:
    """Testes para status de guardrails."""

    @pytest.mark.asyncio
    async def test_get_guardrail_status_cached(self, guardrail_monitor, mock_redis_client):
        """Testar recuperacao de status do cache."""
        import json

        cached_status = {
            "violated": True,
            "should_abort": False,
            "violations_count": 1,
        }
        mock_redis_client.get.return_value = json.dumps(cached_status)

        status = await guardrail_monitor.get_guardrail_status("test-exp")

        assert status is not None
        assert status["violated"] is True
        assert status["violations_count"] == 1

    @pytest.mark.asyncio
    async def test_get_guardrail_status_not_cached(self, guardrail_monitor, mock_redis_client):
        """Testar quando status nao esta em cache."""
        mock_redis_client.get.return_value = None

        status = await guardrail_monitor.get_guardrail_status("test-exp")

        assert status is None

    @pytest.mark.asyncio
    async def test_save_guardrail_status(self, guardrail_monitor, mock_redis_client):
        """Testar salvamento de status no Redis."""
        result = GuardrailCheckResult(
            violated=True,
            violations=[],
            should_abort=False,
            abort_reason=None,
            all_metrics_checked=["error_rate"],
            passed_metrics=[],
        )

        await guardrail_monitor.save_guardrail_status("test-exp", result)

        mock_redis_client.setex.assert_called_once()


class TestEdgeCases:
    """Testes para casos extremos."""

    @pytest.mark.asyncio
    async def test_empty_metrics(self, guardrail_monitor):
        """Testar com metricas vazias."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        result = await guardrail_monitor.check_guardrails(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics={},
            treatment_metrics={},
        )

        assert result.violated is False
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_zero_baseline(self, guardrail_monitor):
        """Testar com baseline zero."""
        guardrails_config = [
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ]

        control_metrics = {"error_rate": [0.0] * 100}
        treatment_metrics = {"error_rate": [0.01] * 100}

        result = await guardrail_monitor.check_guardrails(
            experiment_id="test-exp",
            guardrails_config=guardrails_config,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        # Deve processar sem erro
        assert result is not None
