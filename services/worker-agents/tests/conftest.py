"""
Pytest configuration and fixtures for Worker Agents tests.

This module provides:
- Custom markers for test categorization
- Session-scoped fixtures for shared resources
- Fixtures for executor instances with mocked dependencies
- Fixtures for integration testing with real/mocked services
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Generator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Configuration from environment
CODE_FORGE_URL = os.getenv('CODE_FORGE_URL', 'http://localhost:8000')
ARGOCD_URL = os.getenv('ARGOCD_URL', 'http://localhost:8081')
ARGOCD_TOKEN = os.getenv('ARGOCD_TOKEN', 'test-token')
OPA_URL = os.getenv('OPA_URL', 'http://localhost:8181')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
SONARQUBE_URL = os.getenv('SONARQUBE_URL', 'http://localhost:9000')
SONARQUBE_TOKEN = os.getenv('SONARQUBE_TOKEN', '')
SNYK_TOKEN = os.getenv('SNYK_TOKEN', '')

# Test mode from environment
INTEGRATION_TEST_MODE = os.getenv('INTEGRATION_TEST_MODE', 'mock')  # mock | real | hybrid


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line('markers', 'integration: Integration tests')
    config.addinivalue_line('markers', 'real_integration: Tests that require real external services')
    config.addinivalue_line('markers', 'argocd: ArgoCD integration tests')
    config.addinivalue_line('markers', 'github_actions: GitHub Actions integration tests')
    config.addinivalue_line('markers', 'sonarqube: SonarQube integration tests')
    config.addinivalue_line('markers', 'opa: OPA integration tests')
    config.addinivalue_line('markers', 'trivy: Trivy integration tests')
    config.addinivalue_line('markers', 'snyk: Snyk integration tests')
    config.addinivalue_line('markers', 'checkov: Checkov integration tests')
    config.addinivalue_line('markers', 'code_forge: Code Forge integration tests')
    config.addinivalue_line('markers', 'slow: Slow tests (>1 minute)')


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Skip real_integration tests unless explicitly enabled."""
    if INTEGRATION_TEST_MODE == 'mock':
        skip_real = pytest.mark.skip(reason='Real integration tests disabled (INTEGRATION_TEST_MODE=mock)')
        for item in items:
            if 'real_integration' in item.keywords:
                item.add_marker(skip_real)


