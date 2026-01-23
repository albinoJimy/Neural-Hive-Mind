import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock


@pytest.fixture
def mock_config():
    config = Mock()
    config.kafka_bootstrap_servers = 'localhost:9092'
    config.kafka_consumer_group_id = 'test-group'
    config.kafka_tickets_topic = 'execution.tickets'
    config.kafka_dlq_topic = 'execution.tickets.dlq'
    config.kafka_max_retries_before_dlq = 3
    config.kafka_auto_offset_reset = 'earliest'
    config.kafka_security_protocol = 'PLAINTEXT'
    config.kafka_sasl_mechanism = None
    config.kafka_sasl_username = None
    config.kafka_sasl_password = None
    config.schemas_base_path = '/app/schemas'
    config.supported_task_types = ['BUILD', 'DEPLOY', 'TEST']
    return config


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_execution_engine():
    engine = AsyncMock()
    engine.process_ticket = AsyncMock(side_effect=Exception("Processing failed"))
    return engine


@pytest.fixture
def mock_metrics():
    metrics = Mock()
    metrics.kafka_consumer_initialized_total = Mock()
    metrics.kafka_consumer_initialized_total.inc = Mock()
    metrics.tickets_consumed_total = Mock()
    metrics.tickets_consumed_total.labels = Mock(return_value=Mock(inc=Mock()))
    metrics.kafka_consumer_errors_total = Mock()
    metrics.kafka_consumer_errors_total.labels = Mock(return_value=Mock(inc=Mock()))
    metrics.dlq_messages_total = Mock()
    metrics.dlq_messages_total.labels = Mock(return_value=Mock(inc=Mock()))
    metrics.dlq_publish_duration_seconds = Mock()
    metrics.dlq_publish_duration_seconds.observe = Mock()
    metrics.dlq_publish_errors_total = Mock()
    metrics.dlq_publish_errors_total.labels = Mock(return_value=Mock(inc=Mock()))
    metrics.ticket_retry_count = Mock()
    metrics.ticket_retry_count.labels = Mock(return_value=Mock(observe=Mock()))
    return metrics


class TestKafkaTicketConsumerDLQ:
    """Testes para logica de DLQ no KafkaTicketConsumer"""

    @pytest.mark.asyncio
    async def test_retry_count_incremented_on_failure(self, mock_config, mock_redis, mock_metrics):
        """Testar que retry count e incrementado apos falha"""
        from src.clients.kafka_ticket_consumer import KafkaTicketConsumer

        mock_engine = AsyncMock()
        mock_engine.process_ticket = AsyncMock(side_effect=Exception("Test error"))

        consumer = KafkaTicketConsumer(
            config=mock_config,
            execution_engine=mock_engine,
            metrics=mock_metrics
        )
        consumer.redis_client = mock_redis

        # Simular incremento
        result = await consumer._increment_retry_count('test-ticket-123')

        assert result == 1
        mock_redis.incr.assert_called_once_with('ticket:retry_count:test-ticket-123')
        mock_redis.expire.assert_called_once_with('ticket:retry_count:test-ticket-123', 604800)

    @pytest.mark.asyncio
    async def test_retry_count_cleared_on_success(self, mock_config, mock_redis, mock_metrics):
        """Testar que retry count e limpo apos sucesso"""
        from src.clients.kafka_ticket_consumer import KafkaTicketConsumer

        mock_engine = AsyncMock()

        consumer = KafkaTicketConsumer(
            config=mock_config,
            execution_engine=mock_engine,
            metrics=mock_metrics
        )
        consumer.redis_client = mock_redis

        await consumer._clear_retry_count('test-ticket-456')

        mock_redis.delete.assert_called_once_with('ticket:retry_count:test-ticket-456')

    @pytest.mark.asyncio
    async def test_fail_open_when_redis_unavailable(self, mock_config, mock_metrics):
        """Testar fail-open quando Redis falha"""
        from src.clients.kafka_ticket_consumer import KafkaTicketConsumer

        mock_engine = AsyncMock()

        consumer = KafkaTicketConsumer(
            config=mock_config,
            execution_engine=mock_engine,
            metrics=mock_metrics
        )
        consumer.redis_client = None  # Redis indisponivel

        # Nao deve lancar excecao
        count = await consumer._get_retry_count('test-ticket-999')
        assert count == 0

        count = await consumer._increment_retry_count('test-ticket-999')
        assert count == 1

    @pytest.mark.asyncio
    async def test_publish_to_dlq_on_max_retries(self, mock_config, mock_redis, mock_metrics):
        """Testar publicacao no DLQ apos max retries"""
        from src.clients.kafka_ticket_consumer import KafkaTicketConsumer

        mock_engine = AsyncMock()

        consumer = KafkaTicketConsumer(
            config=mock_config,
            execution_engine=mock_engine,
            metrics=mock_metrics
        )
        consumer.redis_client = mock_redis

        ticket = {
            'ticket_id': 'test-ticket-dlq',
            'task_type': 'BUILD',
            'status': 'PENDING',
            'dependencies': []
        }
        error = Exception("Max retries exceeded")

        with patch('confluent_kafka.Producer') as MockProducer:
            mock_producer_instance = MagicMock()
            MockProducer.return_value = mock_producer_instance

            await consumer._publish_to_dlq(ticket, error, 3)

            # Verificar que producer.produce foi chamado
            mock_producer_instance.produce.assert_called_once()
            call_args = mock_producer_instance.produce.call_args

            assert call_args.kwargs['topic'] == 'execution.tickets.dlq'
            assert call_args.kwargs['key'] == b'test-ticket-dlq'

            # Verificar payload
            payload = json.loads(call_args.kwargs['value'].decode('utf-8'))
            assert payload['ticket_id'] == 'test-ticket-dlq'
            assert 'dlq_metadata' in payload
            assert payload['dlq_metadata']['retry_count'] == 3
            assert payload['dlq_metadata']['error_type'] == 'Exception'


