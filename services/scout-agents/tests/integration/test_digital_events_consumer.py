"""
Testes de integração para DigitalEventsConsumer.

TDD: Testes escritos antes da implementação.
Epic: CR-02 Implementar Scout Consumer Completo
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import ConsumerRecord, TopicPartition

from src.models.digital_event import DigitalEvent, DigitalEventType, DigitalChannel
from src.consumers.digital_events_consumer import DigitalEventsConsumer


class TestDigitalEventModel:
    """Testes do modelo DigitalEvent."""

    def test_digital_event_creation(self):
        """Testa criação de evento digital com todos os campos."""
        event = DigitalEvent(
            event_id="evt-001",
            event_type=DigitalEventType.PAGE_VIEW,
            channel=DigitalChannel.WEB,
            user_id="user-123",
            session_id="session-456",
            timestamp=datetime.now(timezone.utc),
            payload={"url": "/home", "referrer": "google"},
            metadata={"ip": "192.168.1.1"},
        )

        assert event.event_id == "evt-001"
        assert event.event_type == DigitalEventType.PAGE_VIEW
        assert event.channel == DigitalChannel.WEB
        assert event.user_id == "user-123"
        assert event.session_id == "session-456"
        assert event.payload["url"] == "/home"
        assert event.metadata["ip"] == "192.168.1.1"

    def test_digital_event_with_defaults(self):
        """Testa criação de evento com valores padrão."""
        event = DigitalEvent(
            event_id="evt-002",
            event_type=DigitalEventType.CLICK,
            channel=DigitalChannel.MOBILE_APP,
            payload={"button": "submit"},
        )

        assert event.user_id is None
        assert event.session_id is None
        assert event.payload["button"] == "submit"
        assert event.metadata == {}
        assert isinstance(event.timestamp, datetime)

    def test_digital_event_channel_enum(self):
        """Testa enum de canais digitais."""
        assert DigitalChannel.WEB == "web"
        assert DigitalChannel.MOBILE_APP == "mobile_app"
        assert DigitalChannel.API == "api"
        assert DigitalChannel.EMAIL == "email"
        assert DigitalChannel.CHAT == "chat"
        assert DigitalChannel.SOCIAL == "social"

    def test_digital_event_type_enum(self):
        """Testa enum de tipos de evento."""
        assert DigitalEventType.PAGE_VIEW == "page_view"
        assert DigitalEventType.CLICK == "click"
        assert DigitalEventType.SUBMIT == "submit"
        assert DigitalEventType.SEARCH == "search"
        assert DigitalEventType.TRANSACTION == "transaction"
        assert DigitalEventType.ERROR == "error"
        assert DigitalEventType.CUSTOM == "custom"

    def test_digital_event_serialization(self):
        """Testa serialização para JSON."""
        event = DigitalEvent(
            event_id="evt-003",
            event_type=DigitalEventType.SEARCH,
            channel=DigitalChannel.API,
            user_id="user-search",
            payload={"query": "test"},
        )

        event_dict = event.model_dump()

        assert event_dict["event_id"] == "evt-003"
        assert event_dict["event_type"] == "search"
        assert event_dict["channel"] == "api"
        assert event_dict["user_id"] == "user-search"

    def test_digital_event_deserialization(self):
        """Testa desserialização de JSON."""
        data = {
            "event_id": "evt-004",
            "event_type": "transaction",
            "channel": "web",
            "user_id": "user-trans",
            "timestamp": "2026-03-31T12:00:00Z",
            "payload": {"amount": 100},
            "metadata": {"source": "checkout"},
        }

        event = DigitalEvent(**data)

        assert event.event_id == "evt-004"
        assert event.event_type == DigitalEventType.TRANSACTION
        assert event.channel == DigitalChannel.WEB


class TestDigitalEventsConsumerInitialization:
    """Testes de inicialização do DigitalEventsConsumer."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings para testes."""
        settings = Mock()
        settings.kafka.bootstrap_servers = "localhost:9092"
        settings.kafka.consumer_group_id = "scout-agents-dev"
        settings.kafka.topics_digital_events = "digital.events"
        settings.kafka.enable_auto_commit = False
        return settings

    @pytest.fixture
    def mock_exploration_engine(self):
        """Mock exploration engine."""
        engine = AsyncMock()
        engine.process_digital_event = AsyncMock(return_value=None)
        return engine

    @pytest.fixture
    def mock_metrics(self):
        """Mock metrics."""
        metrics = Mock()
        metrics.digital_events_consumed_total = Mock()
        metrics.digital_events_consumed_total.labels = Mock(
            return_value=metrics.digital_events_consumed_total
        )
        metrics.digital_events_consumed_total.inc = Mock()
        return metrics

    def test_consumer_initialization(self, mock_settings, mock_exploration_engine, mock_metrics):
        """Testa inicialização do consumer."""
        consumer = DigitalEventsConsumer(
            settings=mock_settings, exploration_engine=mock_exploration_engine, metrics=mock_metrics
        )

        assert consumer is not None
        assert consumer.settings == mock_settings
        assert consumer.exploration_engine == mock_exploration_engine
        assert consumer.metrics == mock_metrics
        assert consumer.running is False

    def test_consumer_without_optional_params(self, mock_settings):
        """Testa inicialização sem parâmetros opcionais."""
        consumer = DigitalEventsConsumer(settings=mock_settings)

        assert consumer.exploration_engine is None
        assert consumer.metrics is None


