"""
Fixtures for executor instances with various configurations.

This module provides parametrized fixtures for testing executors
with different client configurations and modes.
"""

import pytest
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

from neural_hive_integration.clients.code_forge_client import PipelineStatus


def create_pipeline_status(
    pipeline_id: str = 'test-pipeline-123',
    status: str = 'completed',
    stage: str = 'deploy',
    duration_ms: int = 30000,
    artifacts: Optional[list] = None,
    sbom: Optional[Dict] = None,
    signature: Optional[str] = None,
) -> PipelineStatus:
    """Create a PipelineStatus for testing."""
    return PipelineStatus(
        pipeline_id=pipeline_id,
        status=status,
        stage=stage,
        duration_ms=duration_ms,
        artifacts=artifacts or [{'name': 'app.tar.gz', 'type': 'archive'}],
        sbom=sbom or {'format': 'cyclonedx', 'components': []},
        signature=signature or 'sig-abc123',
    )


def create_mock_code_forge_client(
    pipeline_id: str = 'test-pipeline-123',
    status: str = 'completed',
    should_fail: bool = False,
    fail_after_retries: int = 0,
) -> AsyncMock:
    """
    Create a mock Code Forge client with configurable behavior.

    Args:
        pipeline_id: The pipeline ID to return
        status: The final pipeline status
        should_fail: Whether the client should raise exceptions
        fail_after_retries: Number of failures before success (0 = always fail if should_fail)
    """
    client = AsyncMock()
    call_count = {'trigger': 0, 'status': 0}

    async def trigger_with_retry(*args, **kwargs):
        call_count['trigger'] += 1
        if should_fail:
            if fail_after_retries == 0 or call_count['trigger'] <= fail_after_retries:
                raise ConnectionError('Code Forge unavailable')
        return pipeline_id

    async def wait_for_completion(*args, **kwargs):
        if status == 'timeout':
            return create_pipeline_status(pipeline_id=pipeline_id, status='timeout', stage='pending')
        return create_pipeline_status(pipeline_id=pipeline_id, status=status)

    client.trigger_pipeline = AsyncMock(side_effect=trigger_with_retry)
    client.wait_for_pipeline_completion = AsyncMock(side_effect=wait_for_completion)
    client.get_pipeline_status = AsyncMock(return_value=create_pipeline_status(pipeline_id=pipeline_id, status=status))
    client.submit_generation_request = AsyncMock(return_value='gen-request-456')

    return client


def create_mock_github_actions_client(
    run_id: str = 'run-123',
    success: bool = True,
    tests_passed: int = 10,
    tests_failed: int = 0,
    coverage: float = 85.0,
    should_fail: bool = False,
) -> AsyncMock:
    """Create a mock GitHub Actions client."""
    from services.worker_agents.src.clients.github_actions_client import WorkflowRunStatus

    client = AsyncMock()

    async def trigger_workflow(*args, **kwargs):
        if should_fail:
            raise ConnectionError('GitHub Actions unavailable')
        return run_id

    async def wait_for_run(*args, **kwargs):
        return WorkflowRunStatus(
            run_id=run_id,
            status='completed',
            conclusion='success' if success else 'failure',
            passed=tests_passed,
            failed=tests_failed,
            coverage=coverage,
            duration_seconds=120.0,
            logs=['Test run completed'],
        )

    client.trigger_workflow = AsyncMock(side_effect=trigger_workflow)
    client.wait_for_run = AsyncMock(side_effect=wait_for_run)
    client.get_workflow_run = AsyncMock(return_value=WorkflowRunStatus(
        run_id=run_id,
        status='completed',
        conclusion='success' if success else 'failure',
        passed=tests_passed,
        failed=tests_failed,
        coverage=coverage,
        duration_seconds=120.0,
        logs=['Test run completed'],
    ))

    return client


