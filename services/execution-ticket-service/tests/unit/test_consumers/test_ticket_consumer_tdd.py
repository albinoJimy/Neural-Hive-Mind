"""
Testes TDD para Ticket Consumer - Fase RED

Testes escritos ANTES da implementação.
Seguem o ciclo RED-GREEN-REFACTOR.
"""
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4

import pytest

from src.consumers.ticket_consumer import TicketConsumer
from src.models import ExecutionTicket, TicketStatus


# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        kafka_bootstrap_servers='localhost:9092',
        kafka_consumer_group_id='test-consumer',
        kafka_auto_offset_reset='earliest',
        kafka_enable_auto_commit=False,
        kafka_tickets_topic='execution.tickets',
        kafka_schema_registry_url='http://localhost:8081',
        kafka_security_protocol='PLAINTEXT',
        kafka_sasl_mechanism=None,
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_ssl_ca_location=None,
        kafka_ssl_certificate_location=None,
        kafka_ssl_key_location=None,
        schemas_base_path='/schemas',
        redis_idempotency_ttl_seconds=604800,
    )


@pytest.fixture
def mock_metrics():
    """Métricas mockadas."""
    metrics = SimpleNamespace()
    metrics.duplicates_detected_total = MagicMock()
    metrics.duplicates_detected_total.labels = MagicMock(return_value=MagicMock(inc=lambda: None))
    metrics.idempotency_cache_hits_total = MagicMock()
    metrics.idempotency_cache_hits_total.inc = MagicMock()
    metrics.tickets_consumed_total = MagicMock()
    metrics.tickets_consumed_total.inc = MagicMock()
    metrics.kafka_messages_consumed_total = MagicMock()
    metrics.kafka_messages_consumed_total.inc = MagicMock()
    metrics.tickets_processing_errors_total = MagicMock()
    metrics.tickets_processing_errors_total.inc = MagicMock()
    return metrics


@pytest.fixture
def sample_ticket_dict():
    """Ticket de exemplo."""
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
        'priority': 'MEDIUM',
        'risk_band': 'MEDIUM',
        'sla': {'timeout_ms': 30000, 'deadline': None, 'max_retries': 3},
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


# ===== TESTES: Idempotency Check =====


class TestCheckIdempotency:
    """Testes do método _check_idempotency."""

    @pytest.mark.asyncio
    async def test_check_idempotency_duplicate_found(self, mock_settings, mock_metrics):
        """
        DADO: Um idempotency_key já processado
        QUANDO: Chamo _check_idempotency
        ENTÃO: Deve retornar o ticket_id existente
        """
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value='existing-ticket-123')

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._check_idempotency('key-123')

        assert result == 'existing-ticket-123'
        redis_client.get.assert_called_once_with('ticket:idempotency:key-123')

    @pytest.mark.asyncio
    async def test_check_idempotency_no_duplicate(self, mock_settings, mock_metrics):
        """
        DADO: Um idempotency_key novo
        QUANDO: Chamo _check_idempotency
        ENTÃO: Deve retornar None
        """
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._check_idempotency('key-123')

        assert result is None

    @pytest.mark.asyncio
    async def test_check_idempotency_no_redis_client(self, mock_settings, mock_metrics):
        """
        DADO: Redis client não disponível
        QUANDO: Chamo _check_idempotency
        ENTÃO: Deve retornar None (fail-open)
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: None
        )

        result = await consumer._check_idempotency('key-123')

        assert result is None

    @pytest.mark.asyncio
    async def test_check_idempotency_empty_key(self, mock_settings, mock_metrics):
        """
        DADO: Um idempotency_key vazio
        QUANDO: Chamo _check_idempotency
        ENTÃO: Deve retornar None
        """
        redis_client = AsyncMock()

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._check_idempotency('')

        assert result is None
        redis_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_idempotency_redis_error(self, mock_settings, mock_metrics):
        """
        DADO: Redis lança exceção
        QUANDO: Chamo _check_idempotency
        ENTÃO: Deve retornar None (fail-open)
        """
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(side_effect=Exception("Redis connection error"))

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._check_idempotency('key-123')

        assert result is None


# ===== TESTES: Mark Ticket Processed =====


class TestMarkTicketProcessed:
    """Testes do método _mark_ticket_processed."""

    @pytest.mark.asyncio
    async def test_mark_ticket_processed_success(self, mock_settings, mock_metrics):
        """
        DADO: Um ticket processado com sucesso
        QUANDO: Chamo _mark_ticket_processed
        ENTÃO: Deve marcar no Redis com TTL
        """
        redis_client = AsyncMock()
        redis_client.set = AsyncMock(return_value=True)

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._mark_ticket_processed('key-123', 'ticket-456')

        assert result is True
        redis_client.set.assert_called_once_with(
            'ticket:idempotency:key-123',
            'ticket-456',
            ex=604800
        )

    @pytest.mark.asyncio
    async def test_mark_ticket_processed_no_redis(self, mock_settings, mock_metrics):
        """
        DADO: Redis client não disponível
        QUANDO: Chamo _mark_ticket_processed
        ENTÃO: Deve retornar False
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: None
        )

        result = await consumer._mark_ticket_processed('key-123', 'ticket-456')

        assert result is False

    @pytest.mark.asyncio
    async def test_mark_ticket_processed_empty_key(self, mock_settings, mock_metrics):
        """
        DADO: Um idempotency_key vazio
        QUANDO: Chamo _mark_ticket_processed
        ENTÃO: Deve retornar False sem chamar Redis
        """
        redis_client = AsyncMock()

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._mark_ticket_processed('', 'ticket-456')

        assert result is False
        redis_client.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_ticket_processed_redis_error(self, mock_settings, mock_metrics):
        """
        DADO: Redis lança exceção ao marcar
        QUANDO: Chamo _mark_ticket_processed
        ENTÃO: Deve retornar False (mas não levantar exceção)
        """
        redis_client = AsyncMock()
        redis_client.set = AsyncMock(side_effect=Exception("Redis error"))

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: redis_client
        )

        result = await consumer._mark_ticket_processed('key-123', 'ticket-456')

        assert result is False


