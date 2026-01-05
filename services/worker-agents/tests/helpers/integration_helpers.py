"""
Helper functions and classes for integration testing.

This module provides utilities for:
- Creating test tickets
- Validating executor results
- Polling for async conditions
- Mock service management
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

T = TypeVar('T')


@dataclass
class ExecutorTestResult:
    """Structured result from an executor test."""

    success: bool
    output: Dict[str, Any]
    metadata: Dict[str, Any]
    logs: List[str]
    simulated: bool = False
    duration_seconds: Optional[float] = None

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> 'ExecutorTestResult':
        """Create from executor result dict."""
        return cls(
            success=result.get('success', False),
            output=result.get('output', {}),
            metadata=result.get('metadata', {}),
            logs=result.get('logs', []),
            simulated=result.get('metadata', {}).get('simulated', True),
            duration_seconds=result.get('metadata', {}).get('duration_seconds'),
        )


class ExecutorTestHelper:
    """Helper class for creating and validating executor tests."""

    @staticmethod
    def create_ticket(
        task_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        ticket_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a test ticket with the given parameters.

        Args:
            task_type: The task type (BUILD, DEPLOY, TEST, VALIDATE)
            parameters: Optional parameters dict
            ticket_id: Optional specific ticket ID
            task_id: Optional specific task ID

        Returns:
            A ticket dict suitable for executor.execute()
        """
        ticket_id = ticket_id or str(uuid.uuid4())
        task_id = task_id or f'task-{ticket_id[:8]}'

        return {
            'ticket_id': ticket_id,
            'task_id': task_id,
            'task_type': task_type,
            'parameters': parameters or {},
        }

    @staticmethod
    def create_build_ticket(
        artifact_id: str = 'test-artifact',
        branch: str = 'main',
        commit_sha: str = 'abc123',
        **extra_params,
    ) -> Dict[str, Any]:
        """Create a BUILD ticket."""
        params = {
            'artifact_id': artifact_id,
            'branch': branch,
            'commit_sha': commit_sha,
            **extra_params,
        }
        return ExecutorTestHelper.create_ticket('BUILD', params)

    @staticmethod
    def create_deploy_ticket(
        namespace: str = 'default',
        deployment_name: str = 'test-app',
        image: str = 'test:latest',
        replicas: int = 1,
        **extra_params,
    ) -> Dict[str, Any]:
        """Create a DEPLOY ticket."""
        params = {
            'namespace': namespace,
            'deployment_name': deployment_name,
            'image': image,
            'replicas': replicas,
            **extra_params,
        }
        return ExecutorTestHelper.create_ticket('DEPLOY', params)

    @staticmethod
    def create_test_ticket(
        test_command: Optional[str] = None,
        test_suite: str = 'unit',
        working_dir: str = '/tmp',
        provider: Optional[str] = None,
        **extra_params,
    ) -> Dict[str, Any]:
        """Create a TEST ticket."""
        params = {
            'test_suite': test_suite,
            'working_dir': working_dir,
            **extra_params,
        }
        if test_command:
            params['test_command'] = test_command
        if provider:
            params['provider'] = provider
        return ExecutorTestHelper.create_ticket('TEST', params)

    @staticmethod
    def create_validate_ticket(
        validation_type: str = 'policy',
        **extra_params,
    ) -> Dict[str, Any]:
        """Create a VALIDATE ticket."""
        params = {
            'validation_type': validation_type,
            **extra_params,
        }
        return ExecutorTestHelper.create_ticket('VALIDATE', params)


