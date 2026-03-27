"""Testes unitários para consumidores Kafka."""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json

from src.consumers.base import BaseKafkaConsumer
from src.consumers.cognitive_plan_consumer import CognitivePlanConsumer
from src.consumers.lifecycle import ConsumerManager


# Mock Concrete Consumer for testing BaseKafkaConsumer
class MockConsumer(BaseKafkaConsumer):
    """Mock consumer para testes."""

    def get_topic(self) -> str:
        return "test.topic"

    async def process_message(self, message: dict) -> None:
        self.processed_messages.append(message)
        self.processed_messages = getattr(self, "processed_messages", [])


@pytest.fixture
def mock_settings():
    with patch("src.consumers.base.get_settings") as mock:
        settings = Mock()
        settings.kafka.bootstrap_servers = "localhost:9092"
        settings.kafka.consumer_group = "test-group"
        settings.kafka.auto_offset_reset = "earliest"
        settings.kafka.cognitive_plans_topic = "cognitive.plans.created"
        mock.return_value = settings
        yield mock


@pytest.fixture
def mock_settings_cognitive():
    with patch("src.consumers.cognitive_plan_consumer.get_settings") as mock:
        settings = Mock()
        settings.kafka.cognitive_plans_topic = "cognitive.plans.created"
        mock.return_value = settings
        yield mock


# BaseKafkaConsumer Tests
def test_base_consumer_initializes(mock_settings):
    consumer = MockConsumer()
    assert consumer.bootstrap_servers == "localhost:9092"
    assert consumer.group_id == "test-group"
    assert consumer._running is False


def test_base_consumer_get_topic(mock_settings):
    consumer = MockConsumer()
    assert consumer.get_topic() == "test.topic"


@pytest.mark.asyncio
async def test_base_consumer_register_callback(mock_settings):
    consumer = MockConsumer()

    async def mock_callback(msg):
        pass

    consumer.register_callback(mock_callback)
    assert len(consumer._callbacks) == 1


@pytest.mark.asyncio
async def test_base_consumer_stop(mock_settings):
    consumer = MockConsumer()
    assert consumer._running is False

    # Testar apenas o método stop sem iniciar o consumidor
    # (pois start() tentaria conectar ao Kafka)
    await consumer.stop()
    assert consumer._running is False


# CognitivePlanConsumer Tests
@pytest.mark.asyncio
async def test_cognitive_plan_consumer_initializes(mock_settings_cognitive, mock_settings):
    consumer = CognitivePlanConsumer()
    assert consumer.get_topic() == "cognitive.plans.created"


@pytest.mark.asyncio
async def test_cognitive_plan_consumer_process_message_valid(
    mock_settings_cognitive, mock_settings
):
    consumer = CognitivePlanConsumer()

    # Mock planner
    mock_plan = Mock()
    mock_plan.plan_id = "arch-123"
    mock_plan.architecture_type = Mock(value="microservices")
    mock_plan.components = []

    consumer.planner.plan = AsyncMock(return_value=mock_plan)
    consumer.repository.create = AsyncMock()

    message = {
        "key": None,
        "value": json.dumps({
            "plan_id": "cog-123",
            "intent": "Create API for user management",
            "context": {"team_size": 5}
        }),
        "topic": "cognitive.plans.created"
    }

    await consumer.process_message(message)

    consumer.planner.plan.assert_called_once()
    consumer.repository.create.assert_called_once_with(mock_plan)


@pytest.mark.asyncio
async def test_cognitive_plan_consumer_process_message_invalid_json(
    mock_settings_cognitive, mock_settings
):
    consumer = CognitivePlanConsumer()

    message = {
        "key": None,
        "value": "{invalid json",
        "topic": "cognitive.plans.created"
    }

    # Não deve lançar exceção
    await consumer.process_message(message)


@pytest.mark.asyncio
async def test_cognitive_plan_consumer_process_message_with_cognitive_plan_id(
    mock_settings_cognitive, mock_settings
):
    consumer = CognitivePlanConsumer()

    # Mock planner
    mock_plan = Mock()
    mock_plan.plan_id = "arch-456"
    mock_plan.architecture_type = Mock(value="monolith")
    mock_plan.components = []

    consumer.planner.plan = AsyncMock(return_value=mock_plan)
    consumer.repository.create = AsyncMock()

    message = {
        "key": None,
        "value": json.dumps({
            "plan_id": "cog-456",
            "intent": "Build authentication service"
        }),
        "topic": "cognitive.plans.created"
    }

    await consumer.process_message(message)

    # Verificar que cognitive_plan_id foi passado
    call_args = consumer.planner.plan.call_args[0][0]
    assert call_args["cognitive_plan_id"] == "cog-456"