# ===== TESTES: Start/Stop =====


class TestConsumerStartStop:
    """Testes dos métodos start e stop."""

    @pytest.mark.asyncio
    async def test_start_initializes_consumer(self, mock_settings, mock_metrics):
        """
        DADO: Um TicketConsumer
        QUANDO: Chamo start
        ENTÃO: Deve inicializar o consumer Kafka
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics
        )

        with patch('src.consumers.ticket_consumer.Consumer') as mock_consumer_class, \
             patch('src.consumers.ticket_consumer.instrument_kafka_consumer') as mock_instrument:
            mock_consumer = MagicMock()
            mock_consumer_class.return_value = mock_consumer
            mock_instrument.return_value = mock_consumer
            mock_consumer.subscribe = MagicMock()

            await consumer.start()

        assert consumer.running is True
        mock_consumer.subscribe.assert_called_once_with(['execution.tickets'])

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, mock_settings, mock_metrics):
        """
        DADO: Um TicketConsumer rodando
        QUANDO: Chamo stop
        ENTÃO: Deve definir running=False e fechar consumer
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics
        )
        consumer.running = True
        consumer.consumer = MagicMock()

        await consumer.stop()

        assert consumer.running is False


# ===== TESTES: Properties =====


class TestConsumerProperties:
    """Testes das propriedades do consumer."""

    def test_webhook_manager_property(self, mock_settings, mock_metrics):
        """
        DADO: Um TicketConsumer com webhook_manager_getter
        QUANDO: Acesso webhook_manager
        ENTÃO: Deve chamar o getter
        """
        mock_webhook_manager = MagicMock()

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            webhook_manager_getter=lambda: mock_webhook_manager
        )

        assert consumer.webhook_manager == mock_webhook_manager

    def test_webhook_manager_property_no_getter(self, mock_settings, mock_metrics):
        """
        DADO: Um TicketConsumer sem webhook_manager_getter
        QUANDO: Acesso webhook_manager
        ENTÃO: Deve retornar None
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics
        )

        assert consumer.webhook_manager is None

    def test_redis_client_property(self, mock_settings, mock_metrics):
        """
        DADO: Um TicketConsumer com redis_client_getter
        QUANDO: Acesso redis_client
        ENTÃO: Deve chamar o getter
        """
        mock_redis = AsyncMock()

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics,
            redis_client_getter=lambda: mock_redis
        )

        assert consumer.redis_client == mock_redis

    def test_redis_client_property_no_getter(self, mock_settings, mock_metrics):
        """
        DADO: Um TicketConsumer sem redis_client_getter
        QUANDO: Acesso redis_client
        ENTÃO: Deve retornar None
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics
        )

        assert consumer.redis_client is None


# ===== TESTES: Constants =====


class TestConsumerConstants:
    """Testes das constantes da classe."""

    def test_idempotency_ttl_constant(self):
        """
        DADO: A classe TicketConsumer
        QUANDO: Verifico IDEMPOTENCY_TTL_SECONDS
        ENTÃO: Deve ser 604800 (7 dias)
        """
        assert TicketConsumer.IDEMPOTENCY_TTL_SECONDS == 604800


# ===== TESTES: Security Configuration =====


class TestConfigureSecurity:
    """Testes do método _configure_security."""

    def test_configure_security_plaintext(self, mock_settings, mock_metrics):
        """
        DADO: Settings com security_protocol=PLAINTEXT
        QUANDO: Chamo _configure_security
        ENTÃO: Deve retornar config com security.protocol apenas
        """
        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics
        )

        result = consumer._configure_security()

        assert 'security.protocol' in result
        assert result['security.protocol'] == 'PLAINTEXT'

    def test_configure_security_sasl_plain(self, mock_settings, mock_metrics):
        """
        DADO: Settings com SASL_PLAIN
        QUANDO: Chamo _configure_security
        ENTÃO: Deve incluir config SASL
        """
        mock_settings.kafka_security_protocol = 'SASL_PLAINTEXT'
        mock_settings.kafka_sasl_mechanism = 'PLAIN'
        mock_settings.kafka_sasl_username = 'user'
        mock_settings.kafka_sasl_password = 'pass'

        consumer = TicketConsumer(
            settings=mock_settings,
            metrics=mock_metrics
        )

        result = consumer._configure_security()

        assert result['security.protocol'] == 'SASL_PLAINTEXT'
        assert 'sasl.mechanism' in result
        assert result['sasl.mechanism'] == 'PLAIN'
        assert result['sasl.username'] == 'user'
        assert result['sasl.password'] == 'pass'
