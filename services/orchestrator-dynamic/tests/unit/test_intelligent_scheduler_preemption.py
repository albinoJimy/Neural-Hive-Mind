"""
Unit tests for IntelligentScheduler preemption functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.scheduler.intelligent_scheduler import IntelligentScheduler, Priority


@pytest.fixture
def mock_config():
    """Create mock configuration for tests."""
    config = MagicMock()
    config.scheduler_enable_preemption = True
    config.scheduler_preemption_min_preemptor_priority = 'HIGH'
    config.scheduler_preemption_max_preemptable_priority = 'LOW'
    config.scheduler_preemption_grace_period_seconds = 30
    config.scheduler_preemption_max_concurrent = 5
    config.scheduler_preemption_worker_cooldown_seconds = 60
    config.scheduler_preemption_retry_preempted_tasks = True
    config.scheduler_preemption_retry_delay_seconds = 300
    config.service_registry_host = 'localhost'
    config.service_registry_port = 50051
    config.service_registry_timeout_seconds = 3
    config.service_registry_max_results = 5
    config.service_registry_cache_ttl_seconds = 10
    config.enable_intelligent_scheduler = True
    config.enable_ml_enhanced_scheduling = False
    config.scheduler_max_parallel_tickets = 100
    config.scheduler_priority_weights = {'risk': 0.4, 'qos': 0.3, 'sla': 0.3}
    config.scheduler_enable_affinity = False
    return config


@pytest.fixture
def mock_metrics():
    """Create mock metrics."""
    metrics = MagicMock()
    metrics.record_task_preempted = MagicMock()
    metrics.record_preemption_attempt = MagicMock()
    metrics.record_preemption_failure = MagicMock()
    metrics.record_scheduler_rejection = MagicMock()
    return metrics


@pytest.fixture
def mock_priority_calculator():
    """Create mock priority calculator."""
    calculator = MagicMock()
    calculator.calculate_priority = MagicMock(return_value=0.5)
    return calculator


@pytest.fixture
def mock_resource_allocator():
    """Create mock resource allocator."""
    allocator = MagicMock()
    allocator.allocate = AsyncMock(return_value={'worker_id': 'test-worker'})
    return allocator


@pytest.fixture
def scheduler(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator):
    """Create IntelligentScheduler instance."""
    scheduler = IntelligentScheduler(
        config=mock_config,
        metrics=mock_metrics,
        priority_calculator=mock_priority_calculator,
        resource_allocator=mock_resource_allocator
    )
    return scheduler


class TestCanPreempt:
    """Tests for _can_preempt method."""

    def test_can_preempt_high_preempts_low(self, scheduler):
        """HIGH priority can preempt LOW priority."""
        assert scheduler._can_preempt('HIGH', 'LOW') is True

    def test_can_preempt_critical_preempts_low(self, scheduler):
        """CRITICAL priority can preempt LOW priority."""
        assert scheduler._can_preempt('CRITICAL', 'LOW') is True

    def test_cannot_preempt_medium_preempts_low(self, scheduler):
        """MEDIUM priority cannot preempt (below threshold)."""
        assert scheduler._can_preempt('MEDIUM', 'LOW') is False

    def test_cannot_preempt_high_preempts_medium(self, scheduler):
        """HIGH priority cannot preempt MEDIUM (MEDIUM above max preemptable)."""
        assert scheduler._can_preempt('HIGH', 'MEDIUM') is False

    def test_cannot_preempt_high_preempts_high(self, scheduler):
        """HIGH priority cannot preempt HIGH."""
        assert scheduler._can_preempt('HIGH', 'HIGH') is False

    def test_cannot_preempt_when_disabled(self, scheduler, mock_config):
        """Preemption returns False when disabled."""
        mock_config.scheduler_enable_preemption = False
        assert scheduler._can_preempt('CRITICAL', 'LOW') is False


class TestPreemptLowPriorityTasks:
    """Tests for preempt_low_priority_tasks method."""

    @pytest.mark.asyncio
    async def test_preemption_disabled_returns_empty(self, scheduler, mock_config):
        """Returns empty list when preemption is disabled."""
        mock_config.scheduler_enable_preemption = False
        high_priority_ticket = {'ticket_id': 'test-1', 'priority': 'CRITICAL'}

        result = await scheduler.preempt_low_priority_tasks(high_priority_ticket)

        assert result == []

    @pytest.mark.asyncio
    async def test_max_concurrent_preemptions_exceeded(self, scheduler, mock_metrics):
        """Returns empty when max concurrent preemptions reached."""
        scheduler._active_preemptions = {'a', 'b', 'c', 'd', 'e'}  # 5 active
        high_priority_ticket = {'ticket_id': 'test-1', 'priority': 'CRITICAL'}

        result = await scheduler.preempt_low_priority_tasks(high_priority_ticket)

        assert result == []
        mock_metrics.record_preemption_attempt.assert_called_with(
            success=False,
            reason='max_concurrent'
        )

    @pytest.mark.asyncio
    async def test_no_preemptable_tasks_found(self, scheduler, mock_metrics):
        """Returns empty when no preemptable tasks found."""
        scheduler._discover_workers_cached = AsyncMock(return_value=[])
        high_priority_ticket = {
            'ticket_id': 'test-1',
            'priority': 'CRITICAL',
            'required_capabilities': ['test']
        }

        result = await scheduler.preempt_low_priority_tasks(high_priority_ticket)

        assert result == []

    @pytest.mark.asyncio
    async def test_successful_preemption(self, scheduler, mock_metrics):
        """Successfully preempts a low priority task."""
        # Mock worker with running task
        workers = [{
            'agent_id': 'worker-1',
            'endpoint': 'http://worker-1:8080',
            'capabilities': ['test'],
            'running_task': {
                'ticket_id': 'low-priority-task',
                'priority': 'LOW',
                'started_at': '2024-01-01T00:00:00Z',
                'progress_pct': 30
            }
        }]
        scheduler._discover_workers_cached = AsyncMock(return_value=workers)

        # Mock successful HTTP call
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            high_priority_ticket = {
                'ticket_id': 'high-priority-task',
                'priority': 'CRITICAL',
                'required_capabilities': ['test']
            }

            result = await scheduler.preempt_low_priority_tasks(high_priority_ticket)

        assert 'worker-1' in result
        assert 'worker-1' in scheduler._preemption_cooldowns

    @pytest.mark.asyncio
    async def test_worker_in_cooldown_skipped(self, scheduler):
        """Workers in cooldown are skipped."""
        # Set worker in cooldown
        scheduler._preemption_cooldowns['worker-1'] = datetime.now() + timedelta(seconds=60)

        workers = [{
            'agent_id': 'worker-1',
            'endpoint': 'http://worker-1:8080',
            'capabilities': ['test'],
            'running_task': {
                'ticket_id': 'low-priority-task',
                'priority': 'LOW'
            }
        }]
        scheduler._discover_workers_cached = AsyncMock(return_value=workers)

        high_priority_ticket = {
            'ticket_id': 'high-priority-task',
            'priority': 'CRITICAL',
            'required_capabilities': ['test']
        }

        result = await scheduler.preempt_low_priority_tasks(high_priority_ticket)

        assert result == []


class TestFindPreemptableTasks:
    """Tests for _find_preemptable_tasks method."""

    @pytest.mark.asyncio
    async def test_sorts_by_priority_and_progress(self, scheduler):
        """Preemptable tasks sorted by priority then progress."""
        workers = [
            {
                'agent_id': 'worker-1',
                'capabilities': ['test'],
                'running_task': {'ticket_id': 't1', 'priority': 'LOW', 'progress_pct': 80}
            },
            {
                'agent_id': 'worker-2',
                'capabilities': ['test'],
                'running_task': {'ticket_id': 't2', 'priority': 'LOW', 'progress_pct': 20}
            },
        ]
        scheduler._discover_workers_cached = AsyncMock(return_value=workers)

        high_priority_ticket = {
            'ticket_id': 'hp',
            'priority': 'CRITICAL',
            'required_capabilities': ['test']
        }

        result = await scheduler._find_preemptable_tasks(high_priority_ticket, limit=5)

        # Should be sorted by priority (same) then progress (lowest first)
        assert result[0]['ticket_id'] == 't2'
        assert result[1]['ticket_id'] == 't1'

    @pytest.mark.asyncio
    async def test_respects_limit(self, scheduler):
        """Respects the limit parameter."""
        workers = [
            {
                'agent_id': f'worker-{i}',
                'capabilities': ['test'],
                'running_task': {'ticket_id': f't{i}', 'priority': 'LOW'}
            }
            for i in range(10)
        ]
        scheduler._discover_workers_cached = AsyncMock(return_value=workers)

        high_priority_ticket = {
            'ticket_id': 'hp',
            'priority': 'CRITICAL',
            'required_capabilities': ['test']
        }

        result = await scheduler._find_preemptable_tasks(high_priority_ticket, limit=3)

        assert len(result) == 3


class TestPreemptTask:
    """Tests for _preempt_task method."""

    @pytest.mark.asyncio
    async def test_preempt_task_success(self, scheduler, mock_metrics):
        """Successfully preempts a task."""
        task = {
            'ticket_id': 'low-task',
            'worker_endpoint': 'http://worker:8080',
            'priority': 'LOW'
        }
        preemptor = {'ticket_id': 'high-task', 'priority': 'CRITICAL'}

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await scheduler._preempt_task(task, preemptor)

        assert result is True
        mock_metrics.record_task_preempted.assert_called_once()

    @pytest.mark.asyncio
    async def test_preempt_task_worker_rejected(self, scheduler, mock_metrics):
        """Handles worker rejection."""
        task = {
            'ticket_id': 'low-task',
            'worker_endpoint': 'http://worker:8080',
            'priority': 'LOW'
        }
        preemptor = {'ticket_id': 'high-task', 'priority': 'CRITICAL'}

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = 'Task not found'
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await scheduler._preempt_task(task, preemptor)

        assert result is False
        mock_metrics.record_preemption_failure.assert_called_with(reason='worker_rejected')

    @pytest.mark.asyncio
    async def test_preempt_task_timeout(self, scheduler, mock_metrics):
        """Handles timeout during preemption."""
        import httpx

        task = {
            'ticket_id': 'low-task',
            'worker_endpoint': 'http://worker:8080',
            'priority': 'LOW'
        }
        preemptor = {'ticket_id': 'high-task', 'priority': 'CRITICAL'}

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException('timeout')
            )

            result = await scheduler._preempt_task(task, preemptor)

        assert result is False
        mock_metrics.record_preemption_failure.assert_called_with(reason='timeout')

    @pytest.mark.asyncio
    async def test_preempt_task_no_endpoint(self, scheduler):
        """Returns False when no endpoint provided."""
        task = {'ticket_id': 'low-task', 'priority': 'LOW'}
        preemptor = {'ticket_id': 'high-task', 'priority': 'CRITICAL'}

        result = await scheduler._preempt_task(task, preemptor)

        assert result is False


class TestPriorityEnum:
    """Tests for Priority enum."""

    def test_priority_ordering(self):
        """Priority enum has correct ordering."""
        assert Priority.LOW.value < Priority.MEDIUM.value
        assert Priority.MEDIUM.value < Priority.HIGH.value
        assert Priority.HIGH.value < Priority.CRITICAL.value