@pytest.fixture(scope='session')
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope='session', autouse=True)
def _configure_logging() -> None:
    """Configure logging for tests."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


# ============================================
# Settings Fixtures
# ============================================


@pytest.fixture
def worker_config():
    """
    Fixture providing a configurable WorkerAgentSettings instance.

    This creates a mock config that can be customized per test.
    """
    from services.worker_agents.src.config.settings import WorkerAgentSettings

    class TestSettings(WorkerAgentSettings):
        """Test settings with environment overrides."""

        class Config:
            env_prefix = 'TEST_'

    settings = TestSettings(
        service_name='worker-agents-test',
        code_forge_url=CODE_FORGE_URL,
        code_forge_enabled=True,
        argocd_url=ARGOCD_URL,
        argocd_token=ARGOCD_TOKEN,
        argocd_enabled=False,  # Disabled by default for safety
        opa_url=OPA_URL,
        opa_enabled=True,
        trivy_enabled=True,
        github_actions_enabled=bool(GITHUB_TOKEN),
        github_token=GITHUB_TOKEN,
        sonarqube_enabled=bool(SONARQUBE_TOKEN),
        sonarqube_url=SONARQUBE_URL,
        sonarqube_token=SONARQUBE_TOKEN,
        snyk_enabled=bool(SNYK_TOKEN),
        snyk_token=SNYK_TOKEN,
        checkov_enabled=True,
        allowed_test_commands=['pytest', 'npm test', 'go test', 'python', 'echo'],
        test_execution_timeout_seconds=60,
        code_forge_retry_attempts=3,
        retry_backoff_base_seconds=1,
        retry_backoff_max_seconds=10,
        vault_enabled=False,
    )
    return settings


@pytest.fixture
def worker_config_minimal():
    """Minimal config with all integrations disabled."""
    from services.worker_agents.src.config.settings import WorkerAgentSettings

    return WorkerAgentSettings(
        service_name='worker-agents-test-minimal',
        code_forge_enabled=False,
        argocd_enabled=False,
        opa_enabled=False,
        trivy_enabled=False,
        github_actions_enabled=False,
        sonarqube_enabled=False,
        snyk_enabled=False,
        checkov_enabled=False,
        vault_enabled=False,
    )


# ============================================
# Mock Client Fixtures
# ============================================


@pytest.fixture
def mock_vault_client():
    """Mock Vault client for tests."""
    client = MagicMock()
    client.read_secret = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_code_forge_client():
    """Mock Code Forge client for tests."""
    from neural_hive_integration.clients.code_forge_client import PipelineStatus

    client = AsyncMock()
    client.trigger_pipeline = AsyncMock(return_value='test-pipeline-123')
    client.get_pipeline_status = AsyncMock(return_value=PipelineStatus(
        pipeline_id='test-pipeline-123',
        status='completed',
        stage='deploy',
        duration_ms=30000,
        artifacts=[{'name': 'app.tar.gz', 'type': 'archive'}],
        sbom={'format': 'cyclonedx', 'components': []},
        signature='sig-abc123',
    ))
    client.wait_for_pipeline_completion = AsyncMock(return_value=PipelineStatus(
        pipeline_id='test-pipeline-123',
        status='completed',
        stage='deploy',
        duration_ms=30000,
        artifacts=[{'name': 'app.tar.gz', 'type': 'archive'}],
        sbom={'format': 'cyclonedx', 'components': []},
        signature='sig-abc123',
    ))
    client.submit_generation_request = AsyncMock(return_value='gen-request-456')
    return client


@pytest.fixture
def mock_metrics():
    """Mock metrics collector."""
    metrics = MagicMock()

    # Build metrics
    metrics.build_tasks_executed_total = MagicMock()
    metrics.build_tasks_executed_total.labels.return_value.inc = MagicMock()
    metrics.build_duration_seconds = MagicMock()
    metrics.build_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.build_artifacts_generated_total = MagicMock()
    metrics.build_artifacts_generated_total.labels.return_value.inc = MagicMock()
    metrics.code_forge_api_calls_total = MagicMock()
    metrics.code_forge_api_calls_total.labels.return_value.inc = MagicMock()

    # Deploy metrics
    metrics.deploy_tasks_executed_total = MagicMock()
    metrics.deploy_tasks_executed_total.labels.return_value.inc = MagicMock()
    metrics.deploy_duration_seconds = MagicMock()
    metrics.deploy_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.argocd_api_calls_total = MagicMock()
    metrics.argocd_api_calls_total.labels.return_value.inc = MagicMock()

    # Test metrics
    metrics.test_tasks_executed_total = MagicMock()
    metrics.test_tasks_executed_total.labels.return_value.inc = MagicMock()
    metrics.test_duration_seconds = MagicMock()
    metrics.test_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.tests_passed_total = MagicMock()
    metrics.tests_passed_total.labels.return_value.inc = MagicMock()
    metrics.tests_failed_total = MagicMock()
    metrics.tests_failed_total.labels.return_value.inc = MagicMock()
    metrics.test_coverage_percent = MagicMock()
    metrics.test_coverage_percent.labels.return_value.set = MagicMock()
    metrics.github_actions_api_calls_total = MagicMock()
    metrics.github_actions_api_calls_total.labels.return_value.inc = MagicMock()

    # Validate metrics
    metrics.validate_tasks_executed_total = MagicMock()
    metrics.validate_tasks_executed_total.labels.return_value.inc = MagicMock()
    metrics.validate_duration_seconds = MagicMock()
    metrics.validate_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.validate_violations_total = MagicMock()
    metrics.validate_violations_total.labels.return_value.inc = MagicMock()
    metrics.validate_tools_executed_total = MagicMock()
    metrics.validate_tools_executed_total.labels.return_value.inc = MagicMock()

    return metrics


# ============================================
# Executor Fixtures
# ============================================


@pytest.fixture
def build_executor(worker_config, mock_code_forge_client, mock_vault_client, mock_metrics):
    """BuildExecutor with mocked dependencies."""
    from services.worker_agents.src.executors.build_executor import BuildExecutor

    return BuildExecutor(
        config=worker_config,
        vault_client=mock_vault_client,
        code_forge_client=mock_code_forge_client,
        metrics=mock_metrics,
    )


@pytest.fixture
def build_executor_no_forge(worker_config_minimal, mock_vault_client, mock_metrics):
    """BuildExecutor without Code Forge client (simulation mode)."""
    from services.worker_agents.src.executors.build_executor import BuildExecutor

    return BuildExecutor(
        config=worker_config_minimal,
        vault_client=mock_vault_client,
        code_forge_client=None,
        metrics=mock_metrics,
    )


@pytest.fixture
def deploy_executor(worker_config, mock_vault_client, mock_metrics):
    """DeployExecutor with mocked dependencies."""
    from services.worker_agents.src.executors.deploy_executor import DeployExecutor

    return DeployExecutor(
        config=worker_config,
        vault_client=mock_vault_client,
        metrics=mock_metrics,
    )


@pytest.fixture
def deploy_executor_argocd_enabled(worker_config, mock_vault_client, mock_metrics):
    """DeployExecutor with ArgoCD enabled."""
    from services.worker_agents.src.executors.deploy_executor import DeployExecutor

    worker_config.argocd_enabled = True
    return DeployExecutor(
        config=worker_config,
        vault_client=mock_vault_client,
        metrics=mock_metrics,
    )


@pytest.fixture
def test_executor(worker_config, mock_vault_client, mock_metrics):
    """TestExecutor with mocked dependencies."""
    from services.worker_agents.src.executors.test_executor import TestExecutor

    return TestExecutor(
        config=worker_config,
        vault_client=mock_vault_client,
        metrics=mock_metrics,
    )


@pytest.fixture
def validate_executor(worker_config, mock_vault_client, mock_metrics):
    """ValidateExecutor with mocked dependencies."""
    from services.worker_agents.src.executors.validate_executor import ValidateExecutor

    return ValidateExecutor(
        config=worker_config,
        vault_client=mock_vault_client,
        metrics=mock_metrics,
    )


@pytest.fixture
def validate_executor_minimal(worker_config_minimal, mock_vault_client, mock_metrics):
    """ValidateExecutor without any validation tools enabled."""
    from services.worker_agents.src.executors.validate_executor import ValidateExecutor

    return ValidateExecutor(
        config=worker_config_minimal,
        vault_client=mock_vault_client,
        metrics=mock_metrics,
    )


# ============================================
# Test Ticket Fixtures
# ============================================


@pytest.fixture
def build_ticket():
    """Sample BUILD ticket for testing."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'BUILD',
        'parameters': {
            'artifact_id': 'test-artifact-123',
            'branch': 'main',
            'commit_sha': 'abc123def456',
            'build_args': {'debug': 'true'},
            'env_vars': {'NODE_ENV': 'test'},
        },
    }