class ResultValidator:
    """Helper class for validating executor results."""

    @staticmethod
    def assert_success(result: Dict[str, Any], message: str = '') -> None:
        """Assert that the result indicates success."""
        assert result.get('success') is True, f'Expected success=True. {message}'

    @staticmethod
    def assert_failure(result: Dict[str, Any], message: str = '') -> None:
        """Assert that the result indicates failure."""
        assert result.get('success') is False, f'Expected success=False. {message}'

    @staticmethod
    def assert_simulated(result: Dict[str, Any], expected: bool = True) -> None:
        """Assert the simulated flag matches expected value."""
        simulated = result.get('metadata', {}).get('simulated', None)
        assert simulated == expected, f'Expected simulated={expected}, got {simulated}'

    @staticmethod
    def assert_has_output(result: Dict[str, Any], *keys: str) -> None:
        """Assert that the output contains all specified keys."""
        output = result.get('output', {})
        for key in keys:
            assert key in output, f'Expected key "{key}" in output, got: {list(output.keys())}'

    @staticmethod
    def assert_output_value(result: Dict[str, Any], key: str, expected: Any) -> None:
        """Assert that a specific output value matches expected."""
        actual = result.get('output', {}).get(key)
        assert actual == expected, f'Expected output[{key}]={expected}, got {actual}'

    @staticmethod
    def assert_has_logs(result: Dict[str, Any], min_count: int = 1) -> None:
        """Assert that logs exist with at least min_count entries."""
        logs = result.get('logs', [])
        assert len(logs) >= min_count, f'Expected at least {min_count} logs, got {len(logs)}'

    @staticmethod
    def assert_log_contains(result: Dict[str, Any], substring: str) -> None:
        """Assert that at least one log entry contains the substring."""
        logs = result.get('logs', [])
        found = any(substring.lower() in log.lower() for log in logs)
        assert found, f'Expected log containing "{substring}" in: {logs}'

    @staticmethod
    def assert_metadata_executor(result: Dict[str, Any], executor_name: str) -> None:
        """Assert the executor name in metadata."""
        executor = result.get('metadata', {}).get('executor')
        assert executor == executor_name, f'Expected executor={executor_name}, got {executor}'

    @staticmethod
    def validate_build_result(result: Dict[str, Any], simulated: bool = False) -> None:
        """Validate a BUILD executor result."""
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, simulated)
        ResultValidator.assert_metadata_executor(result, 'BuildExecutor')
        ResultValidator.assert_has_logs(result)

        if simulated:
            ResultValidator.assert_has_output(result, 'artifact_url', 'build_id')
        else:
            ResultValidator.assert_has_output(result, 'pipeline_id', 'artifact_id')

    @staticmethod
    def validate_deploy_result(result: Dict[str, Any], simulated: bool = False) -> None:
        """Validate a DEPLOY executor result."""
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, simulated)
        ResultValidator.assert_metadata_executor(result, 'DeployExecutor')
        ResultValidator.assert_has_output(result, 'deployment_id', 'status', 'namespace')
        ResultValidator.assert_has_logs(result)

    @staticmethod
    def validate_test_result(result: Dict[str, Any], simulated: bool = False) -> None:
        """Validate a TEST executor result."""
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, simulated)
        ResultValidator.assert_metadata_executor(result, 'TestExecutor')
        ResultValidator.assert_has_output(result, 'tests_passed', 'test_suite')
        ResultValidator.assert_has_logs(result)

    @staticmethod
    def validate_validate_result(result: Dict[str, Any], simulated: bool = False) -> None:
        """Validate a VALIDATE executor result."""
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, simulated)
        ResultValidator.assert_metadata_executor(result, 'ValidateExecutor')
        ResultValidator.assert_has_output(result, 'validation_passed', 'validation_type')
        ResultValidator.assert_has_logs(result)


async def poll_until(
    condition: Callable[[], T],
    timeout_seconds: float = 30.0,
    poll_interval: float = 1.0,
    timeout_message: str = 'Condition not met within timeout',
) -> T:
    """
    Poll until a condition is met or timeout is reached.

    Args:
        condition: A callable that returns a truthy value when condition is met
        timeout_seconds: Maximum time to wait
        poll_interval: Time between polls
        timeout_message: Message to include in TimeoutError

    Returns:
        The return value of condition() when it returns truthy

    Raises:
        TimeoutError: If condition is not met within timeout
    """
    start_time = asyncio.get_event_loop().time()
    while True:
        result = condition()
        if result:
            return result

        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout_seconds:
            raise TimeoutError(f'{timeout_message} after {elapsed:.1f}s')

        await asyncio.sleep(poll_interval)


async def poll_async_until(
    condition: Callable[[], 'asyncio.Future[T]'],
    timeout_seconds: float = 30.0,
    poll_interval: float = 1.0,
    timeout_message: str = 'Condition not met within timeout',
) -> T:
    """
    Poll an async condition until it returns truthy or timeout is reached.

    Args:
        condition: An async callable that returns a truthy value when condition is met
        timeout_seconds: Maximum time to wait
        poll_interval: Time between polls
        timeout_message: Message to include in TimeoutError

    Returns:
        The return value of condition() when it returns truthy

    Raises:
        TimeoutError: If condition is not met within timeout
    """
    start_time = asyncio.get_event_loop().time()
    while True:
        result = await condition()
        if result:
            return result

        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout_seconds:
            raise TimeoutError(f'{timeout_message} after {elapsed:.1f}s')

        await asyncio.sleep(poll_interval)


@dataclass
class MetricsCollector:
    """Collects and validates metrics calls during tests."""

    calls: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, metric_name: str, labels: Dict[str, str], value: Any = None) -> None:
        """Record a metrics call."""
        self.calls.append({
            'name': metric_name,
            'labels': labels,
            'value': value,
        })

    def assert_metric_called(self, metric_name: str, **label_filters) -> None:
        """Assert that a metric was called with the specified labels."""
        matching = [
            c for c in self.calls
            if c['name'] == metric_name and all(
                c['labels'].get(k) == v for k, v in label_filters.items()
            )
        ]
        assert matching, f'Metric {metric_name} with labels {label_filters} not found in: {self.calls}'

    def assert_metric_not_called(self, metric_name: str) -> None:
        """Assert that a metric was not called."""
        matching = [c for c in self.calls if c['name'] == metric_name]
        assert not matching, f'Metric {metric_name} was called but should not have been: {matching}'

    def clear(self) -> None:
        """Clear recorded calls."""
        self.calls.clear()
