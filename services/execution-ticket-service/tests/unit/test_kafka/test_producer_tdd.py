"""
Testes TDD para Kafka Producer.

Foca em comportamentos essenciais sem conectar ao Kafka real.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Mock Classes
# =============================================================================


class MockSettings:
    """Settings mockado."""

    def __init__(self):
        self.kafka_bootstrap_servers = "localhost:9092"
        self.kafka_tickets_topic = "execution.tickets"
        self.kafka_security_protocol = "PLAINTEXT"
        self.kafka_sasl_mechanism = "SCRAM-SHA-512"
        self.kafka_sasl_username = None
        self.kafka_sasl_password = None


class MockProducer:
    """AIOKafkaProducer mockado."""

    def __init__(self, **kwargs):
        self.started = False
        self.stopped = False
        self.config = kwargs
        self.messages = []

    async def start(self):
        """Mock start."""
        self.started = True

    async def stop(self):
        """Mock stop."""
        self.stopped = True
        self.started = False

    async def send_and_wait(self, topic, value=None, key=None):
        """Mock send_and_wait."""
        if not self.started:
            raise RuntimeError("Producer not started")
        self.messages.append({"topic": topic, "value": value, "key": key})
        return True


# =============================================================================
# Testes: KafkaTicketProducer Init
# =============================================================================


class TestKafkaTicketProducerInit:
    """Testes de inicialização do KafkaTicketProducer."""

    def test_initializes_with_none_producer(self):
        """KafkaTicketProducer inicia com producer None."""
        # Arrange & Act
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()):
            producer = KafkaTicketProducer()

            # Assert
            assert producer._producer is None

    def test_initializes_with_settings(self):
        """KafkaTicketProducer carrega settings."""
        # Arrange
        mock_settings = MockSettings()

        # Act
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=mock_settings):
            producer = KafkaTicketProducer()

            # Assert
            assert producer._topic == "execution.tickets"


# =============================================================================
# Testes: start
# =============================================================================


class TestKafkaProducerStart:
    """Testes do método start."""

    @pytest.mark.asyncio
    async def test_start_creates_producer(self):
        """start cria producer AIOKafka."""
        # Arrange
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=MockProducer()):

            producer = KafkaTicketProducer()

            # Act
            await producer.start()

            # Assert
            assert producer._producer is not None

    @pytest.mark.asyncio
    async def test_start_calls_producer_start(self):
        """start chama producer.start()."""
        # Arrange
        mock_producer = MockProducer()

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()

            # Act
            await producer.start()

            # Assert
            assert mock_producer.started is True

    @pytest.mark.asyncio
    async def test_start_retries_on_failure(self):
        """start retrya em caso de falha."""
        # Arrange
        mock_producer = MockProducer()
        call_count = 0

        async def failing_start(self):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection failed")
            self.started = True

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer), \
             patch.object(MockProducer, "start", failing_start):

            producer = KafkaTicketProducer()

            # Act
            await producer.start(max_retries=3, initial_delay=0.01)

            # Assert
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_start_raises_after_max_retries(self):
        """start raises RuntimeError após max_retries."""
        # Arrange
        mock_producer = MockProducer()

        async def always_fail(self):
            raise Exception("Always fails")

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer), \
             patch.object(MockProducer, "start", always_fail):

            producer = KafkaTicketProducer()

            # Act & Assert
            with pytest.raises(RuntimeError) as exc_info:
                await producer.start(max_retries=2, initial_delay=0.01)

            assert "Failed to start Kafka producer" in str(exc_info.value)


# =============================================================================
# Testes: stop
# =============================================================================


class TestKafkaProducerStop:
    """Testes do método stop."""

    @pytest.mark.asyncio
    async def test_stop_calls_producer_stop(self):
        """stop chama producer.stop()."""
        # Arrange
        mock_producer = MockProducer()
        mock_producer.started = True

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            # Act
            await producer.stop()

            # Assert
            assert mock_producer.stopped is True

    @pytest.mark.asyncio
    async def test_stop_sets_producer_to_none(self):
        """stop define producer como None."""
        # Arrange
        mock_producer = MockProducer()

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            # Act
            await producer.stop()

            # Assert
            assert producer._producer is None

    @pytest.mark.asyncio
    async def test_stop_with_none_producer(self):
        """stop não raises quando producer é None."""
        # Arrange
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()):
            producer = KafkaTicketProducer()
            producer._producer = None

            # Act & Assert - não deve raise
            await producer.stop()


# =============================================================================
# Testes: publish_ticket
# =============================================================================


class TestPublishTicket:
    """Testes do método publish_ticket."""

    @pytest.mark.asyncio
    async def test_publish_ticket_sends_to_kafka(self):
        """publish_ticket envia mensagem para Kafka."""
        # Arrange
        mock_producer = MockProducer()
        mock_producer.started = True

        ticket = {"ticket_id": "ticket-123", "plan_id": "plan-456"}

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            # Act
            result = await producer.publish_ticket(ticket)

            # Assert
            assert result is True
            assert len(mock_producer.messages) == 1
            assert mock_producer.messages[0]["value"] == ticket

    @pytest.mark.asyncio
    async def test_publish_ticket_uses_ticket_id_as_key(self):
        """publish_ticket usa ticket_id como key."""
        # Arrange
        mock_producer = MockProducer()
        mock_producer.started = True

        ticket = {"ticket_id": "ticket-123", "plan_id": "plan-456"}

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            # Act
            await producer.publish_ticket(ticket)

            # Assert
            assert mock_producer.messages[0]["key"] == "ticket-123"

    @pytest.mark.asyncio
    async def test_publish_ticket_returns_false_when_not_initialized(self):
        """publish_ticket retorna False quando producer não inicializado."""
        # Arrange
        ticket = {"ticket_id": "ticket-123"}

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()):
            producer = KafkaTicketProducer()
            producer._producer = None

            # Act
            result = await producer.publish_ticket(ticket)

            # Assert
            assert result is False

    @pytest.mark.asyncio
    async def test_publish_ticket_with_custom_key(self):
        """publish_ticket usa key customizada quando fornecida."""
        # Arrange
        mock_producer = MockProducer()
        mock_producer.started = True

        ticket = {"ticket_id": "ticket-123"}
        custom_key = "custom-key"

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            # Act
            await producer.publish_ticket(ticket, key=custom_key)

            # Assert
            assert mock_producer.messages[0]["key"] == custom_key


# =============================================================================
# Testes: health_check
# =============================================================================


class TestHealthCheck:
    """Testes do método health_check."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_producer_exists(self):
        """health_check retorna True quando producer existe."""
        # Arrange
        mock_producer = MockProducer()

        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            producer = KafkaTicketProducer()
            producer._producer = mock_producer

            # Act
            result = await producer.health_check()

            # Assert
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_producer_none(self):
        """health_check retorna False quando producer é None."""
        # Arrange
        from src.kafka.producer import KafkaTicketProducer

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()):
            producer = KafkaTicketProducer()
            producer._producer = None

            # Act
            result = await producer.health_check()

            # Assert
            assert result is False