@pytest.fixture
def deploy_ticket():
    """Sample DEPLOY ticket for testing."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'DEPLOY',
        'parameters': {
            'namespace': 'test-ns',
            'deployment_name': 'test-app',
            'image': 'test-image:v1.0',
            'replicas': 2,
            'repo_url': 'https://github.com/test/repo',
            'chart_path': 'charts/app',
            'revision': 'HEAD',
        },
    }


@pytest.fixture
def test_ticket():
    """Sample TEST ticket for testing."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'TEST',
        'parameters': {
            'test_suite': 'unit',
            'test_command': 'echo "tests passed"',
            'working_dir': '/tmp',
        },
    }


@pytest.fixture
def test_ticket_github_actions():
    """Sample TEST ticket for GitHub Actions."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'TEST',
        'parameters': {
            'provider': 'github_actions',
            'repo': 'test-org/test-repo',
            'workflow_id': 'ci.yml',
            'ref': 'main',
            'inputs': {'environment': 'test'},
            'test_suite': 'integration',
        },
    }


@pytest.fixture
def validate_ticket_policy():
    """Sample VALIDATE ticket for OPA policy validation."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'policy',
            'policy_path': 'policy/allow',
            'input_data': {'user': 'admin', 'action': 'read'},
        },
    }


@pytest.fixture
def validate_ticket_sast():
    """Sample VALIDATE ticket for SAST validation."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'sast',
            'working_dir': '/tmp',
        },
    }


@pytest.fixture
def validate_ticket_sonarqube():
    """Sample VALIDATE ticket for SonarQube validation."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'sonarqube',
            'project_key': 'test-project',
            'working_dir': '/tmp/src',
        },
    }


@pytest.fixture
def validate_ticket_snyk():
    """Sample VALIDATE ticket for Snyk validation."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'snyk',
            'manifest_path': '/tmp/package.json',
        },
    }


@pytest.fixture
def validate_ticket_iac():
    """Sample VALIDATE ticket for IaC/Checkov validation."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'iac',
            'working_dir': '/tmp/terraform',
        },
    }
