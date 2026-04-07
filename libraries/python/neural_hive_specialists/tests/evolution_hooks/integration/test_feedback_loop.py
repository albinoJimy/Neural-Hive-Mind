"""
Integration tests para EvolutionFeedbackConsumer.

Este módulo testa o loop completo de feedback:
- Consumo de mensagens Kafka
- Validação com FeedbackMessage
- Atualização do PatternRegistry
- Commit de offsets
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from neural_hive_specialists.evolution_hooks.models import (
    FeedbackOutcome,
    FeedbackSource,
    Fingerprint,
    EvolutionEvaluation,
    TaskCountRange,
    DurationRange,
    DEFAULT_WEIGHTS,
)
from neural_hive_specialists.evolution_hooks.pattern_registry import PatternRegistry
from neural_hive_specialists.evolution_hooks.feedback_consumer import (
    EvolutionFeedbackConsumer,
    create_feedback_consumer,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def feedback_message_dict():
    """Mensagem de feedback de exemplo."""
    return {
        "plan_id": "test-plan-123",
        "fingerprint": {
            "domain": "technical",
            "priority": "high",
            "task_count_range": "medium",
            "task_types": ["BUILD", "TEST", "DEPLOY"],
            "avg_dependency_count": 1.5,
            "has_conditional_deps": True,
            "estimated_duration_range": "medium",
            "complexity_signature": "T-H-B-T-D-M",
        },
        "evaluation": {
            "confidence_score": 0.75,
            "risk_score": 0.25,
            "recommendation": "approve",
            "weights_used": DEFAULT_WEIGHTS.copy(),
            "reasoning_factors": [],
        },
        "feedback": {
            "outcome": "approve",
            "source": "human",
            "reasoning": "Approved after review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@pytest.fixture
def mock_kafka_message(feedback_message_dict):
    """Mock de mensagem Kafka."""

    class MockConsumerRecord:
        def __init__(self, value):
            self.value = value
            self.topic = "evolution.feedback.topic"
            self.partition = 0
            self.offset = 100

    return MockConsumerRecord(feedback_message_dict)


@pytest.fixture
async def pattern_registry_with_data(mongo_client):
    """PatternRegistry com dados iniciais."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    fingerprint = Fingerprint(
        domain="technical",
        priority="high",
        task_count_range=TaskCountRange.MEDIUM,
        task_types=["BUILD", "TEST", "DEPLOY"],
        avg_dependency_count=1.5,
        has_conditional_deps=True,
        estimated_duration_range=DurationRange.MEDIUM,
        complexity_signature="T-H-B-T-D-M",
    )

    evaluation = EvolutionEvaluation(
        confidence_score=0.75,
        risk_score=0.25,
        recommendation="approve",
        weights_used=DEFAULT_WEIGHTS.copy(),
    )

    # Armazenar avaliação inicial
    pattern_id = await registry.store_evaluation(
        plan_id="test-plan-123", fingerprint=fingerprint, evaluation=evaluation
    )

    yield registry, pattern_id

    # Limpar após teste
    collection = mongo_client["test_neural_hive_specialists"][registry.COLLECTION_NAME]
    await collection.delete_many({})


# ============================================================================
# Testes de Inicialização
# ============================================================================


@pytest.mark.asyncio
async def test_consumer_creation(mongo_client):
    """Testa criação do consumer."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    assert consumer.bootstrap_servers == "localhost:9092"
    assert consumer.topic == "evolution.feedback.topic"
    assert consumer.group_id == "evolution-feedback-group"
    assert consumer.pattern_registry is registry
    assert not consumer.is_running
    assert consumer.messages_processed == 0
    assert consumer.messages_failed == 0


@pytest.mark.asyncio
async def test_consumer_factory(mongo_client):
    """Testa factory function."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = create_feedback_consumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
        max_poll_records=20,
    )

    assert isinstance(consumer, EvolutionFeedbackConsumer)
    assert consumer.max_poll_records == 20


# ============================================================================
# Testes de Processamento de Mensagens
# ============================================================================