# =============================================================================
# Testes: get_kafka_producer
# =============================================================================


class TestGetKafkaProducer:
    """Testes da função get_kafka_producer."""

    @pytest.mark.asyncio
    async def test_get_kafka_producer_creates_singleton(self):
        """get_kafka_producer cria singleton."""
        # Arrange
        mock_producer = MockProducer()

        from src.kafka import producer as producer_module

        # Reset global
        producer_module._producer = None

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            # Act
            p1 = await producer_module.get_kafka_producer()
            p2 = await producer_module.get_kafka_producer()

            # Assert
            assert p1 is p2

            # Cleanup
            producer_module._producer = None

    @pytest.mark.asyncio
    async def test_get_kafka_producer_starts_producer(self):
        """get_kafka_producer inicia o producer."""
        # Arrange
        mock_producer = MockProducer()

        from src.kafka import producer as producer_module

        # Reset global
        producer_module._producer = None

        with patch("src.kafka.producer.get_settings", return_value=MockSettings()), \
             patch("src.kafka.producer.AIOKafkaProducer", return_value=mock_producer):

            # Act
            await producer_module.get_kafka_producer()

            # Assert
            assert mock_producer.started is True

            # Cleanup
            producer_module._producer = None


# =============================================================================
# Testes: close_kafka_producer
# =============================================================================


class TestCloseKafkaProducer:
    """Testes da função close_kafka_producer."""

    @pytest.mark.asyncio
    async def test_close_kafka_producer_stops_producer(self):
        """close_kafka_producer para o producer."""
        # Arrange
        mock_producer = MockProducer()
        mock_producer.started = True

        from src.kafka import producer as producer_module

        producer_module._producer = mock_producer

        # Act
        await producer_module.close_kafka_producer()

        # Assert
        assert mock_producer.stopped is True
        assert producer_module._producer is None

    @pytest.mark.asyncio
    async def test_close_kafka_producer_with_none(self):
        """close_kafka_producer não raises quando _producer é None."""
        # Arrange
        from src.kafka import producer as producer_module

        producer_module._producer = None

        # Act & Assert - não deve raise
        await producer_module.close_kafka_producer()
