"""Testes de integração para Saga Producer e Metrics."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import asyncio
from collections import defaultdict

from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus
from src.saga.saga_metrics import SagaMetrics, get_saga_metrics, timer


@pytest.fixture
def sample_saga():
    """Saga de exemplo para testes."""
    steps = [
        SagaStep(
            step_id='step-1',
            name='validate_plan',
            action='validate',
            compensation_action='invalidate',
            created_at=1000000
        ),
        SagaStep(
            step_id='step-2',
            name='build_artifact',
            action='build',
            compensation_action='delete_artifacts',
            created_at=1000000
        ),
    ]

    return SagaState(
        saga_id='saga-123',
        workflow_id='workflow-123',
        plan_id='plan-123',
        intent_id='intent-123',
        status=SagaStatus.STARTED,
        steps=steps,
        compensation_order=['step-2', 'step-1'],
        created_at=1000000,
        started_at=1001000,
        current_step_index=0
    )


@pytest.fixture
def mock_saga_producer():
    """Mock do SagaProducer."""
    producer = AsyncMock()
    producer.publish_saga_created = AsyncMock(return_value=True)
    producer.publish_saga_started = AsyncMock(return_value=True)
    producer.publish_saga_step_completed = AsyncMock(return_value=True)
    producer.publish_saga_step_failed = AsyncMock(return_value=True)
    producer.publish_saga_compensating = AsyncMock(return_value=True)
    producer.publish_saga_compensated = AsyncMock(return_value=True)
    producer.publish_saga_completed = AsyncMock(return_value=True)
    producer.publish_saga_failed = AsyncMock(return_value=True)
    return producer


# Import das activities para teste
from src.activities.saga_events import (
    publish_saga_created,
    publish_saga_started,
    publish_saga_completed,
    publish_saga_failed,
)


@pytest.mark.asyncio
class TestSagaEventsActivity:
    """Testes para activity de eventos de Saga."""

    async def test_publish_saga_created_success(self, mock_saga_producer):
        """Testa publicação bem-sucedida de evento saga.created."""
        with patch(
            'src.activities.saga_events.get_saga_producer',
            return_value=mock_saga_producer
        ):
            result = await publish_saga_created(
                saga_id='saga-123',
                workflow_id='workflow-123',
                plan_id='plan-123',
                intent_id='intent-123',
                steps_count=3,
                metadata={'tenant': 'acme'}
            )

        assert result['success'] is True
        assert result['saga_id'] == 'saga-123'
        assert result['workflow_id'] == 'workflow-123'
        mock_saga_producer.publish_saga_created.assert_called_once()

    async def test_publish_saga_started_success(self, mock_saga_producer):
        """Testa publicação bem-sucedida de evento saga.started."""
        with patch(
            'src.activities.saga_events.get_saga_producer',
            return_value=mock_saga_producer
        ):
            result = await publish_saga_started(
                saga_id='saga-123',
                workflow_id='workflow-123',
                plan_id='plan-123',
                steps_count=3
            )

        assert result['success'] is True
        assert result['saga_id'] == 'saga-123'
        mock_saga_producer.publish_saga_started.assert_called_once()

    async def test_publish_saga_completed_success(self, mock_saga_producer):
        """Testa publicação bem-sucedida de evento saga.completed."""
        with patch(
            'src.activities.saga_events.get_saga_producer',
            return_value=mock_saga_producer
        ):
            result = await publish_saga_completed(
                saga_id='saga-123',
                workflow_id='workflow-123',
                plan_id='plan-123',
                steps_completed=3
            )

        assert result['success'] is True
        assert result['saga_id'] == 'saga-123'
        mock_saga_producer.publish_saga_completed.assert_called_once()

    async def test_publish_saga_failed_success(self, mock_saga_producer):
        """Testa publicação bem-sucedida de evento saga.failed."""
        with patch(
            'src.activities.saga_events.get_saga_producer',
            return_value=mock_saga_producer
        ):
            result = await publish_saga_failed(
                saga_id='saga-123',
                workflow_id='workflow-123',
                plan_id='plan-123',
                error='Validation error',
                retry_count=1,
                max_retries=3
            )

        assert result['success'] is True
        assert result['saga_id'] == 'saga-123'
        mock_saga_producer.publish_saga_failed.assert_called_once()

    async def test_publish_saga_created_error_handling(self):
        """Testa tratamento de erro na publicação."""
        async def failing_init():
            raise Exception('Kafka connection failed')

        with patch(
            'src.activities.saga_events.get_saga_producer',
            side_effect=failing_init
        ):
            result = await publish_saga_created(
                saga_id='saga-123',
                workflow_id='workflow-123',
                plan_id='plan-123',
                intent_id='intent-123',
                steps_count=3
            )

        assert result['success'] is False
        assert result['saga_id'] == 'saga-123'
        assert 'error' in result


class TestSagaMetrics:
    """Testes para SagaMetrics."""

    def test_increment_counter(self):
        """Deve incrementar contador."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 1)
        metrics.increment('saga_created', 2)

        assert metrics.get_counter('saga_created') == 3

    def test_increment_with_tags(self):
        """Deve incrementar contador com tags."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 1, {'plan_id': 'plan-123'})
        metrics.increment('saga_created', 2, {'plan_id': 'plan-456'})

        assert metrics.get_counter('saga_created', {'plan_id': 'plan-123'}) == 1
        assert metrics.get_counter('saga_created', {'plan_id': 'plan-456'}) == 2
        # Default sem tags retorna 0 pois as operações foram com tags
        assert metrics.get_counter('saga_created') == 0

    def test_record_duration(self):
        """Deve registrar duracao."""
        metrics = SagaMetrics()

        metrics.record_duration('saga_execution', 100.0)
        metrics.record_duration('saga_execution', 200.0)
        metrics.record_duration('saga_execution', 150.0)

        stats = metrics.get_duration_stats('saga_execution')

        assert stats['count'] == 3
        assert stats['min'] == 100.0
        assert stats['max'] == 200.0
        assert stats['avg'] == 150.0

    def test_record_duration_with_tags(self):
        """Deve registrar duracao com tags."""
        metrics = SagaMetrics()

        metrics.record_duration('saga_execution', 100.0, {'plan_id': 'plan-123'})
        metrics.record_duration('saga_execution', 200.0, {'plan_id': 'plan-456'})

        stats_123 = metrics.get_duration_stats('saga_execution', {'plan_id': 'plan-123'})
        stats_456 = metrics.get_duration_stats('saga_execution', {'plan_id': 'plan-456'})

        assert stats_123['count'] == 1
        assert stats_123['avg'] == 100.0
        assert stats_456['count'] == 1
        assert stats_456['avg'] == 200.0

    def test_get_counters(self):
        """Deve retornar todos os contadores."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 5)
        metrics.increment('saga_completed', 3)
        metrics.increment('saga_failed', 1)

        counters = metrics.get_counters()

        assert counters['saga_created']['default'] == 5
        assert counters['saga_completed']['default'] == 3
        assert counters['saga_failed']['default'] == 1

    def test_reset_counters(self):
        """Deve resetar todos os contadores."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 5)
        metrics.record_duration('saga_execution', 100.0)

        metrics.reset_counters()

        assert metrics.get_counter('saga_created') == 0
        assert metrics.get_duration_stats('saga_execution')['count'] == 0

    def test_reset_single_counter(self):
        """Deve resetar contador especifico."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 5)
        metrics.increment('saga_completed', 3)

        metrics.reset_counter('saga_created')

        assert metrics.get_counter('saga_created') == 0
        assert metrics.get_counter('saga_completed') == 3

    def test_get_summary(self):
        """Deve retornar resumo das metricas."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 5)
        metrics.increment('saga_completed', 3)
        metrics.record_duration('saga_execution', 100.0)
        metrics.record_duration('saga_execution', 200.0)

        summary = metrics.get_summary()

        assert 'timestamp' in summary
        assert summary['counters']['saga_created'] == 5
        assert summary['counters']['saga_completed'] == 3
        assert summary['durations']['saga_execution']['count'] == 2
        assert summary['durations']['saga_execution']['avg'] == 150.0

    def test_enable_disable(self):
        """Deve habilitar/desabilitar coleta de metricas."""
        metrics = SagaMetrics()

        metrics.increment('saga_created', 5)
        assert metrics.get_counter('saga_created') == 5

        metrics.disable()
        metrics.increment('saga_created', 3)
        assert metrics.get_counter('saga_created') == 5  # Nao incrementou

        metrics.enable()
        metrics.increment('saga_created', 2)
        assert metrics.get_counter('saga_created') == 7  # Incrementou

    def test_get_saga_metrics_singleton(self):
        """Deve retornar instancia singleton."""
        # Reset singleton
        import src.saga.saga_metrics
        src.saga.saga_metrics._metrics = None

        metrics1 = get_saga_metrics()
        metrics2 = get_saga_metrics()

        assert metrics1 is metrics2

        metrics1.increment('saga_created', 5)
        assert metrics2.get_counter('saga_created') == 5


@pytest.mark.asyncio
class TestSagaTimer:
    """Testes para SagaTimer."""

    @pytest.mark.asyncio
    async def test_timer_records_duration(self):
        """Deve medir duracao de operacao."""
        metrics = SagaMetrics()

        # Criar timer diretamente com metrics ao inves de usar singleton
        from src.saga.saga_metrics import SagaTimer
        async with SagaTimer(metrics, 'test_operation', {'tag': 'value'}) as t:
            assert t._start_time is not None
            # Simular operacao
            await asyncio.sleep(0.01)

        stats = metrics.get_duration_stats('test_operation', {'tag': 'value'})
        assert stats['count'] == 1
        assert stats['min'] > 0  # Deve ter medido algum tempo

    @pytest.mark.asyncio
    async def test_timer_with_metrics_singleton(self):
        """Deve funcionar com singleton de metrics."""
        # Reset singleton
        import src.saga.saga_metrics
        src.saga.saga_metrics._metrics = None

        async with timer('singleton_test'):
            await asyncio.sleep(0.01)

        metrics = get_saga_metrics()
        stats = metrics.get_duration_stats('singleton_test')
        assert stats['count'] == 1


@pytest.mark.asyncio
class TestSagaProducerWithMetrics:
    """Testes de integração Producer + Metrics."""

    @pytest.mark.asyncio
    async def test_producer_registers_metrics_on_publish(self, sample_saga):
        """Deve registrar metricas quando publicar eventos."""
        from src.saga.saga_producer import SagaProducer

        # Criar mock settings
        mock_settings = MagicMock()
        mock_settings.kafka_bootstrap_servers = 'localhost:9092'
        mock_settings.kafka_saga_events_topic = 'saga.events'

        metrics = SagaMetrics()
        producer = SagaProducer(settings=mock_settings)
        producer._producer = AsyncMock()
        producer._producer.send_and_wait = AsyncMock()
        producer.set_metrics(metrics)

        # Publicar eventos
        await producer.publish_saga_created(sample_saga)
        await producer.publish_saga_started(sample_saga)
        await producer.publish_saga_step_completed(
            saga_id='saga-123',
            step_id='step-1',
            step_name='validate',
        )

        # Verificar metricas registradas (com as tags corretas)
        assert metrics.get_counter('saga_created', {'plan_id': 'plan-123'}) == 1
        assert metrics.get_counter('saga_started', {'plan_id': 'plan-123'}) == 1
        assert metrics.get_counter('step_completed', {'step_name': 'validate'}) == 1

    @pytest.mark.asyncio
    async def test_get_saga_producer_singleton(self):
        """Deve retornar singleton de producer."""
        # Reset singleton
        import src.saga.saga_producer
        src.saga.saga_producer._producer = None

        with patch('src.saga.saga_producer.AIOKafkaProducer') as mock_kafka:
            mock_producer_instance = AsyncMock()
            mock_producer_instance.start = AsyncMock()
            mock_kafka.return_value = mock_producer_instance

            with patch('src.saga.saga_producer.get_settings'):
                from src.saga.saga_producer import get_saga_producer

                producer1 = await get_saga_producer()
                producer2 = await get_saga_producer()

                assert producer1 is producer2
                mock_producer_instance.start.assert_called_once()
