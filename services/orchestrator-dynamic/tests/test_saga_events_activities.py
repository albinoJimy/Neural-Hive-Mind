"""
Testes unitários para activities de eventos Saga.

Cobre:
- publish_saga_created: Publicação de evento de criação
- publish_saga_started: Publicação de evento de início
- publish_saga_completed: Publicação de evento de conclusão
- publish_saga_failed: Publicação de evento de falha
"""

# Configure path
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.activities.saga_events import (
    get_saga_producer,
    publish_saga_completed,
    publish_saga_created,
    publish_saga_failed,
    publish_saga_started,
)


@pytest.fixture()
def mock_saga_producer():
    """Mock do SagaProducer."""
    producer = AsyncMock()
    producer.publish_saga_created = AsyncMock()
    producer.publish_saga_started = AsyncMock()
    producer.publish_saga_completed = AsyncMock()
    producer.publish_saga_failed = AsyncMock()
    return producer


@pytest.fixture()
def mock_settings():
    """Mock das settings."""
    settings = MagicMock()
    return settings


@pytest.fixture()
def mock_saga_metrics():
    """Mock das métricas Saga."""
    metrics = MagicMock()
    return metrics


class TestPublishSagaCreated:
    """Testes para publish_saga_created."""

    @pytest.mark.asyncio()
    async def test_publish_created_success(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação de saga.created com sucesso."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):  # Reset singleton
                        result = await publish_saga_created(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            intent_id="intent-abc",
                            steps_count=5,
                            metadata={"key": "value"},
                        )

                        assert result["success"] is True
                        assert result["saga_id"] == "saga-123"
                        assert result["workflow_id"] == "workflow-456"
                        mock_saga_producer.publish_saga_created.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_created_without_metadata(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação sem metadados."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_created(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            intent_id="intent-abc",
                            steps_count=3,
                        )

                        assert result["success"] is True

    @pytest.mark.asyncio()
    async def test_publish_created_producer_error(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação quando producer lança exceção."""
        mock_saga_producer.publish_saga_created.side_effect = Exception("Kafka error")

        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_created(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            intent_id="intent-abc",
                            steps_count=1,
                        )

                        # Deve retornar sucesso=False mas não lançar exceção
                        assert result["success"] is False
                        assert "error" in result

    @pytest.mark.asyncio()
    async def test_publish_created_initialization_error(self, mock_settings, mock_saga_metrics):
        """Testa publicação quando inicialização falha."""
        mock_settings_instance = MagicMock()
        mock_settings_instance.initialize = AsyncMock(side_effect=Exception("Init error"))

        with patch("src.activities.saga_events.get_settings", return_value=mock_settings_instance):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch("src.activities.saga_events._producer", None):
                    result = await publish_saga_created(
                        saga_id="saga-123",
                        workflow_id="workflow-456",
                        plan_id="plan-789",
                        intent_id="intent-abc",
                        steps_count=1,
                    )

                    assert result["success"] is False


class TestPublishSagaStarted:
    """Testes para publish_saga_started."""

    @pytest.mark.asyncio()
    async def test_publish_started_success(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação de saga.started com sucesso."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_started(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            steps_count=5,
                        )

                        assert result["success"] is True
                        assert result["saga_id"] == "saga-123"
                        mock_saga_producer.publish_saga_started.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_started_producer_error(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação com erro no producer."""
        mock_saga_producer.publish_saga_started.side_effect = Exception("Kafka error")

        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_started(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            steps_count=1,
                        )

                        assert result["success"] is False
                        assert result["saga_id"] == "saga-123"


class TestPublishSagaCompleted:
    """Testes para publish_saga_completed."""

    @pytest.mark.asyncio()
    async def test_publish_completed_success(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação de saga.completed com sucesso."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_completed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            steps_completed=5,
                        )

                        assert result["success"] is True
                        assert result["saga_id"] == "saga-123"
                        mock_saga_producer.publish_saga_completed.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_completed_partial_steps(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação com_steps parciais."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_completed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            steps_completed=3,
                        )

                        assert result["success"] is True

    @pytest.mark.asyncio()
    async def test_publish_completed_producer_error(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação com erro no producer."""
        mock_saga_producer.publish_saga_completed.side_effect = Exception("Kafka error")

        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_completed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            steps_completed=1,
                        )

                        assert result["success"] is False


class TestPublishSagaFailed:
    """Testes para publish_saga_failed."""

    @pytest.mark.asyncio()
    async def test_publish_failed_success(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação de saga.failed com sucesso."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_failed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            error="Task execution failed",
                            retry_count=1,
                            max_retries=3,
                        )

                        assert result["success"] is True
                        assert result["saga_id"] == "saga-123"
                        mock_saga_producer.publish_saga_failed.assert_called_once()

    @pytest.mark.asyncio()
    async def test_publish_failed_without_retry_info(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação sem informações de retry."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_failed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            error="Critical error",
                        )

                        assert result["success"] is True

    @pytest.mark.asyncio()
    async def test_publish_failed_with_max_retries(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação após máximo de retries."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_failed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            error="Max retries exceeded",
                            retry_count=3,
                            max_retries=3,
                        )

                        assert result["success"] is True

    @pytest.mark.asyncio()
    async def test_publish_failed_producer_error(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa publicação com erro no producer."""
        mock_saga_producer.publish_saga_failed.side_effect = Exception("Kafka error")

        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.get_saga_producer",
                    return_value=mock_saga_producer,
                ):
                    with patch("src.activities.saga_events._producer", None):
                        result = await publish_saga_failed(
                            saga_id="saga-123",
                            workflow_id="workflow-456",
                            plan_id="plan-789",
                            error="Error",
                        )

                        assert result["success"] is False


class TestGetSagaProducer:
    """Testes para get_saga_producer."""

    @pytest.mark.asyncio()
    async def test_get_producer_singleton(
        self, mock_saga_producer, mock_settings, mock_saga_metrics
    ):
        """Testa que producer é singleton."""
        with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
            with patch(
                "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
            ):
                with patch(
                    "src.activities.saga_events.SagaProducer", return_value=mock_saga_producer
                ):
                    with patch("src.activities.saga_events._producer", None):
                        producer1 = await get_saga_producer()
                        producer2 = await get_saga_producer()

                        assert producer1 is producer2

    @pytest.mark.asyncio()
    async def test_get_producer_initializes_once(self, mock_settings, mock_saga_metrics):
        """Testa que producer é inicializado apenas uma vez."""
        producer_mock = MagicMock()
        producer_mock.initialize = AsyncMock()

        with patch("src.activities.saga_events.SagaProducer", return_value=producer_mock):
            with patch("src.activities.saga_events.get_settings", return_value=mock_settings):
                with patch(
                    "src.activities.saga_events.get_saga_metrics", return_value=mock_saga_metrics
                ):
                    with patch("src.activities.saga_events._producer", None):
                        await get_saga_producer()

                        producer_mock.initialize.assert_called_once()
