"""
Integration tests for BuildExecutor.

Tests the BuildExecutor with mocked and real Code Forge integration,
including retry logic, timeout handling, and fallback to simulation.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_integration.clients.code_forge_client import PipelineStatus


# Import test helpers
from tests.fixtures.executor_fixtures import (
    create_mock_code_forge_client,
    create_pipeline_status,
)
from tests.helpers.integration_helpers import (
    ExecutorTestHelper,
    ResultValidator,
)


pytestmark = [pytest.mark.integration]


class TestBuildExecutorWithMockCodeForge:
    """Tests for BuildExecutor with mocked Code Forge client."""

    @pytest.mark.asyncio
    async def test_build_executor_with_mock_code_forge_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test successful build execution with mocked Code Forge."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Create mock Code Forge client
        mock_client = create_mock_code_forge_client(
            pipeline_id='pipeline-123',
            status='completed',
        )

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket(
            artifact_id='test-artifact',
            branch='main',
            commit_sha='abc123def456',
        )

        result = await executor.execute(ticket)

        # Validate result
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_has_output(result, 'pipeline_id', 'artifact_id', 'branch')
        ResultValidator.assert_output_value(result, 'pipeline_id', 'pipeline-123')
        ResultValidator.assert_output_value(result, 'artifact_id', 'test-artifact')
        ResultValidator.assert_has_logs(result, min_count=2)
        ResultValidator.assert_log_contains(result, 'Build started')
        ResultValidator.assert_log_contains(result, 'pipeline')

        # Verify Code Forge client was called
        mock_client.trigger_pipeline.assert_called_once_with('test-artifact')
        mock_client.wait_for_pipeline_completion.assert_called_once()

        # Verify metrics were recorded
        mock_metrics.build_tasks_executed_total.labels.assert_called()

    @pytest.mark.asyncio
    async def test_build_executor_code_forge_connection_failure_fallback(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test fallback to simulation when Code Forge is unavailable."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Create mock that always fails
        mock_client = create_mock_code_forge_client(should_fail=True)

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Should fall back to simulation and still succeed
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)
        ResultValidator.assert_has_output(result, 'artifact_url', 'build_id')

    @pytest.mark.asyncio
    async def test_build_executor_pipeline_timeout(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of pipeline timeout."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Create mock that returns timeout status
        mock_client = create_mock_code_forge_client(
            pipeline_id='pipeline-timeout',
            status='timeout',
        )

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Pipeline timeout should result in failure
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'pipeline_id', 'pipeline-timeout')

    @pytest.mark.asyncio
    async def test_build_executor_pipeline_failed_status(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of failed pipeline status."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Create mock that returns failed status
        mock_client = create_mock_code_forge_client(
            pipeline_id='pipeline-failed',
            status='failed',
        )

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Failed pipeline should result in failure
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)

    @pytest.mark.asyncio
    async def test_build_executor_retry_logic_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test retry logic when trigger fails initially then succeeds."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Track call count for retry verification
        call_count = {'value': 0}
        async def trigger_with_retry(artifact_id):
            call_count['value'] += 1
            if call_count['value'] < 3:
                raise ConnectionError('Temporary failure')
            return 'pipeline-retry-success'

        mock_client = AsyncMock()
        mock_client.trigger_pipeline = AsyncMock(side_effect=trigger_with_retry)
        mock_client.wait_for_pipeline_completion = AsyncMock(
            return_value=create_pipeline_status(
                pipeline_id='pipeline-retry-success',
                status='completed',
            )
        )

        # Configure settings for faster retries in tests
        worker_config.code_forge_retry_attempts = 5
        worker_config.retry_backoff_base_seconds = 0.1
        worker_config.retry_backoff_max_seconds = 0.5

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Should succeed after retries
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        assert call_count['value'] == 3, 'Expected 3 calls (2 failures + 1 success)'

    @pytest.mark.asyncio
    async def test_build_executor_retry_exhausted(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test fallback when all retries are exhausted."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Mock that always fails
        mock_client = AsyncMock()
        mock_client.trigger_pipeline = AsyncMock(
            side_effect=ConnectionError('Persistent failure')
        )

        # Configure for quick retries
        worker_config.code_forge_retry_attempts = 2
        worker_config.retry_backoff_base_seconds = 0.01
        worker_config.retry_backoff_max_seconds = 0.05

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Should fall back to simulation after exhausting retries
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)
        assert mock_client.trigger_pipeline.call_count == 2


class TestBuildExecutorSimulation:
    """Tests for BuildExecutor simulation mode (no Code Forge client)."""

    @pytest.mark.asyncio
    async def test_build_executor_simulation_mode(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test build execution in pure simulation mode."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        executor = BuildExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            code_forge_client=None,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Simulation should always succeed
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)
        ResultValidator.assert_has_output(result, 'artifact_url', 'build_id', 'commit_sha')
        ResultValidator.assert_log_contains(result, 'simulated')

    @pytest.mark.asyncio
    async def test_build_executor_simulation_metrics(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test that metrics are recorded in simulation mode."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        executor = BuildExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            code_forge_client=None,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()

        result = await executor.execute(ticket)

        # Verify metrics were recorded
        mock_metrics.build_tasks_executed_total.labels.assert_called_with(status='success')
        mock_metrics.build_duration_seconds.labels.assert_called_with(stage='simulated')


class TestBuildExecutorValidation:
    """Tests for BuildExecutor input validation."""

    @pytest.mark.asyncio
    async def test_build_executor_missing_ticket_id(
        self, build_executor
    ):
        """Test that missing ticket_id raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'task_id': 'task-123',
            'task_type': 'BUILD',
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await build_executor.execute(ticket)

        assert 'ticket_id' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_build_executor_wrong_task_type(
        self, build_executor
    ):
        """Test that wrong task_type raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'ticket_id': 'ticket-123',
            'task_id': 'task-123',
            'task_type': 'DEPLOY',  # Wrong type
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await build_executor.execute(ticket)

        assert 'task type mismatch' in str(exc_info.value).lower()


@pytest.mark.real_integration
@pytest.mark.code_forge
class TestBuildExecutorRealCodeForge:
    """Tests that require a real Code Forge instance."""

    @pytest.mark.asyncio
    async def test_build_executor_with_real_code_forge(self, worker_config, mock_vault_client, mock_metrics):
        """Test with real Code Forge (requires CODE_FORGE_URL env var)."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from neural_hive_integration.clients.code_forge_client import CodeForgeClient

        code_forge_url = os.getenv('CODE_FORGE_URL')
        if not code_forge_url:
            pytest.skip('CODE_FORGE_URL not configured')

        # Create real Code Forge client
        real_client = CodeForgeClient(base_url=code_forge_url, timeout=60)

        try:
            executor = BuildExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                code_forge_client=real_client,
                metrics=mock_metrics,
            )

            # Use a test artifact that exists in the Code Forge
            ticket = ExecutorTestHelper.create_build_ticket(
                artifact_id='test-integration-artifact',
                branch='main',
            )

            result = await executor.execute(ticket)

            # With real service, expect either success or graceful failure
            assert 'success' in result
            assert 'output' in result
            assert 'metadata' in result

        finally:
            await real_client.close()
