"""
Integration Tests para Kafka Producer - Execution Ticket Service

Testes de integração que usam Kafka real via Docker Compose.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.kafka.producer import KafkaTicketProducer


# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    settings = SimpleNamespace(
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='execution.tickets',
        kafka_security_protocol='PLAINTEXT',
        kafka_sasl_mechanism=None,
        kafka_sasl_username=None,
        kafka_sasl_password=None,
    )
    return settings


@pytest.fixture
def sample_ticket_dict():
    """Ticket de exemplo para publicação."""
    return {
        'ticket_id': str(uuid4()),
        'plan_id': str(uuid4()),
        'intent_id': str(uuid4()),
        'decision_id': str(uuid4()),
        'task_id': 'task-123',
        'task_type': 'BUILD',
        'description': 'Test ticket',
        'dependencies': [],
        'status': 'PENDING',
        'priority': 'NORMAL',
        'risk_band': 'medium',
        'sla': {'timeout_ms': 30000, 'deadline': 0, 'max_retries': 3},
        'qos': {
            'delivery_mode': 'AT_MOST_ONCE',
            'consistency': 'EVENTUAL',
            'durability': 'TRANSIENT'
        },
        'parameters': {},
        'required_capabilities': [],
        'security_level': 'INTERNAL',
        'created_at': 1714800000000,
        'started_at': None,
        'completed_at': None,
        'retry_count': 0,
        'error_message': None,
        'compensation_ticket_id': None,
        'metadata': {},
        'schema_version': 1
    }


# ===== TESTES: Initialization =====


class TestKafkaProducerInit:
    """Testes de inicialização do Kafka Producer."""

    def test_init_creates_producer(self, mock_settings):
        """
        DADO: Configurações válidas
        QUANDO: Crio KafkaTicketProducer
        ENTÃO: Deve inicializar corretamente
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings):

            producer = KafkaTicketProducer()

        assert producer._producer is None
        assert producer._topic == 'execution.tickets'


# ===== TESTES: Start/Stop =====


class TestKafkaProducerStartStop:
    """Testes dos métodos start e stop."""

    @pytest.mark.asyncio
    async def test_start_creates_aiokafka_producer(self, mock_settings):
        """
        DADO: Um KafkaTicketProducer
        QUANDO: Chamo start
        ENTÃO: Deve criar o AIOKafkaProducer
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class:

            mock_producer = AsyncMock()
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()
            await producer.start()

        assert producer._producer is not None

    @pytest.mark.asyncio
    async def test_stop_stops_producer(self, mock_settings):
        """
        DADO: Um producer rodando
        QUANDO: Chamo stop
        ENTÃO: Deve parar o producer
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class:

            mock_producer = AsyncMock()
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            await producer.stop()

        mock_producer.stop.assert_called_once()


# ===== TESTES: Publish Operations =====


class TestKafkaProducerPublish:
    """Testes de publicação de mensagens."""

    @pytest.mark.asyncio
    async def test_publish_ticket_success(self, mock_settings):
        """
        DADO: Um producer rodando com ticket válido
        QUANDO: Chamo publish_ticket
        ENTÃO: Deve publicar mensagem no Kafka
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class:

            mock_producer = AsyncMock()
            mock_producer.send_and_wait = AsyncMock(return_value=None)
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            ticket_data = {'ticket_id': 'test-123', 'status': 'PENDING'}
            result = await producer.publish_ticket(ticket_data)

        assert result is True
        mock_producer.send_and_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_ticket_no_producer(self, mock_settings):
        """
        DADO: Producer não inicializado
        QUANDO: Chamo publish_ticket
        ENTÃO: Deve retornar False
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings):
            producer = KafkaTicketProducer()
            producer._producer = None

            ticket_data = {'ticket_id': 'test-123', 'status': 'PENDING'}
            result = await producer.publish_ticket(ticket_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_ticket_with_timeout(self, mock_settings):
        """
        DADO: Producer rodando
        QUANDO: publish_ticket com timeout curto
        ENTÃO: Deve retornar False após timeout
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class:

            mock_producer = AsyncMock()
            mock_producer.send_and_wait = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            ticket_data = {'ticket_id': 'test-123', 'status': 'PENDING'}
            result = await producer.publish_ticket(ticket_data, timeout_ms=100)

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_ticket_with_key(self, mock_settings):
        """
        DADO: Ticket com key específica
        QUANDO: Chamo publish_ticket com key
        ENTÃO: Deve usar a key fornecida
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class:

            mock_producer = AsyncMock()
            mock_producer.send_and_wait = AsyncMock(return_value=None)
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            ticket_data = {'ticket_id': 'test-123', 'status': 'PENDING'}
            await producer.publish_ticket(ticket_data, key='custom-key')

        # Verificar que send_and_wait foi chamado com key='custom-key'
        mock_producer.send_and_wait.assert_called_once()
        call_args = mock_producer.send_and_wait.call_args
        assert call_args[1]['key'] == 'custom-key'


# ===== TESTES: Health Check =====


class TestKafkaProducerHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_with_producer(self, mock_settings):
        """
        DADO: Producer inicializado
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar True
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class:

            mock_producer = AsyncMock()
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            result = await producer.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_without_producer(self, mock_settings):
        """
        DADO: Producer não inicializado
        QUANDO: Chamo health_check
        ENTÃO: Deve retornar False
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings):
            producer = KafkaTicketProducer()
            producer._producer = None

            result = await producer.health_check()

        assert result is False


# ===== TESTES: Error Handling =====


class TestKafkaProducerErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_start_exhausts_retries(self, mock_settings):
        """
        DADO: Kafka sempre falhando
        QUANDO: Chamo start com max_retries
        ENTÃO: Deve levantar RuntimeError após exaurir tentativas
        """
        with patch('src.kafka.producer.get_settings', return_value=mock_settings), \
             patch('src.kafka.producer.AIOKafkaProducer') as mock_producer_class, \
             patch('asyncio.sleep') as mock_sleep:

            mock_producer = AsyncMock()
            mock_producer.start = AsyncMock(side_effect=Exception("Always failing"))
            mock_producer_class.return_value = mock_producer

            producer = KafkaTicketProducer()

            with pytest.raises(RuntimeError, match="Failed to start Kafka producer"):
                await producer.start(max_retries=2, initial_delay=0.01)