@pytest.mark.asyncio
async def test_process_message_success(pattern_registry_with_data, feedback_message_dict):
    """Testa processamento bem-sucedido de mensagem."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    # Processar mensagem
    success = await consumer.process_message(feedback_message_dict)

    assert success is True
    assert consumer.messages_processed == 1
    assert consumer.messages_failed == 0

    # Verificar que feedback foi adicionado
    pattern = await registry.get_pattern_by_plan_id("test-plan-123")
    assert pattern is not None
    assert pattern.feedback is not None
    assert pattern.feedback.outcome == FeedbackOutcome.APPROVE


@pytest.mark.asyncio
async def test_process_message_reject(pattern_registry_with_data):
    """Testa processamento de mensagem com reject."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    feedback_message_dict = {
        "plan_id": "test-plan-123",
        "fingerprint": {
            "domain": "technical",
            "priority": "high",
            "task_count_range": "medium",
            "task_types": ["BUILD", "TEST", "DEPLOY"],
            "avg_dependency_count": 1.5,
            "has_conditional_deps": True,
            "estimated_duration_range": "medium",
            "complexity_signature": "T-H-B-T-D-M",
        },
        "evaluation": {
            "confidence_score": 0.75,
            "risk_score": 0.25,
            "recommendation": "approve",
            "weights_used": DEFAULT_WEIGHTS.copy(),
            "reasoning_factors": [],
        },
        "feedback": {
            "outcome": "reject",
            "source": "human",
            "reasoning": "Security concerns",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    success = await consumer.process_message(feedback_message_dict)

    assert success is True

    pattern = await registry.get_pattern_by_plan_id("test-plan-123")
    assert pattern.feedback.outcome == FeedbackOutcome.REJECT


@pytest.mark.asyncio
async def test_process_message_invalid_schema(mongo_client, pattern_registry_with_data):
    """Testa processamento de mensagem com schema inválido."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    # Mensagem com schema inválido (falta campos obrigatórios)
    invalid_message = {"plan_id": "test-plan-123", "falta_outros_campos": True}

    with pytest.raises(Exception):  # ValidationError do Pydantic
        await consumer.process_message(invalid_message)

    assert consumer.messages_failed == 1


@pytest.mark.asyncio
async def test_process_message_pattern_not_found(mongo_client):
    """Testa processamento quando pattern não existe."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    feedback_message_dict = {
        "plan_id": "non-existent-plan",
        "fingerprint": {
            "domain": "technical",
            "priority": "high",
            "task_count_range": "medium",
            "task_types": ["BUILD", "TEST", "DEPLOY"],
            "avg_dependency_count": 1.5,
            "has_conditional_deps": True,
            "estimated_duration_range": "medium",
            "complexity_signature": "T-H-B-T-D-M",
        },
        "evaluation": {
            "confidence_score": 0.75,
            "risk_score": 0.25,
            "recommendation": "approve",
            "weights_used": DEFAULT_WEIGHTS.copy(),
            "reasoning_factors": [],
        },
        "feedback": {
            "outcome": "approve",
            "source": "human",
            "reasoning": "Approved after review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    success = await consumer.process_message(feedback_message_dict)

    assert success is False  # Pattern não encontrado
    assert consumer.messages_processed == 0


# ============================================================================
# Testes de Feedback com corrected_weights
# ============================================================================


@pytest.mark.asyncio
async def test_process_message_with_corrected_weights(pattern_registry_with_data):
    """Testa processamento com pesos corrigidos."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    corrected_weights = {
        "maintainability": 0.30,
        "scalability": 0.20,
        "extensibility": 0.20,
        "modularity": 0.15,
        "tech_debt_prevention": 0.15,
    }

    feedback_message_dict = {
        "plan_id": "test-plan-123",
        "fingerprint": {
            "domain": "technical",
            "priority": "high",
            "task_count_range": "medium",
            "task_types": ["BUILD", "TEST", "DEPLOY"],
            "avg_dependency_count": 1.5,
            "has_conditional_deps": True,
            "estimated_duration_range": "medium",
            "complexity_signature": "T-H-B-T-D-M",
        },
        "evaluation": {
            "confidence_score": 0.75,
            "risk_score": 0.25,
            "recommendation": "approve",
            "weights_used": DEFAULT_WEIGHTS.copy(),
            "reasoning_factors": [],
        },
        "feedback": {
            "outcome": "approve",
            "source": "human",
            "reasoning": "Approved after review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "corrected_weights": corrected_weights,
        },
    }

    success = await consumer.process_message(feedback_message_dict)

    assert success is True

    pattern = await registry.get_pattern_by_plan_id("test-plan-123")
    assert pattern.feedback.corrected_weights == corrected_weights


# ============================================================================
# Testes de Integração Kafka Mock
# ============================================================================


@pytest.mark.asyncio
async def test_poll_with_timeout_no_messages(mongo_client):
    """Testa _poll_with_timeout quando não há mensagens."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
        poll_timeout_ms=100,
    )

    # Criar mock consumer que retorna vazio
    mock_consumer = Mock()
    mock_consumer.getmany = AsyncMock(return_value={})

    with patch.object(consumer, "_create_consumer", new=AsyncMock()):
        with patch.object(consumer, "_start_consumer", new=AsyncMock()):
            consumer.consumer = mock_consumer
            messages = await consumer._poll_with_timeout()

            assert messages == {}


@pytest.mark.asyncio
async def test_poll_with_timeout_with_messages(mongo_client):
    """Testa _poll_with_timeout com mensagens."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    # Criar mock de mensagem
    class MockTP:
        partition = 0

    class MockMsg:
        value = {"test": "data"}

    mock_messages = {MockTP(): [MockMsg()]}

    # Criar mock consumer
    mock_consumer = Mock()
    mock_consumer.getmany = AsyncMock(return_value=mock_messages)

    with patch.object(consumer, "_create_consumer", new=AsyncMock()):
        with patch.object(consumer, "_start_consumer", new=AsyncMock()):
            consumer.consumer = mock_consumer
            messages = await consumer._poll_with_timeout()

            assert messages == mock_messages


# ============================================================================
# Testes do Loop de Consumo
# ============================================================================


@pytest.mark.asyncio
async def test_consume_loop_processes_messages(
    pattern_registry_with_data, feedback_message_dict, mock_kafka_message
):
    """Testa loop de consumo processando mensagens."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    # Criar mock consumer
    class MockTP:
        partition = 0

    mock_messages = {MockTP(): [mock_kafka_message]}

    async def mock_getmany(*args, **kwargs):
        # Retornar mensagens na primeira chamada, vazio depois
        if consumer._messages_processed == 0:
            return mock_messages
        return {}

    async def mock_commit():
        pass

    async def mock_stop():
        pass

    # Criar consumer mock
    consumer.consumer = Mock()
    consumer.consumer.getmany = mock_getmany
    consumer.consumer.commit = mock_commit
    consumer.consumer.stop = mock_stop

    # Marcar como rodando e iniciar o loop
    consumer._running = True

    # Iniciar por um curto período
    task = asyncio.create_task(consumer._consume_loop())

    # Esperar processamento
    await asyncio.sleep(0.1)

    # Parar
    await consumer.stop()

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert consumer.messages_processed == 1


# ============================================================================
# Testes de Start/Stop
# ============================================================================


@pytest.mark.asyncio
async def test_start_stop_lifecycle(mongo_client):
    """Testa ciclo de vida start/stop."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    assert not consumer.is_running

    # Mock do consumer Kafka
    with patch.object(consumer, "_create_consumer", new=AsyncMock()):
        with patch.object(consumer, "_start_consumer", new=AsyncMock()):
            await consumer.start()

            assert consumer.is_running
            assert consumer._consumer_task is not None

            await consumer.stop()

            assert not consumer.is_running


@pytest.mark.asyncio
async def test_start_when_already_running(mongo_client):
    """Testa start quando já está rodando."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    with patch.object(consumer, "_create_consumer", new=AsyncMock()):
        with patch.object(consumer, "_start_consumer", new=AsyncMock()):
            await consumer.start()

            # Tentar start novamente (deve ser idempotente)
            await consumer.start()

            assert consumer.is_running

            await consumer.stop()


@pytest.mark.asyncio
async def test_stop_when_not_running(mongo_client):
    """Testa stop quando não está rodando."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    assert not consumer.is_running

    # Stop quando não está rodando não deve levantar erro
    await consumer.stop()

    assert not consumer.is_running


# ============================================================================
# Testes de Múltiplas Mensagens
# ============================================================================


@pytest.mark.asyncio
async def test_process_multiple_messages(pattern_registry_with_data):
    """Testa processamento de múltiplas mensagens."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    messages = [
        {
            "plan_id": "test-plan-123",
            "fingerprint": {
                "domain": "technical",
                "priority": "high",
                "task_count_range": "medium",
                "task_types": ["BUILD", "TEST", "DEPLOY"],
                "avg_dependency_count": 1.5,
                "has_conditional_deps": True,
                "estimated_duration_range": "medium",
                "complexity_signature": "T-H-B-T-D-M",
            },
            "evaluation": {
                "confidence_score": 0.75,
                "risk_score": 0.25,
                "recommendation": "approve",
                "weights_used": DEFAULT_WEIGHTS.copy(),
                "reasoning_factors": [],
            },
            "feedback": {
                "outcome": "approve",
                "source": "human",
                "reasoning": "Approved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        },
        {
            "plan_id": "test-plan-123",
            "fingerprint": {
                "domain": "technical",
                "priority": "high",
                "task_count_range": "medium",
                "task_types": ["BUILD", "TEST", "DEPLOY"],
                "avg_dependency_count": 1.5,
                "has_conditional_deps": True,
                "estimated_duration_range": "medium",
                "complexity_signature": "T-H-B-T-D-M",
            },
            "evaluation": {
                "confidence_score": 0.60,
                "risk_score": 0.40,
                "recommendation": "review_required",
                "weights_used": DEFAULT_WEIGHTS.copy(),
                "reasoning_factors": [],
            },
            "feedback": {
                "outcome": "reject",
                "source": "automated",
                "reasoning": "Security scan failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        },
    ]

    for msg in messages:
        await consumer.process_message(msg)

    # Segunda mensagem deve atualizar o feedback existente
    pattern = await registry.get_pattern_by_plan_id("test-plan-123")
    assert pattern.feedback.outcome == FeedbackOutcome.REJECT
    assert consumer.messages_processed == 2


# ============================================================================
# Testes de Fontes de Feedback
# ============================================================================


@pytest.mark.asyncio
async def test_feedback_source_system(pattern_registry_with_data):
    """Testa feedback com source system."""
    registry, pattern_id = pattern_registry_with_data

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    feedback_message_dict = {
        "plan_id": "test-plan-123",
        "fingerprint": {
            "domain": "technical",
            "priority": "high",
            "task_count_range": "medium",
            "task_types": ["BUILD", "TEST", "DEPLOY"],
            "avg_dependency_count": 1.5,
            "has_conditional_deps": True,
            "estimated_duration_range": "medium",
            "complexity_signature": "T-H-B-T-D-M",
        },
        "evaluation": {
            "confidence_score": 0.75,
            "risk_score": 0.25,
            "recommendation": "approve",
            "weights_used": DEFAULT_WEIGHTS.copy(),
            "reasoning_factors": [],
        },
        "feedback": {
            "outcome": "approve",
            "source": "system",
            "reasoning": "Auto-approved by policy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    success = await consumer.process_message(feedback_message_dict)

    assert success is True

    pattern = await registry.get_pattern_by_plan_id("test-plan-123")
    assert pattern.feedback.source == FeedbackSource.SYSTEM


# ============================================================================
# Testes de Erro
# ============================================================================


@pytest.mark.asyncio
async def test_process_message_handles_exception(mongo_client):
    """Testa que exceções são tratadas e contabilizadas."""
    registry = PatternRegistry(mongo_client, database="test_neural_hive_specialists")

    consumer = EvolutionFeedbackConsumer(
        bootstrap_servers="localhost:9092",
        topic="evolution.feedback.topic",
        group_id="evolution-feedback-group",
        pattern_registry=registry,
    )

    # Mensagem que causa erro (schema inválido)
    invalid_message = {"invalid": "message"}

    with pytest.raises(Exception):
        await consumer.process_message(invalid_message)

    assert consumer.messages_failed == 1