class TestDigitalEventsConsumerStartStop:
    """Testes de start e stop do consumer."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings para testes."""
        settings = Mock()
        settings.kafka.bootstrap_servers = "localhost:9092"
        settings.kafka.consumer_group_id = "scout-agents-dev"
        settings.kafka.topics_digital_events = "digital.events"
        return settings

    @pytest.fixture
    def consumer(self, mock_settings):
        """Consumer instance para testes."""
        from src.consumers.digital_events_consumer import DigitalEventsConsumer

        return DigitalEventsConsumer(settings=mock_settings)

    @pytest.mark.asyncio
    async def test_initialize_creates_kafka_consumer(self, consumer, mock_settings):
        """Testa que initialize cria o consumer Kafka corretamente."""
        with patch("src.consumers.digital_events_consumer.AIOKafkaConsumer") as mock_kafka_class:
            mock_consumer = AsyncMock()
            mock_kafka_class.return_value = mock_consumer

            await consumer.initialize()

            mock_kafka_class.assert_called_once()
            call_args = mock_kafka_class.call_args

            assert call_args[0][0] == mock_settings.kafka.topics_digital_events
            assert call_args[1]["bootstrap_servers"] == mock_settings.kafka.bootstrap_servers
            assert call_args[1]["group_id"] == mock_settings.kafka.consumer_group_id + "-digital"

    @pytest.mark.asyncio
    async def test_initialize_starts_consumer(self, consumer):
        """Testa que initialize inicia o consumer Kafka."""
        with patch("src.consumers.digital_events_consumer.AIOKafkaConsumer") as mock_kafka_class:
            mock_consumer = AsyncMock()
            mock_kafka_class.return_value = mock_consumer

            await consumer.initialize()

            mock_consumer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_sets_running_flag(self, consumer):
        """Testa que stop define running como False."""
        consumer.running = True
        consumer.consumer = AsyncMock()

        await consumer.stop()

        assert consumer.running is False

    @pytest.mark.asyncio
    async def test_stop_stops_kafka_consumer(self, consumer):
        """Testa que stop para o consumer Kafka."""
        consumer.consumer = AsyncMock()

        await consumer.stop()

        consumer.consumer.stop.assert_called_once()