def create_mock_sonarqube_client(
    passed: bool = True,
    issues: Optional[list] = None,
) -> AsyncMock:
    """Create a mock SonarQube client."""
    from services.worker_agents.src.clients.sonarqube_client import SonarQubeAnalysis

    client = AsyncMock()
    client.trigger_analysis = AsyncMock(return_value=SonarQubeAnalysis(
        task_id='task-123',
        passed=passed,
        issues=issues or [],
        duration_seconds=15.0,
        logs=['Analysis completed'],
    ))
    return client


def create_mock_snyk_client(
    passed: bool = True,
    vulnerabilities: Optional[list] = None,
) -> AsyncMock:
    """Create a mock Snyk client."""
    from services.worker_agents.src.clients.snyk_client import SnykReport

    client = AsyncMock()
    client.test_dependencies = AsyncMock(return_value=SnykReport(
        passed=passed,
        vulnerabilities=vulnerabilities or [],
        duration_seconds=5.0,
        logs=['Snyk scan completed'],
    ))
    return client


def create_mock_checkov_client(
    passed: bool = True,
    findings: Optional[list] = None,
) -> AsyncMock:
    """Create a mock Checkov client."""
    from services.worker_agents.src.clients.checkov_client import CheckovReport

    client = AsyncMock()
    client.scan_iac = AsyncMock(return_value=CheckovReport(
        passed=passed,
        findings=findings or [],
        duration_seconds=10.0,
        logs=['Checkov scan completed'],
    ))
    return client


@pytest.fixture
def mock_code_forge_success():
    """Mock Code Forge client that succeeds."""
    return create_mock_code_forge_client(status='completed')


@pytest.fixture
def mock_code_forge_failed():
    """Mock Code Forge client where pipeline fails."""
    return create_mock_code_forge_client(status='failed')


@pytest.fixture
def mock_code_forge_timeout():
    """Mock Code Forge client that times out."""
    return create_mock_code_forge_client(status='timeout')


@pytest.fixture
def mock_code_forge_connection_error():
    """Mock Code Forge client that fails with connection error."""
    return create_mock_code_forge_client(should_fail=True)


@pytest.fixture
def mock_code_forge_retry_success():
    """Mock Code Forge client that fails twice then succeeds."""
    return create_mock_code_forge_client(should_fail=True, fail_after_retries=2)


@pytest.fixture
def mock_github_actions_success():
    """Mock GitHub Actions client that succeeds."""
    return create_mock_github_actions_client(success=True)


@pytest.fixture
def mock_github_actions_failed():
    """Mock GitHub Actions client where workflow fails."""
    return create_mock_github_actions_client(success=False, tests_failed=5)


@pytest.fixture
def mock_github_actions_connection_error():
    """Mock GitHub Actions client that fails with connection error."""
    return create_mock_github_actions_client(should_fail=True)


@pytest.fixture
def mock_sonarqube_success():
    """Mock SonarQube client that passes."""
    return create_mock_sonarqube_client(passed=True)


@pytest.fixture
def mock_sonarqube_failed():
    """Mock SonarQube client with issues."""
    return create_mock_sonarqube_client(
        passed=False,
        issues=[{'key': 'issue1', 'severity': 'CRITICAL', 'message': 'SQL Injection'}],
    )


@pytest.fixture
def mock_snyk_success():
    """Mock Snyk client that passes."""
    return create_mock_snyk_client(passed=True)


@pytest.fixture
def mock_snyk_failed():
    """Mock Snyk client with vulnerabilities."""
    return create_mock_snyk_client(
        passed=False,
        vulnerabilities=[{'id': 'SNYK-123', 'severity': 'high', 'title': 'Prototype Pollution'}],
    )


@pytest.fixture
def mock_checkov_success():
    """Mock Checkov client that passes."""
    return create_mock_checkov_client(passed=True)


@pytest.fixture
def mock_checkov_failed():
    """Mock Checkov client with findings."""
    return create_mock_checkov_client(
        passed=False,
        findings=[{'check_id': 'CKV_AWS_1', 'severity': 'HIGH', 'resource': 's3_bucket'}],
    )
