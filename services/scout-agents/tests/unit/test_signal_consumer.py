"""
Unit tests para SignalFeedbackConsumer.

Testa o consumer que processa exploration-signals do Scout Agents,
implementando feedback loop para ajuste de parâmetros de exploração.
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from collections import defaultdict

from src.consumers.signal_consumer import SignalFeedbackConsumer


@pytest.fixture
def mock_settings():
    """Settings mock para testes."""
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.kafka_consumer_group_id = "test-group"
    settings.kafka_topics_signals = "exploration-signals"
    return settings


@pytest.fixture
def mock_exploration_engine():
    """Exploration engine mock."""
    engine = AsyncMock()
    return engine


@pytest.fixture
def mock_pheromone_client():
    """Pheromone client mock."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.signals_feedback_consumed_total = MagicMock()
    metrics.signals_feedback_consumed_total.labels.return_value = MagicMock()
    metrics.signals_feedback_consumed_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture
def consumer(mock_settings, mock_exploration_engine, mock_pheromone_client, mock_metrics):
    """Consumer instance para testes."""
    return SignalFeedbackConsumer(
        settings=mock_settings,
        exploration_engine=mock_exploration_engine,
        pheromone_client=mock_pheromone_client,
        metrics=mock_metrics
    )


class TestSignalFeedbackConsumerInitialization:
    """Testes de inicialização do consumer."""

    def test_consumer_initialization(self, consumer):
        """Consumer deve ter atributos corretos após criação."""
        assert consumer.settings is not None
        assert consumer.exploration_engine is not None
        assert consumer.pheromone_client is not None
        assert consumer.metrics is not None
        assert consumer.consumer is None
        assert consumer.running is False
        assert isinstance(consumer.signal_stats, defaultdict)

    @pytest.mark.asyncio
    async def test_consumer_initialize(self, consumer):
        """Consumer deve inicializar corretamente."""
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()

        with patch('src.consumers.signal_consumer.instrument_kafka_consumer') as mock_instrument:
            mock_instrument.return_value = mock_producer

            await consumer.initialize()

            assert consumer.consumer is not None
            mock_producer.start.assert_called_once()


class TestProcessMessage:
    """Testes de processamento de mensagens."""

    @pytest.mark.asyncio
    async def test_process_signal_feedback(self, consumer):
        """Deve processar feedback de sinal."""
        signal_data = {
            'signal_id': 'signal-123',
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.8,
            'confidence': 0.9,
            'relevance_score': 0.7,
            'risk_score': 0.2,
            'correlation_id': 'corr-789',
            'metadata': {
                'used_in_exploration': True
            }
        }

        message = MagicMock()
        message.value = signal_data
        message.headers = []
        message.topic = 'exploration-signals'
        message.partition = 0
        message.offset = 0

        # Mock commit
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar estatísticas atualizadas
        key = "BUSINESS:PATTERN_EMERGING"
        assert consumer.signal_stats[key]['total'] == 1
        assert consumer.signal_stats[key]['acted_upon'] == 1
        assert consumer.signal_stats[key]['ignored'] == 0

    @pytest.mark.asyncio
    async def test_process_ignored_signal(self, consumer):
        """Deve processar sinal ignorado (não utilizado)."""
        signal_data = {
            'signal_id': 'signal-123',
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.8,
            'confidence': 0.9,
            'relevance_score': 0.7,
            'risk_score': 0.2,
            'metadata': {
                'used_in_exploration': False  # Não utilizado
            }
        }

        message = MagicMock()
        message.value = signal_data
        message.headers = []

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar estatísticas
        key = "BUSINESS:PATTERN_EMERGING"
        assert consumer.signal_stats[key]['ignored'] == 1
        assert consumer.signal_stats[key]['acted_upon'] == 0

    @pytest.mark.asyncio
    async def test_update_signal_stats_rolling_average(self, consumer):
        """Deve calcular média móvel de curiosity score."""
        # Primeiro sinal
        signal_data_1 = {
            'signal_id': 'signal-1',
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.5,
            'metadata': {'used_in_exploration': True}
        }

        message_1 = MagicMock()
        message_1.value = signal_data_1
        message_1.headers = []

        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message_1)

        # Segundo sinal com score diferente
        signal_data_2 = {
            'signal_id': 'signal-2',
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.9,
            'metadata': {'used_in_exploration': True}
        }

        message_2 = MagicMock()
        message_2.value = signal_data_2
        message_2.headers = []

        await consumer._process_message(message_2)

        # Média deve ser (0.5 + 0.9) / 2 = 0.7
        key = "BUSINESS:PATTERN_EMERGING"
        assert abs(consumer.signal_stats[key]['avg_curiosity'] - 0.7) < 0.01