class TestDigitalEventsConsumerProcessing:
    """Testes de processamento de eventos digitais."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings para testes."""
        settings = Mock()
        settings.kafka.bootstrap_servers = "localhost:9092"
        settings.kafka.consumer_group_id = "scout-agents-dev"
        settings.kafka.topics_digital_events = "digital.events"
        return settings

    @pytest.fixture
    def mock_exploration_engine(self):
        """Mock exploration engine."""
        engine = AsyncMock()
        engine.process_digital_event = AsyncMock(return_value=None)
        return engine

    @pytest.fixture
    def consumer(self, mock_settings, mock_exploration_engine):
        """Consumer instance para testes."""
        return DigitalEventsConsumer(
            settings=mock_settings, exploration_engine=mock_exploration_engine
        )

    def test_deserialize_event_valid_json(self, consumer):
        """Testa desserialização de JSON válido."""
        event_data = {
            "event_id": "evt-001",
            "event_type": "page_view",
            "channel": "web",
            "payload": {"url": "/home"},
        }

        result = consumer._deserialize_event(json.dumps(event_data))

        assert isinstance(result, DigitalEvent)
        assert result.event_id == "evt-001"
        assert result.event_type == DigitalEventType.PAGE_VIEW

    def test_deserialize_event_invalid_json(self, consumer):
        """Testa desserialização de JSON inválido."""
        result = consumer._deserialize_event("invalid json")

        assert result is None

    def test_deserialize_event_missing_fields(self, consumer):
        """Testa desserialização com campos obrigatórios faltando."""
        event_data = {
            "event_type": "page_view"
            # Missing event_id
        }

        result = consumer._deserialize_event(json.dumps(event_data))

        assert result is None

    @pytest.mark.asyncio
    async def test_process_message_calls_engine_callback(self, consumer, mock_exploration_engine):
        """Testa que process_message chama o callback da engine."""
        event_data = {
            "event_id": "evt-002",
            "event_type": "click",
            "channel": "mobile_app",
            "payload": {"element": "button"},
        }

        message = Mock()
        message.value = json.dumps(event_data)
        message.headers = []
        message.topic = "digital.events"
        message.partition = 0
        message.offset = 100

        await consumer._process_message(message)

        mock_exploration_engine.process_digital_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_records_metrics(self, consumer, mock_exploration_engine):
        """Testa que process_message registra métricas."""
        from src.observability import metrics

        # Criar mock para o contador
        mock_counter = Mock()
        mock_counter.labels = Mock(return_value=mock_counter)
        mock_counter.inc = Mock()

        # Configurar consumer com o mock de metrics
        consumer.metrics = Mock()
        consumer.metrics.digital_events_consumed_total = mock_counter

        event_data = {
            "event_id": "evt-003",
            "event_type": "submit",
            "channel": "api",
            "payload": {},
        }

        message = Mock()
        message.value = json.dumps(event_data)
        message.headers = []
        message.topic = "digital.events"
        message.partition = 0
        message.offset = 101

        await consumer._process_message(message)

        # Verificar que as métricas foram registradas
        mock_counter.labels.assert_called_once()
        mock_counter.inc.assert_called_once()


class TestDigitalEventsConsumerEndToEnd:
    """Testes de integração end-to-end."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings para testes."""
        settings = Mock()
        settings.kafka.bootstrap_servers = "localhost:9092"
        settings.kafka.consumer_group_id = "scout-agents-dev"
        settings.kafka.topics_digital_events = "digital.events"
        return settings

    @pytest.mark.asyncio
    async def test_consumer_full_lifecycle(self, mock_settings):
        """Testa ciclo de vida completo do consumer."""
        engine = AsyncMock()

        consumer = DigitalEventsConsumer(settings=mock_settings, exploration_engine=engine)

        # Initialize
        with patch("src.consumers.digital_events_consumer.AIOKafkaConsumer") as mock_kafka_class:
            mock_consumer = AsyncMock()
            mock_kafka_class.return_value = mock_consumer

            await consumer.initialize()
            assert consumer.consumer is not None

        # Stop
        await consumer.stop()
        assert consumer.running is False

    @pytest.mark.asyncio
    async def test_consumer_with_kafka_testcontainers(self, mock_settings):
        """Teste de integração com Kafka (requer testcontainers)."""
        pytest.skip("Requer Kafka running - executar em ambiente de teste com Docker")
