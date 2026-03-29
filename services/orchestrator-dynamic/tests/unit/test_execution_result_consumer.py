"""
Unit tests para ExecutionResultConsumer.

Testa o consumer que processa execution.results e envia signals
para workflows Temporal, fechando o feedback loop de execução.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.consumers.execution_result_consumer import ExecutionResultConsumer


@pytest.fixture
def mock_config():
    """Config mock para testes."""
    config = MagicMock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.execution_result_consumer_group = "test-group"
    config.kafka_security_protocol = "PLAINTEXT"
    return config


@pytest.fixture
def mock_temporal_client():
    """Temporal client mock."""
    client = MagicMock()
    handle = MagicMock()
    handle.signal = AsyncMock()  # signal é async
    client.get_workflow_handle.return_value = handle
    return client


@pytest.fixture
def mock_redis_client():
    """Redis client mock."""
    redis = AsyncMock()
    return redis


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.execution_results_processed_total = MagicMock()
    metrics.execution_results_processed_total.labels.return_value = MagicMock()
    metrics.workflow_signals_sent_total = MagicMock()
    return metrics


@pytest.fixture
def consumer(mock_config, mock_temporal_client, mock_redis_client, mock_metrics):
    """Consumer instance para testes."""
    return ExecutionResultConsumer(
        config=mock_config,
        temporal_client=mock_temporal_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics
    )


class TestExecutionResultConsumerInitialization:
    """Testes de inicialização do consumer."""

    def test_consumer_initialization(self, consumer):
        """Consumer deve ter atributos corretos após criação."""
        assert consumer.config is not None
        assert consumer.temporal_client is not None
        assert consumer.redis_client is not None
        assert consumer.consumer is None  # Não inicializado automaticamente
        assert consumer.running is False


class TestWorkflowCache:
    """Testes de cache de workflow_id."""

    @pytest.mark.asyncio
    async def test_get_workflow_from_cache(self, consumer, mock_redis_client):
        """Deve recuperar workflow_id do cache Redis."""
        ticket_id = "ticket-123"
        plan_id = "plan-456"
        workflow_id = "workflow-789"

        # Mock Redis retorna workflow_id
        mock_redis_client.get.return_value = workflow_id

        result = await consumer._get_workflow_for_ticket(ticket_id, plan_id)

        assert result == workflow_id
        mock_redis_client.get.assert_called_once_with(
            f"workflow:by:ticket:{ticket_id}"
        )

    @pytest.mark.asyncio
    async def test_get_workflow_not_in_cache(self, consumer, mock_redis_client):
        """Deve retornar None quando workflow não está em cache."""
        ticket_id = "ticket-123"
        plan_id = "plan-456"

        # Mock Redis retorna None (não encontrado)
        mock_redis_client.get.return_value = None

        result = await consumer._get_workflow_for_ticket(ticket_id, plan_id)

        assert result is None
        mock_redis_client.get.assert_called_once_with(
            f"workflow:by:ticket:{ticket_id}"
        )

    @pytest.mark.asyncio
    async def test_get_workflow_redis_unavailable(self, consumer):
        """Deve retornar None quando Redis não está disponível."""
        consumer_without_redis = ExecutionResultConsumer(
            config=consumer.config,
            temporal_client=consumer.temporal_client,
            redis_client=None,
            metrics=None
        )

        result = await consumer_without_redis._get_workflow_for_ticket(
            "ticket-123",
            "plan-456"
        )

        assert result is None


class TestWorkflowSignal:
    """Testes de envio de signal para workflow Temporal."""

    @pytest.mark.asyncio
    async def test_send_signal_success(self, consumer, mock_temporal_client):
        """Deve enviar signal ticket_completed para workflow."""
        workflow_id = "workflow-789"
        ticket_id = "ticket-123"
        result = {
            'ticket_id': ticket_id,
            'status': 'COMPLETED',
            'result': {'success': True}
        }

        await consumer._send_workflow_signal(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            result=result
        )

        # Verificar que signal foi enviado
        mock_temporal_client.get_workflow_handle.assert_called_once_with(workflow_id)
        handle = mock_temporal_client.get_workflow_handle.return_value
        handle.signal.assert_called_once_with("ticket_completed", ticket_id=ticket_id, result=result)

    @pytest.mark.asyncio
    async def test_send_signal_with_metrics(self, consumer, mock_temporal_client, mock_metrics):
        """Deve registrar métrica ao enviar signal."""
        workflow_id = "workflow-789"
        ticket_id = "ticket-123"
        result = {'status': 'COMPLETED', 'result': {'success': True}}

        await consumer._send_workflow_signal(
            workflow_id=workflow_id,
            ticket_id=ticket_id,
            result=result
        )

        mock_metrics.workflow_signals_sent_total.inc.assert_called_once()


class TestResultDeserialization:
    """Testes de deserialização de mensagens."""

    def test_deserialize_json_success(self, consumer):
        """Deve deserializar mensagem JSON corretamente."""
        import json

        message = MagicMock()
        message.value = json.dumps({
            'ticket_id': 'ticket-123',
            'status': 'COMPLETED',
            'result': {'success': True}
        }).encode('utf-8')

        result = consumer._deserialize(message)

        assert result['ticket_id'] == 'ticket-123'
        assert result['status'] == 'COMPLETED'
        assert result['result']['success'] is True

    def test_deserialize_json_invalid(self, consumer):
        """Deve levantar erro para JSON inválido."""
        message = MagicMock()
        message.value = b'{"invalid json'

        with pytest.raises(ValueError, match="Failed to deserialize"):
            consumer._deserialize(message)


class TestResultProcessing:
    """Testes de processamento de resultados."""

    @pytest.mark.asyncio
    async def test_process_result_with_workflow_id_in_message(
        self, consumer, mock_temporal_client, mock_redis_client
    ):
        """Deve processar resultado quando workflow_id está na mensagem."""
        message = MagicMock()
        message.topic = "execution.results"
        message.partition = 0
        message.offset = 100

        import json
        message.value = json.dumps({
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-456',
            'workflow_id': 'workflow-789',  # Já na mensagem
            'status': 'COMPLETED',
            'result': {'success': True}
        }).encode('utf-8')

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, 'consumer', mock_consumer):
            await consumer._process_result(message)

        # Verificar signal enviado com workflow_id da mensagem
        mock_temporal_client.get_workflow_handle.assert_called_once_with('workflow-789')

    @pytest.mark.asyncio
    async def test_process_result_with_workflow_id_from_cache(
        self, consumer, mock_temporal_client, mock_redis_client
    ):
        """Deve recuperar workflow_id do cache quando não está na mensagem."""
        message = MagicMock()
        message.topic = "execution.results"
        message.partition = 0
        message.offset = 100

        import json
        message.value = json.dumps({
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-456',
            'workflow_id': None,  # Não está na mensagem
            'status': 'COMPLETED',
            'result': {'success': True}
        }).encode('utf-8')

        # Mock Redis retorna workflow_id
        mock_redis_client.get.return_value = 'workflow-789'

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, 'consumer', mock_consumer):
            await consumer._process_result(message)

        # Verificar que cache foi consultado
        mock_redis_client.get.assert_called_once_with(
            "workflow:by:ticket:ticket-123"
        )
        # Verificar signal enviado com workflow_id do cache
        mock_temporal_client.get_workflow_handle.assert_called_once_with('workflow-789')

    @pytest.mark.asyncio
    async def test_process_result_missing_workflow_id_logs_warning(
        self, consumer, mock_temporal_client, mock_redis_client
    ):
        """Deve logar warning quando workflow_id não encontrado e não enviar signal."""
        message = MagicMock()
        message.topic = "execution.results"
        message.partition = 0
        message.offset = 100

        import json
        message.value = json.dumps({
            'ticket_id': 'ticket-123',
            'plan_id': 'plan-456',
            'workflow_id': None,
            'status': 'COMPLETED',
            'result': {'success': True}
        }).encode('utf-8')

        # Mock Redis retorna None (não encontrado)
        mock_redis_client.get.return_value = None

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, 'consumer', mock_consumer):
            await consumer._process_result(message)

        # Não deve enviar signal Temporal
        mock_temporal_client.get_workflow_handle.assert_not_called()
        # Deve fazer commit mesmo assim
        mock_consumer.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_result_records_metrics(
        self, consumer, mock_temporal_client, mock_redis_client, mock_metrics
    ):
        """Deve registrar métricas de processamento."""
        message = MagicMock()
        message.topic = "execution.results"
        message.partition = 0
        message.offset = 100

        import json
        message.value = json.dumps({
            'ticket_id': 'ticket-123',
            'workflow_id': 'workflow-789',
            'status': 'COMPLETED',
            'result': {'success': True}
        }).encode('utf-8')

        mock_redis_client.get.return_value = 'workflow-789'
        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, 'consumer', mock_consumer):
            await consumer._process_result(message)

        # Verificar métrica registrada
        mock_metrics.execution_results_processed_total.labels.assert_called_once_with(status='COMPLETED')


class TestConsumerLifecycle:
    """Testes de ciclo de vida do consumer."""

    @pytest.mark.asyncio
    async def test_initialize_starts_consumer(self, consumer):
        """Initialize deve iniciar consumer Kafka."""
        with patch('src.consumers.execution_result_consumer.AIOKafkaConsumer') as mock_kafka:
            mock_kafka_instance = AsyncMock()
            mock_kafka.return_value = mock_kafka_instance
            mock_kafka_instance.start = AsyncMock()

            await consumer.initialize()

            assert consumer.consumer is not None
            mock_kafka_instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_stops_consumer(self, consumer):
        """Stop deve parar consumer gracefulmente."""
        with patch('src.consumers.execution_result_consumer.AIOKafkaConsumer') as mock_kafka:
            mock_kafka_instance = AsyncMock()
            mock_kafka_instance.stop = AsyncMock()

            consumer.consumer = mock_kafka_instance
            consumer.running = True

            await consumer.stop()

            assert consumer.running is False
            mock_kafka_instance.stop.assert_called_once()
