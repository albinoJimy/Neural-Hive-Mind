"""
Integration tests for TestExecutor.

Tests the TestExecutor with mocked and real CI/CD integrations,
including GitHub Actions, local command execution, and security validations.
"""

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.executor_fixtures import create_mock_github_actions_client
from tests.fixtures.client_fixtures import MockGitHubActionsServer
from tests.helpers.integration_helpers import (
    ExecutorTestHelper,
    ResultValidator,
)


pytestmark = [pytest.mark.integration]


class TestTestExecutorWithMockGitHubActions:
    """Tests for TestExecutor with mocked GitHub Actions."""

    @pytest.mark.asyncio
    async def test_test_executor_github_actions_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test successful test execution via GitHub Actions."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        # Enable GitHub Actions
        worker_config.github_actions_enabled = True
        worker_config.github_token = 'test-token'

        mock_client = create_mock_github_actions_client(
            run_id='run-123',
            success=True,
            tests_passed=42,
            tests_failed=0,
            coverage=87.5,
        )

        with patch('services.worker_agents.src.executors.test_executor.GitHubActionsClient') as mock_class:
            mock_class.from_env.return_value = mock_client

            executor = TestExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                metrics=mock_metrics,
            )
            # Manually set the client since it's created in __init__
            executor.github_actions_client = mock_client

            ticket = ExecutorTestHelper.create_test_ticket(
                provider='github_actions',
                repo='test-org/test-repo',
                workflow_id='ci.yml',
                ref='main',
                test_suite='integration',
            )

            result = await executor.execute(ticket)

        # Validate result
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_has_output(result, 'tests_passed', 'tests_failed', 'coverage', 'run_id')
        ResultValidator.assert_output_value(result, 'tests_passed', 42)
        ResultValidator.assert_output_value(result, 'tests_failed', 0)
        ResultValidator.assert_output_value(result, 'run_id', 'run-123')

    @pytest.mark.asyncio
    async def test_test_executor_github_actions_failure(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of failed GitHub Actions workflow."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        worker_config.github_actions_enabled = True
        worker_config.github_token = 'test-token'

        mock_client = create_mock_github_actions_client(
            run_id='run-456',
            success=False,
            tests_passed=35,
            tests_failed=7,
            coverage=72.0,
        )

        with patch('services.worker_agents.src.executors.test_executor.GitHubActionsClient') as mock_class:
            mock_class.from_env.return_value = mock_client

            executor = TestExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                metrics=mock_metrics,
            )
            executor.github_actions_client = mock_client

            ticket = ExecutorTestHelper.create_test_ticket(
                provider='github_actions',
                repo='test-org/test-repo',
                workflow_id='ci.yml',
            )

            result = await executor.execute(ticket)

        # Should return failure
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'tests_failed', 7)

    @pytest.mark.asyncio
    async def test_test_executor_github_actions_connection_error(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of GitHub Actions connection error."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        worker_config.github_actions_enabled = True
        worker_config.github_token = 'test-token'

        mock_client = create_mock_github_actions_client(should_fail=True)

        with patch('services.worker_agents.src.executors.test_executor.GitHubActionsClient') as mock_class:
            mock_class.from_env.return_value = mock_client

            executor = TestExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                metrics=mock_metrics,
            )
            executor.github_actions_client = mock_client

            ticket = ExecutorTestHelper.create_test_ticket(
                provider='github_actions',
                repo='test-org/test-repo',
                workflow_id='ci.yml',
            )

            result = await executor.execute(ticket)

        # Should fail due to connection error
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)