class TestKafkaDLQConsumer:
    """Testes para KafkaDLQConsumer"""

    @pytest.mark.asyncio
    async def test_dlq_consumer_persists_message(self, mock_config):
        """Testar que DLQ consumer persiste mensagem no MongoDB"""
        from src.clients.kafka_dlq_consumer import KafkaDLQConsumer

        mock_mongodb = AsyncMock()
        mock_collection = AsyncMock()
        mock_mongodb.db = {'execution_tickets_dlq': mock_collection}

        dlq_consumer = KafkaDLQConsumer(
            config=mock_config,
            mongodb_client=mock_mongodb,
            alert_manager=None
        )

        dlq_message = {
            'ticket_id': 'test-ticket-789',
            'task_type': 'DEPLOY',
            'dlq_metadata': {
                'original_error': 'Connection timeout',
                'error_type': 'TimeoutError',
                'retry_count': 3
            }
        }

        await dlq_consumer._persist_dlq_message(dlq_message)

        mock_collection.insert_one.assert_called_once()
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args['ticket_id'] == 'test-ticket-789'
        assert 'processed_at' in call_args
        assert 'processed_at_ms' in call_args

    @pytest.mark.asyncio
    async def test_dlq_consumer_sends_alert(self, mock_config):
        """Testar que DLQ consumer envia alerta"""
        from src.clients.kafka_dlq_consumer import KafkaDLQConsumer

        mock_alert_manager = AsyncMock()

        dlq_consumer = KafkaDLQConsumer(
            config=mock_config,
            mongodb_client=None,
            alert_manager=mock_alert_manager
        )

        dlq_message = {
            'ticket_id': 'test-ticket-alert',
            'task_type': 'TEST',
            'dlq_metadata': {
                'original_error': 'Test failed',
                'error_type': 'AssertionError',
                'retry_count': 3
            }
        }

        await dlq_consumer._alert_sre(dlq_message)

        mock_alert_manager.send_alert.assert_called_once()
        alert_payload = mock_alert_manager.send_alert.call_args[0][0]
        assert alert_payload['ticket_id'] == 'test-ticket-alert'
        assert alert_payload['severity'] == 'warning'
        assert alert_payload['component'] == 'worker-agents'
        assert 'runbook_url' in alert_payload

    @pytest.mark.asyncio
    async def test_dlq_consumer_handles_missing_mongodb(self, mock_config):
        """Testar que DLQ consumer lida com MongoDB indisponivel"""
        from src.clients.kafka_dlq_consumer import KafkaDLQConsumer

        dlq_consumer = KafkaDLQConsumer(
            config=mock_config,
            mongodb_client=None,  # MongoDB indisponivel
            alert_manager=None
        )

        dlq_message = {
            'ticket_id': 'test-ticket-no-mongo',
            'task_type': 'BUILD',
            'dlq_metadata': {}
        }

        # Nao deve lancar excecao
        await dlq_consumer._persist_dlq_message(dlq_message)


class TestDLQMetrics:
    """Testes para metricas de DLQ"""

    @pytest.mark.asyncio
    async def test_dlq_metrics_recorded(self, mock_config, mock_redis, mock_metrics):
        """Testar que metricas sao registradas ao publicar no DLQ"""
        from src.clients.kafka_ticket_consumer import KafkaTicketConsumer

        mock_engine = AsyncMock()

        consumer = KafkaTicketConsumer(
            config=mock_config,
            execution_engine=mock_engine,
            metrics=mock_metrics
        )
        consumer.redis_client = mock_redis

        ticket = {
            'ticket_id': 'test-metrics',
            'task_type': 'VALIDATE',
            'status': 'PENDING'
        }
        error = Exception("Validation failed")

        with patch('confluent_kafka.Producer') as MockProducer:
            mock_producer_instance = MagicMock()
            MockProducer.return_value = mock_producer_instance

            await consumer._publish_to_dlq(ticket, error, 3)

            # Verificar metricas
            mock_metrics.dlq_messages_total.labels.assert_called_with(
                reason='max_retries_exceeded',
                task_type='VALIDATE'
            )
            mock_metrics.dlq_publish_duration_seconds.observe.assert_called_once()
            mock_metrics.ticket_retry_count.labels.assert_called_with(task_type='VALIDATE')
