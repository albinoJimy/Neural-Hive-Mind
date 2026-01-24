"""
Unit tests for ExecutionEngine cancellation/preemption functionality.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.engine.execution_engine import ExecutionEngine


@pytest.fixture
def mock_config():
    """Create mock configuration for tests."""
    config = MagicMock()
    config.agent_id = 'test-worker-1'
    config.max_concurrent_tasks = 10
    config.max_retries_per_ticket = 3
    config.task_timeout_multiplier = 1.5
    config.retry_backoff_base_seconds = 1
    config.retry_backoff_max_seconds = 30
    return config


@pytest.fixture
def mock_ticket_client():
    """Create mock ticket client."""
    client = AsyncMock()
    client.update_ticket_status = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_result_producer():
    """Create mock result producer."""
    producer = AsyncMock()
    producer.publish_result = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def mock_dependency_coordinator():
    """Create mock dependency coordinator."""
    return AsyncMock()


@pytest.fixture
def mock_executor_registry():
    """Create mock executor registry."""
    registry = MagicMock()
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={'success': True})
    registry.get_executor = MagicMock(return_value=mock_executor)
    return registry


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=False)
    return client


@pytest.fixture
def mock_metrics():
    """Create mock metrics."""
    metrics = MagicMock()
    metrics.tasks_cancelled_total = MagicMock()
    metrics.tasks_cancelled_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.tasks_preempted_total = MagicMock(inc=MagicMock())
    metrics.checkpoint_saves_total = MagicMock()
    metrics.checkpoint_saves_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.active_tasks = MagicMock(set=MagicMock())
    return metrics


@pytest.fixture
def execution_engine(
    mock_config,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry,
    mock_redis_client,
    mock_metrics
):
    """Create ExecutionEngine instance."""
    return ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=mock_redis_client,
        metrics=mock_metrics
    )


class TestCancelActiveTask:
    """Tests for cancel_active_task method."""

    @pytest.mark.asyncio
    async def test_cancel_non_existent_task(self, execution_engine):
        """Returns failure when task not found."""
        result = await execution_engine.cancel_active_task(
            ticket_id='non-existent',
            reason='preemption'
        )

        assert result['success'] is False
        assert 'not active' in result['message']

    @pytest.mark.asyncio
    async def test_cancel_active_task_success(
        self,
        execution_engine,
        mock_ticket_client,
        mock_result_producer,
        mock_redis_client
    ):
        """Successfully cancels an active task."""
        # Create a mock task that will be cancelled
        async def long_running_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(long_running_task())
        execution_engine.active_tasks['test-ticket'] = task

        result = await execution_engine.cancel_active_task(
            ticket_id='test-ticket',
            reason='preemption',
            preempted_by='high-priority-ticket',
            grace_period_seconds=5
        )

        assert result['success'] is True
        assert result['ticket_id'] == 'test-ticket'
        assert result['reason'] == 'preemption'

        # Verify ticket status was updated
        mock_ticket_client.update_ticket_status.assert_called()

        # Verify result was published
        mock_result_producer.publish_result.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_with_checkpoint_save(
        self,
        execution_engine,
        mock_redis_client
    ):
        """Saves checkpoint during cancellation."""
        async def long_running_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(long_running_task())
        execution_engine.active_tasks['test-ticket'] = task

        result = await execution_engine.cancel_active_task(
            ticket_id='test-ticket',
            reason='preemption'
        )

        assert result['checkpoint_saved'] is True
        assert result['checkpoint_key'] == 'checkpoint:test-ticket'

        # Verify checkpoint was saved to Redis
        mock_redis_client.set.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_metrics_recorded(
        self,
        execution_engine,
        mock_metrics
    ):
        """Metrics are recorded during cancellation."""
        async def long_running_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(long_running_task())
        execution_engine.active_tasks['test-ticket'] = task

        await execution_engine.cancel_active_task(
            ticket_id='test-ticket',
            reason='preemption'
        )

        # Verify metrics were recorded
        mock_metrics.tasks_cancelled_total.labels.assert_called_with(reason='preemption')
        mock_metrics.tasks_preempted_total.inc.assert_called_once()


class TestSaveCheckpoint:
    """Tests for _save_checkpoint method."""

    @pytest.mark.asyncio
    async def test_save_checkpoint_success(self, execution_engine, mock_redis_client):
        """Successfully saves checkpoint."""
        result = await execution_engine._save_checkpoint(
            ticket_id='test-ticket',
            reason='preemption',
            preempted_by='high-priority-ticket'
        )

        assert result['success'] is True
        assert result['checkpoint_key'] == 'checkpoint:test-ticket'
        mock_redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_checkpoint_no_redis(self, execution_engine):
        """Returns failure when Redis not available."""
        execution_engine.redis_client = None

        result = await execution_engine._save_checkpoint(
            ticket_id='test-ticket',
            reason='preemption'
        )

        assert result['success'] is False
        assert 'Redis not available' in result['message']

    @pytest.mark.asyncio
    async def test_save_checkpoint_redis_error(self, execution_engine, mock_redis_client):
        """Handles Redis error gracefully."""
        mock_redis_client.set.side_effect = Exception('Redis connection error')

        result = await execution_engine._save_checkpoint(
            ticket_id='test-ticket',
            reason='preemption'
        )

        assert result['success'] is False
        assert 'Redis connection error' in result['message']


class TestExecuteTicketCancellation:
    """Tests for _execute_ticket handling CancelledError."""

    @pytest.mark.asyncio
    async def test_execute_ticket_handles_cancellation(
        self,
        execution_engine,
        mock_executor_registry,
        mock_ticket_client,
        mock_dependency_coordinator
    ):
        """_execute_ticket properly handles CancelledError."""
        # Mock the tracer
        with patch('src.engine.execution_engine.get_tracer') as mock_get_tracer:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span.set_attribute = MagicMock()

            mock_tracer = MagicMock()
            mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
            mock_get_tracer.return_value = mock_tracer

            # Mock executor that will be cancelled
            async def slow_execute(ticket):
                await asyncio.sleep(100)
                return {'success': True}

            mock_executor = AsyncMock()
            mock_executor.execute = slow_execute
            mock_executor_registry.get_executor.return_value = mock_executor

            # Mock dependency coordinator to not block
            mock_dependency_coordinator.wait_for_dependencies = AsyncMock(return_value=None)

            ticket = {
                'ticket_id': 'test-ticket',
                'task_type': 'test',
                'sla': {'timeout_ms': 60000}
            }

            # Start the execution
            task = asyncio.create_task(execution_engine._execute_ticket(ticket))
            execution_engine.active_tasks['test-ticket'] = task

            # Give it a moment to start
            await asyncio.sleep(0.1)

            # Cancel the task
            task.cancel()

            # Should raise CancelledError
            with pytest.raises(asyncio.CancelledError):
                await task


class TestGracefulShutdownWithPreemption:
    """Tests for shutdown behavior with preemption."""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_active_tasks(self, execution_engine, mock_metrics):
        """Shutdown cancels all active tasks."""
        async def long_running_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        # Create multiple active tasks
        for i in range(3):
            task = asyncio.create_task(long_running_task())
            execution_engine.active_tasks[f'ticket-{i}'] = task

        # Shutdown with short timeout to force cancellation
        await execution_engine.shutdown(timeout_seconds=1)

        # All tasks should be done (cancelled)
        for ticket_id, task in execution_engine.active_tasks.items():
            assert task.done() or task.cancelled()