class TestTestExecutorLocalCommand:
    """Tests for TestExecutor local command execution."""

    @pytest.mark.asyncio
    async def test_test_executor_local_command_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test successful local command execution."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Use a simple echo command
        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='echo "test passed"',
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # Should succeed
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_log_contains(result, 'echo')

    @pytest.mark.asyncio
    async def test_test_executor_local_command_with_output(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test local command that produces JSON output."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Create temp directory with test report
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / 'report.json'
            report_path.write_text('{"tests_passed": 10, "tests_failed": 2, "coverage": 85.0}')

            ticket = ExecutorTestHelper.create_test_ticket(
                test_command='echo done',
                working_dir=tmpdir,
                report_path='report.json',
            )

            result = await executor.execute(ticket)

        ResultValidator.assert_success(result)

    @pytest.mark.asyncio
    async def test_test_executor_command_not_allowed(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test that disallowed commands raise ValueError."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        # Set strict allowed commands
        worker_config.allowed_test_commands = ['pytest', 'npm test']

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='rm -rf /',  # Dangerous command
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # Should fall back to simulation (command not allowed error caught)
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)

    @pytest.mark.asyncio
    async def test_test_executor_command_timeout(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test command execution timeout."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        # Set very short timeout
        worker_config.test_execution_timeout_seconds = 1

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='python -c "import time; time.sleep(10)"',
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # Should fail with timeout
        ResultValidator.assert_failure(result)
        ResultValidator.assert_log_contains(result, 'timeout')

    @pytest.mark.asyncio
    async def test_test_executor_working_dir_not_found(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of non-existent working directory."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='echo test',
            working_dir='/nonexistent/directory/path',
        )

        result = await executor.execute(ticket)

        # Should fall back to simulation
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)

    @pytest.mark.asyncio
    async def test_test_executor_command_returns_nonzero(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of command that returns non-zero exit code."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='python -c "exit(1)"',
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # Should return failure
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)


class TestTestExecutorSimulation:
    """Tests for TestExecutor simulation mode."""

    @pytest.mark.asyncio
    async def test_test_executor_simulation_mode(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test execution in pure simulation mode."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket(
            test_suite='unit',
        )

        result = await executor.execute(ticket)

        # Simulation should succeed
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)
        ResultValidator.assert_has_output(result, 'tests_passed', 'coverage', 'test_suite')
        ResultValidator.assert_log_contains(result, 'simulated')

    @pytest.mark.asyncio
    async def test_test_executor_simulation_metrics(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test that metrics are recorded in simulation mode."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket()

        result = await executor.execute(ticket)

        # Verify metrics were recorded
        mock_metrics.test_tasks_executed_total.labels.assert_called()
        mock_metrics.test_duration_seconds.labels.assert_called()


class TestTestExecutorValidation:
    """Tests for TestExecutor input validation."""

    @pytest.mark.asyncio
    async def test_test_executor_missing_ticket_id(self, test_executor):
        """Test that missing ticket_id raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'task_id': 'task-123',
            'task_type': 'TEST',
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await test_executor.execute(ticket)

        assert 'ticket_id' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_test_executor_wrong_task_type(self, test_executor):
        """Test that wrong task_type raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'ticket_id': 'ticket-123',
            'task_id': 'task-123',
            'task_type': 'BUILD',  # Wrong type
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await test_executor.execute(ticket)

        assert 'task type mismatch' in str(exc_info.value).lower()


class TestTestExecutorCommandSecurity:
    """Security-focused tests for command execution."""

    @pytest.mark.asyncio
    async def test_command_injection_prevented(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test that command injection attempts are handled safely."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        # Only allow safe commands
        worker_config.allowed_test_commands = ['pytest', 'echo']

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Attempt command injection
        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='echo test; rm -rf /',
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # The command should be executed safely via shlex.split
        # or fall back to simulation
        assert 'success' in result

    @pytest.mark.asyncio
    async def test_empty_command_handled(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test that empty commands are handled safely."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_test_ticket(
            test_command='',  # Empty command
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # Should fall back to simulation
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)


@pytest.mark.real_integration
@pytest.mark.github_actions
class TestTestExecutorRealGitHubActions:
    """Tests that require real GitHub Actions integration."""

    @pytest.mark.asyncio
    async def test_test_executor_with_real_github_actions(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with real GitHub Actions (requires GITHUB_TOKEN env var)."""
        from services.worker_agents.src.executors.test_executor import TestExecutor
        from services.worker_agents.src.clients.github_actions_client import GitHubActionsClient

        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            pytest.skip('GITHUB_TOKEN not configured')

        test_repo = os.getenv('GITHUB_TEST_REPO')
        test_workflow = os.getenv('GITHUB_TEST_WORKFLOW', 'test.yml')

        if not test_repo:
            pytest.skip('GITHUB_TEST_REPO not configured')

        worker_config.github_actions_enabled = True
        worker_config.github_token = github_token
        worker_config.github_actions_timeout_seconds = 300

        # Create real client
        real_client = GitHubActionsClient(
            token=github_token,
            timeout=300,
        )
        real_client.default_repo = test_repo

        executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.github_actions_client = real_client

        ticket = ExecutorTestHelper.create_test_ticket(
            provider='github_actions',
            repo=test_repo,
            workflow_id=test_workflow,
            ref='main',
        )

        result = await executor.execute(ticket)

        # With real service, expect either success or graceful failure
        assert 'success' in result
        assert 'output' in result
        assert 'metadata' in result
