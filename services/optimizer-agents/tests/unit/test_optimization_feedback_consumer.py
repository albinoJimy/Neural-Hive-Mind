"""
Unit tests para OptimizationFeedbackConsumer.

Testa o consumer que processa optimization.applied do Optimizer Agents,
implementando feedback loop para ajuste de estratégias de otimização.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.consumers.optimization_feedback_consumer import (
    OptimizationFeedbackConsumer,
    OptimizationStatus,
    OptimizationType,
)


@pytest.fixture
def mock_settings():
    """Settings mock para testes."""
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.kafka_consumer_group_id = "test-group"
    settings.kafka_optimization_topic = "optimization.applied"
    return settings


@pytest.fixture
def mock_optimization_engine():
    """Optimization engine mock."""
    engine = AsyncMock()
    return engine


@pytest.fixture
def mock_experiment_manager():
    """Experiment manager mock."""
    manager = AsyncMock()
    return manager


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.increment_counter = MagicMock()
    return metrics


@pytest.fixture
def consumer(mock_settings, mock_optimization_engine, mock_experiment_manager, mock_metrics):
    """Consumer instance para testes."""
    return OptimizationFeedbackConsumer(
        settings=mock_settings,
        optimization_engine=mock_optimization_engine,
        experiment_manager=mock_experiment_manager,
        metrics=mock_metrics,
    )


class TestOptimizationFeedbackConsumerInitialization:
    """Testes de inicialização do consumer."""

    def test_consumer_initialization(self, consumer):
        """Consumer deve ter atributos corretos após criação."""
        assert consumer.settings is not None
        assert consumer.optimization_engine is not None
        assert consumer.experiment_manager is not None
        assert consumer.metrics is not None
        assert consumer.consumer is None
        assert consumer.running is False
        assert isinstance(consumer.optimization_stats, defaultdict)

    def test_consumer_uses_default_settings(self):
        """Consumer deve usar settings padrão quando não fornecido."""
        consumer = OptimizationFeedbackConsumer()

        assert consumer.settings is not None
        assert consumer.optimization_engine is None
        assert consumer.experiment_manager is None


class TestProcessMessage:
    """Testes de processamento de mensagens."""

    @pytest.mark.asyncio
    async def test_process_applied_optimization(self, consumer):
        """Deve processar otimização aplicada com sucesso."""
        event_data = {
            "optimization_id": "opt-123",
            "optimization_type": OptimizationType.WEIGHT_RECALIBRATION.value,
            "status": OptimizationStatus.APPLIED.value,
            "actual_improvement": 0.15,  # 15% melhoria
        }

        message = MagicMock()
        message.value = json.dumps(event_data).encode("utf-8")

        await consumer._process_message(message)

        # Verificar estatísticas atualizadas
        assert consumer.optimization_stats["WEIGHT_RECALIBRATION"]["total"] == 1
        assert consumer.optimization_stats["WEIGHT_RECALIBRATION"]["successful"] == 1
        assert (
            abs(consumer.optimization_stats["WEIGHT_RECALIBRATION"]["avg_improvement"] - 0.15)
            < 0.01
        )

    @pytest.mark.asyncio
    async def test_process_failed_optimization(self, consumer):
        """Deve processar otimização falha."""
        event_data = {
            "optimization_id": "opt-123",
            "optimization_type": OptimizationType.SLO_ADJUSTMENT.value,
            "status": OptimizationStatus.FAILED.value,
            "actual_improvement": 0.0,
        }

        message = MagicMock()
        message.value = json.dumps(event_data).encode("utf-8")

        await consumer._process_message(message)

        # Verificar falha contabilizada
        assert consumer.optimization_stats["SLO_ADJUSTMENT"]["failed"] == 1

    @pytest.mark.asyncio
    async def test_process_rolled_back_optimization(self, consumer):
        """Deve processar otimização revertida."""
        event_data = {
            "optimization_id": "opt-123",
            "optimization_type": OptimizationType.RESOURCE_SCALING.value,
            "status": OptimizationStatus.ROLLED_BACK.value,
            "actual_improvement": -0.05,  # Degradacao
        }

        message = MagicMock()
        message.value = json.dumps(event_data).encode("utf-8")

        await consumer._process_message(message)

        # Verificar rollback contabilizado
        assert consumer.optimization_stats["RESOURCE_SCALING"]["rolled_back"] == 1
        assert abs(consumer.optimization_stats["RESOURCE_SCALING"]["avg_degradation"] - 0.05) < 0.01

    @pytest.mark.asyncio
    async def test_update_rolling_average_improvement(self, consumer):
        """Deve calcular média móvel de melhoria."""
        # Primeira otimização
        event_data_1 = {
            "optimization_id": "opt-1",
            "optimization_type": OptimizationType.WEIGHT_RECALIBRATION.value,
            "status": OptimizationStatus.APPLIED.value,
            "actual_improvement": 0.10,
        }

        message_1 = MagicMock()
        message_1.value = json.dumps(event_data_1).encode("utf-8")

        await consumer._process_message(message_1)

        # Segunda otimização
        event_data_2 = {
            "optimization_id": "opt-2",
            "optimization_type": OptimizationType.WEIGHT_RECALIBRATION.value,
            "status": OptimizationStatus.APPLIED.value,
            "actual_improvement": 0.20,
        }

        message_2 = MagicMock()
        message_2.value = json.dumps(event_data_2).encode("utf-8")

        await consumer._process_message(message_2)

        # Média deve ser (0.10 + 0.20) / 2 = 0.15
        assert (
            abs(consumer.optimization_stats["WEIGHT_RECALIBRATION"]["avg_improvement"] - 0.15)
            < 0.01
        )


class TestAdjustOptimizationStrategies:
    """Testes de ajuste de estratégias de otimização."""

    @pytest.mark.asyncio
    async def test_reduce_aggressiveness_low_success_rate(self, consumer):
        """Deve reduzir agressividade quando taxa de sucesso é baixa."""
        consumer.optimization_stats["WEIGHT_RECALIBRATION"] = {
            "total": 20,
            "successful": 8,  # 40% sucesso (baixa)
            "failed": 12,
            "rolled_back": 0,
            "avg_improvement": 0.1,
            "avg_degradation": 0.0,
            "last_updated": datetime.now(timezone.utc),
        }

        event = {
            "optimization_type": OptimizationType.WEIGHT_RECALIBRATION.value,
            "status": "APPLIED",
            "actual_improvement": 0.1,
        }

        with patch.object(consumer, "_adjust_aggressiveness", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_optimization_strategies(event)

            # Deve reduzir agressividade
            mock_adjust.assert_called_once_with("WEIGHT_RECALIBRATION", "lower", 0.2)

    @pytest.mark.asyncio
    async def test_increase_aggressiveness_high_success_rate(self, consumer):
        """Deve aumentar agressividade quando taxa de sucesso é alta."""
        consumer.optimization_stats["SLO_ADJUSTMENT"] = {
            "total": 20,
            "successful": 19,  # 95% sucesso (alta)
            "failed": 1,
            "rolled_back": 0,  # Sem rollback
            "avg_improvement": 0.15,
            "avg_degradation": 0.0,
            "last_updated": datetime.now(timezone.utc),
        }

        event = {
            "optimization_type": OptimizationType.SLO_ADJUSTMENT.value,
            "status": "APPLIED",
            "actual_improvement": 0.15,
        }

        with patch.object(consumer, "_adjust_aggressiveness", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_optimization_strategies(event)

            # Deve aumentar agressividade
            mock_adjust.assert_called_once_with("SLO_ADJUSTMENT", "higher", 0.1)

    @pytest.mark.asyncio
    async def test_drastic_reduce_high_rollback_rate(self, consumer):
        """Deve reduzir drasticamente quando taxa de rollback é alta."""
        consumer.optimization_stats["RESOURCE_SCALING"] = {
            "total": 20,
            "successful": 10,
            "failed": 2,
            "rolled_back": 8,  # 40% rollback (alta)
            "avg_improvement": 0.1,
            "avg_degradation": 0.05,
            "last_updated": datetime.now(timezone.utc),
        }

        event = {
            "optimization_type": OptimizationType.RESOURCE_SCALING.value,
            "status": "ROLLED_BACK",
            "actual_improvement": -0.05,
        }

        with patch.object(consumer, "_adjust_aggressiveness", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_optimization_strategies(event)

            # Deve reduzir drasticamente
            mock_adjust.assert_called_once_with("RESOURCE_SCALING", "lower", 0.3)

    @pytest.mark.asyncio
    async def test_increase_threshold_more_degradation(self, consumer):
        """Deve aumentar threshold de melhoria quando há mais degradação."""
        consumer.optimization_stats["PARAMETER_TUNING"] = {
            "total": 20,
            "successful": 10,
            "failed": 5,
            "rolled_back": 5,
            "avg_improvement": 0.05,
            "avg_degradation": 0.15,  # Mais degradação que melhoria
            "last_updated": datetime.now(timezone.utc),
        }

        event = {
            "optimization_type": OptimizationType.PARAMETER_TUNING.value,
            "status": "APPLIED",
            "actual_improvement": 0.05,
        }

        with patch.object(
            consumer, "_adjust_improvement_threshold", new=AsyncMock()
        ) as mock_adjust:
            await consumer._adjust_optimization_strategies(event)

            # Deve aumentar threshold
            mock_adjust.assert_called_once_with("PARAMETER_TUNING", "higher")

    @pytest.mark.asyncio
    async def test_wait_for_minimum_samples(self, consumer):
        """Deve esperar por amostragem mínima antes de ajustar."""
        consumer.optimization_stats["WEIGHT_RECALIBRATION"] = {
            "total": 5,  # Menos que 10
            "successful": 2,
            "failed": 3,
            "rolled_back": 0,
            "avg_improvement": 0.1,
            "avg_degradation": 0.0,
            "last_updated": datetime.now(timezone.utc),
        }

        event = {
            "optimization_type": OptimizationType.WEIGHT_RECALIBRATION.value,
            "status": "APPLIED",
            "actual_improvement": 0.1,
        }

        with patch.object(consumer, "_adjust_aggressiveness", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_optimization_strategies(event)

            # Não deve ajustar
            mock_adjust.assert_not_called()


class TestGetFeedbackStats:
    """Testes de recuperação de estatísticas."""

    def test_get_feedback_stats_empty(self, consumer):
        """Deve retornar estatísticas vazias quando não há dados."""
        stats = consumer.get_feedback_stats()

        assert stats["total_optimizations"] == 0
        assert stats["total_successful"] == 0
        assert stats["total_failed"] == 0
        assert stats["total_rolled_back"] == 0
        assert stats["global_success_rate"] == 0.0

    def test_get_feedback_stats_with_data(self, consumer):
        """Deve retornar estatísticas corretas."""
        consumer.optimization_stats["WEIGHT_RECALIBRATION"] = {
            "total": 15,
            "successful": 12,
            "failed": 2,
            "rolled_back": 1,
            "avg_improvement": 0.15,
            "avg_degradation": 0.02,
            "last_updated": datetime.now(timezone.utc),
        }
        consumer.optimization_stats["SLO_ADJUSTMENT"] = {
            "total": 10,
            "successful": 8,
            "failed": 1,
            "rolled_back": 1,
            "avg_improvement": 0.10,
            "avg_degradation": 0.05,
            "last_updated": datetime.now(timezone.utc),
        }

        stats = consumer.get_feedback_stats()

        assert stats["total_optimizations"] == 25
        assert stats["total_successful"] == 20
        assert stats["total_failed"] == 3
        assert stats["total_rolled_back"] == 2
        # Taxa de sucesso global = 20 / (20 + 3) ≈ 0.87
        assert abs(stats["global_success_rate"] - 0.87) < 0.01


class TestConsumerLifecycle:
    """Testes de ciclo de vida do consumer."""

    def test_start_consumer(self):
        """Deve iniciar consumer corretamente."""
        consumer = OptimizationFeedbackConsumer()

        with patch("src.consumers.optimization_feedback_consumer.Consumer") as mock_consumer_class:
            mock_consumer = MagicMock()
            mock_consumer_class.return_value = mock_consumer
            mock_consumer.subscribe = MagicMock()

            consumer.start()

            mock_consumer.subscribe.assert_called_once()

    def test_stop_consumer(self):
        """Deve parar consumer corretamente."""
        consumer = OptimizationFeedbackConsumer()
        consumer.running = True

        mock_producer = MagicMock()
        consumer.consumer = mock_producer

        consumer.stop()

        mock_producer.close.assert_called_once()
        assert consumer.running is False