class TestAdjustExplorationParameters:
    """Testes de ajuste de parâmetros de exploração."""

    @pytest.mark.asyncio
    async def test_reduce_thresholds_low_utilization(self, consumer):
        """Deve reduzir thresholds quando utilização é baixa."""
        # Preparar estatísticas
        key = "BUSINESS:PATTERN_EMERGING"
        consumer.signal_stats[key] = {
            'total': 20,
            'acted_upon': 3,  # 15% utilização (baixa)
            'ignored': 17,
            'avg_curiosity': 0.8,  # Alta curiosidade
            'last_updated': datetime.utcnow()
        }

        signal = {
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.8,
            'relevance_score': 0.7
        }

        with patch.object(consumer, '_adjust_thresholds', new=AsyncMock()) as mock_adjust:
            await consumer._adjust_exploration_parameters(signal)

            # Deve reduzir thresholds
            mock_adjust.assert_called_once_with(
                'BUSINESS',
                'lower',
                0.05
            )

    @pytest.mark.asyncio
    async def test_increase_thresholds_high_utilization(self, consumer):
        """Deve aumentar thresholds quando utilização é alta."""
        # Preparar estatísticas
        key = "BUSINESS:PATTERN_EMERGING"
        consumer.signal_stats[key] = {
            'total': 20,
            'acted_upon': 18,  # 90% utilização (alta)
            'ignored': 2,
            'avg_curiosity': 0.4,  # Baixa curiosidade
            'last_updated': datetime.utcnow()
        }

        signal = {
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.4,
            'relevance_score': 0.7
        }

        with patch.object(consumer, '_adjust_thresholds', new=AsyncMock()) as mock_adjust:
            await consumer._adjust_exploration_parameters(signal)

            # Deve aumentar thresholds
            mock_adjust.assert_called_once_with(
                'BUSINESS',
                'higher',
                0.05
            )

    @pytest.mark.asyncio
    async def test_wait_for_minimum_samples(self, consumer):
        """Deve esperar por amostragem mínima antes de ajustar."""
        # Estatísticas insuficientes
        key = "BUSINESS:PATTERN_EMERGING"
        consumer.signal_stats[key] = {
            'total': 5,  # Menos que 10
            'acted_upon': 1,
            'ignored': 4,
            'avg_curiosity': 0.8,
            'last_updated': datetime.utcnow()
        }

        signal = {
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.8,
            'relevance_score': 0.7
        }

        with patch.object(consumer, '_adjust_thresholds', new=AsyncMock()) as mock_adjust:
            await consumer._adjust_exploration_parameters(signal)

            # Não deve ajustar
            mock_adjust.assert_not_called()

    @pytest.mark.asyncio
    async def test_reinforce_pheromone_high_relevance(self, consumer):
        """Deve reforçar feromônio para sinal de alta relevância."""
        key = "BUSINESS:PATTERN_EMERGING"
        consumer.signal_stats[key] = {
            'total': 20,
            'acted_upon': 10,
            'ignored': 10,
            'avg_curiosity': 0.7,
            'last_updated': datetime.utcnow()
        }

        signal = {
            'signal_id': 'signal-123',
            'signal_type': 'PATTERN_EMERGING',
            'exploration_domain': 'BUSINESS',
            'curiosity_score': 0.7,
            'relevance_score': 0.8  # Alta relevância
        }

        with patch.object(consumer, '_reinforce_signal_pheromone', new=AsyncMock()) as mock_reinforce:
            await consumer._adjust_exploration_parameters(signal)

            # Deve reforçar feromônio
            mock_reinforce.assert_called_once_with(signal)


class TestGetFeedbackStats:
    """Testes de recuperação de estatísticas."""

    def test_get_feedback_stats_empty(self, consumer):
        """Deve retornar estatísticas vazias quando não há dados."""
        stats = consumer.get_feedback_stats()

        assert stats['total_signals'] == 0
        assert stats['total_acted_upon'] == 0
        assert stats['by_type'] == {}

    def test_get_feedback_stats_with_data(self, consumer):
        """Deve retornar estatísticas corretas."""
        consumer.signal_stats['BUSINESS:PATTERN_EMERGING'] = {
            'total': 10,
            'acted_upon': 7,
            'ignored': 3,
            'avg_curiosity': 0.75,
            'last_updated': datetime.utcnow()
        }
        consumer.signal_stats['TECHNICAL:ANOMALY_POSITIVE'] = {
            'total': 5,
            'acted_upon': 2,
            'ignored': 3,
            'avg_curiosity': 0.6,
            'last_updated': datetime.utcnow()
        }

        stats = consumer.get_feedback_stats()

        assert stats['total_signals'] == 15
        assert stats['total_acted_upon'] == 9
        assert 'BUSINESS:PATTERN_EMERGING' in stats['by_type']
        assert 'TECHNICAL:ANOMALY_POSITIVE' in stats['by_type']


class TestConsumerLifecycle:
    """Testes de ciclo de vida do consumer."""

    @pytest.mark.asyncio
    async def test_start_stop_consumer(self, consumer):
        """Deve iniciar e parar consumer corretamente."""
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()
        mock_producer.__aiter__ = AsyncMock(return_value=iter([]))

        with patch('src.consumers.signal_consumer.instrument_kafka_consumer') as mock_instrument:
            mock_instrument.return_value = mock_producer

            await consumer.initialize()
            assert consumer.consumer is not None

            # Simular start (loop vazio)
            start_task = asyncio.create_task(consumer.start())
            await asyncio.sleep(0.1)
            consumer.running = False
            await start_task

            await consumer.stop()
            mock_producer.stop.assert_called_once()
