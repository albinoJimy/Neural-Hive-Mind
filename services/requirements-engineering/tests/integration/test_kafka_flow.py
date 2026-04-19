"""Testes de integração Kafka para Requirements Engineering."""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from src.consumers.cognitive_plan_consumer import CognitivePlanConsumer
from src.producers.requirements_producer import RequirementsProducer
from src.services.requirements_engineer import RequirementsEngineer


@pytest.fixture()
def mock_settings():
    """Fixture com configurações de teste."""

    class MockSettings:
        kafka_bootstrap_servers = "localhost:9092"
        kafka_consumer_group = "test-consumers"
        kafka_input_topic = "cognitive.plans.created"
        kafka_output_topic = "requirements.generated"
        kafka_dlq_topic = "requirements.dlq"
        openai_api_key = "test-key"
        llm_model = "gpt-4"

    return MockSettings()


@pytest.fixture()
def mock_llm_client():
    """Fixture para mock LLM client."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[
            Mock(
                message=Mock(
                    content='[{"id": "REQ-001", "title": "Test Requirement", "description": "This is a test description that is long enough", "priority": "high", "type": "functional", "rationale": "Test rationale"}]'
                )
            )
        ]
    )
    return mock_client


@pytest.mark.asyncio()
async def test_cognitive_plan_consumer_processes_message(mock_settings, mock_llm_client):
    """Testa que o consumer processa mensagens do Kafka."""
    # Arrange
    requirements_engineer = RequirementsEngineer(llm_client=mock_llm_client)
    mock_producer = AsyncMock()
    mock_producer.publish_requirements_generated = AsyncMock()

    consumer = CognitivePlanConsumer(
        requirements_engineer=requirements_engineer,
        producer=mock_producer,
    )
    consumer._bootstrap_servers = mock_settings.kafka_bootstrap_servers
    consumer._group_id = mock_settings.kafka_consumer_group
    consumer._input_topic = mock_settings.kafka_input_topic

    # Criar mensagem mock
    mock_message = Mock()
    mock_message.topic = mock_settings.kafka_input_topic
    mock_message.partition = 0
    mock_message.offset = 0
    mock_message.value = json.dumps(
        {
            "plan_id": "plan-123",
            "intent": {"text": "Test intent"},
            "plan_text": "Test plan text with enough description for minimum length",
        }
    ).encode("utf-8")

    # Act
    await consumer._process_message(mock_message)

    # Assert
    mock_producer.publish_requirements_generated.assert_called_once()


@pytest.mark.asyncio()
async def test_requirements_publisher_sends_to_kafka():
    """Testa que o producer envia eventos para o Kafka."""
    # Arrange
    producer = RequirementsProducer()
    producer._producer = AsyncMock()
    producer._producer.send_and_wait = AsyncMock()
    producer._running = True

    # Act
    await producer.publish_requirements_generated(
        requirements_set_id="rs-123",
        cognitive_plan_id="plan-123",
        requirements_count=5,
        functional_count=3,
        non_functional_count=2,
    )

    # Assert
    producer._producer.send_and_wait.assert_called_once()


@pytest.mark.asyncio()
async def test_consumer_handles_invalid_json(mock_settings, mock_llm_client):
    """Testa que o consumer lida com JSON inválido."""
    # Arrange
    requirements_engineer = RequirementsEngineer(llm_client=mock_llm_client)
    mock_producer = AsyncMock()

    consumer = CognitivePlanConsumer(
        requirements_engineer=requirements_engineer,
        producer=mock_producer,
    )
    consumer._dlq_topic = mock_settings.kafka_dlq_topic

    # Criar mensagem com JSON inválido
    mock_message = Mock()
    mock_message.value = b"invalid json"

    # Act & Assert (não deve levantar exceção)
    await consumer._process_message(mock_message)


@pytest.mark.asyncio()
async def test_end_to_end_flow(mock_settings, mock_llm_client):
    """Teste E2E: mensagem entra, requisitos são gerados, evento publicado."""
    # Arrange
    requirements_engineer = RequirementsEngineer(llm_client=mock_llm_client)
    mock_producer = AsyncMock()
    mock_producer.publish_requirements_generated = AsyncMock()

    consumer = CognitivePlanConsumer(
        requirements_engineer=requirements_engineer,
        producer=mock_producer,
    )

    mock_message = Mock()
    mock_message.value = json.dumps(
        {
            "plan_id": "plan-e2e",
            "plan_text": "E2E test plan with enough description to pass validation requirements",
        }
    ).encode("utf-8")

    # Act
    await consumer._process_message(mock_message)

    # Assert
    assert mock_producer.publish_requirements_generated.call_count == 1
    call_args = mock_producer.publish_requirements_generated.call_args
    assert call_args[1]["cognitive_plan_id"] == "plan-e2e"
    assert call_args[1]["requirements_count"] >= 1