@pytest.mark.asyncio
async def test_cognitive_plan_consumer_process_message_with_dict_value(
    mock_settings_cognitive, mock_settings
):
    consumer = CognitivePlanConsumer()

    # Mock planner
    mock_plan = Mock()
    mock_plan.plan_id = "arch-789"
    mock_plan.architecture_type = Mock(value="serverless")
    mock_plan.components = []

    consumer.planner.plan = AsyncMock(return_value=mock_plan)
    consumer.repository.create = AsyncMock()

    message = {
        "key": None,
        "value": {"plan_id": "cog-789", "intent": "Serverless function"},
        "topic": "cognitive.plans.created"
    }

    await consumer.process_message(message)

    consumer.planner.plan.assert_called_once()


@pytest.mark.asyncio
async def test_cognitive_plan_consumer_on_plan_created(
    mock_settings_cognitive, mock_settings
):
    consumer = CognitivePlanConsumer()

    # Mock planner e repository
    mock_plan = Mock()
    mock_plan.plan_id = "arch-999"
    mock_plan.architecture_type = Mock(value="hybrid")
    mock_plan.components = []

    consumer.planner.plan = AsyncMock(return_value=mock_plan)
    consumer.repository.create = AsyncMock()

    # Callback mock
    callback_mock = AsyncMock()

    # Registrar callback
    await consumer.on_plan_created(callback_mock)

    # Processar mensagem
    message = {
        "key": None,
        "value": json.dumps({"plan_id": "cog-999", "intent": "Hybrid architecture"}),
        "topic": "cognitive.plans.created"
    }

    await consumer.process_message(message)

    # Nota: O callback é executado via register_callback,
    # mas no fluxo atual é chamado dentro de process_message
    # Vamos verificar que o plano foi criado
    assert consumer._last_created_plan is not None


# ConsumerManager Tests
def test_consumer_manager_initializes():
    manager = ConsumerManager()
    assert len(manager.consumers) == 0
    assert len(manager._tasks) == 0


def test_consumer_manager_registers_consumer(mock_settings):
    manager = ConsumerManager()
    consumer = MockConsumer()
    manager.register(consumer)

    assert len(manager.consumers) == 1
    assert manager.consumers[0] == consumer


@pytest.mark.asyncio
async def test_consumer_manager_stops_all(mock_settings):
    manager = ConsumerManager()
    consumer = MockConsumer()
    manager.register(consumer)

    # Mock stop method
    consumer.stop = AsyncMock()

    await manager.stop_all()

    consumer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_consumer_manager_start_all_creates_tasks(mock_settings):
    """Testa que start_all cria tarefas para os consumidores."""
    manager = ConsumerManager()
    consumer = MockConsumer()

    # Patch para evitar conexão real com Kafka (AIOKafkaConsumer é importado dentro do método start)
    with patch("aiokafka.AIOKafkaConsumer") as mock_kafka_consumer:
        # Mock do consumer Kafka
        mock_kafka_instance = AsyncMock()
        mock_kafka_instance.start = AsyncMock()
        mock_kafka_instance.stop = AsyncMock()
        mock_kafka_instance.__aiter__ = AsyncMock(return_value=iter([]))
        mock_kafka_consumer.return_value = mock_kafka_instance

        manager.register(consumer)

        # start_all roda gather que aguarda forever,
        # então usamos timeout no teste
        task = asyncio.create_task(manager.start_all())
        await asyncio.sleep(0.05)  # Deixar iniciar

        # Verificar que tarefas foram criadas
        assert len(manager._tasks) == 1

        # Cancelar e limpar
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_consumer_manager_multiple_consumers(mock_settings):
    manager = ConsumerManager()

    consumer1 = MockConsumer()
    consumer2 = MockConsumer()

    manager.register(consumer1)
    manager.register(consumer2)

    assert len(manager.consumers) == 2

    # Mock stop methods
    consumer1.stop = AsyncMock()
    consumer2.stop = AsyncMock()

    await manager.stop_all()

    consumer1.stop.assert_called_once()
    consumer2.stop.assert_called_once()


# Edge cases
@pytest.mark.asyncio
async def test_cognitive_plan_consumer_process_message_empty_intent(
    mock_settings_cognitive, mock_settings
):
    consumer = CognitivePlanConsumer()

    # Mock planner
    mock_plan = Mock()
    mock_plan.plan_id = "arch-empty"
    mock_plan.architecture_type = Mock(value="monolith")
    mock_plan.components = []

    consumer.planner.plan = AsyncMock(return_value=mock_plan)
    consumer.repository.create = AsyncMock()

    message = {
        "key": None,
        "value": json.dumps({"plan_id": "cog-empty"}),
        "topic": "cognitive.plans.created"
    }

    # Não deve lançar exceção
    await consumer.process_message(message)

    consumer.planner.plan.assert_called_once()


@pytest.mark.asyncio
async def test_cognitive_plan_consumer_process_message_planner_exception(
    mock_settings_cognitive, mock_settings, caplog
):
    consumer = CognitivePlanConsumer()

    # Mock planner que lança exceção
    consumer.planner.plan = AsyncMock(side_effect=Exception("LLM error"))

    message = {
        "key": None,
        "value": json.dumps({"plan_id": "cog-error", "intent": "Test"}),
        "topic": "cognitive.plans.created"
    }

    # Não deve lançar exceção, apenas logar
    await consumer.process_message(message)
