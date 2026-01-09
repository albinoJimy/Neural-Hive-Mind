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
# Para habilitar testes de integração real, configure:
#   export INTEGRATION_TEST_MODE=real
#   pytest tests/integration/ -m real_integration
INTEGRATION_TEST_MODE = os.getenv('INTEGRATION_TEST_MODE', 'mock')  # mock | real | hybrid


def check_service_availability(url: str, timeout: int = 5) -> bool:
    """
    Verifica se um serviço está disponível.

    Args:
        url: URL do serviço
        timeout: Timeout em segundos

    Returns:
        True se o serviço está disponível
    """
    try:
        import httpx
        response = httpx.get(url, timeout=timeout)
        return response.status_code < 500
    except Exception:
        return False


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


# ============================================
# Execute Executor Fixtures
# ============================================


@pytest.fixture
def execute_ticket():
    """Sample EXECUTE ticket for testing."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'EXECUTE',
        'parameters': {
            'command': 'echo',
            'args': ['hello', 'world'],
            'runtime': 'local',
            'timeout_seconds': 60,
        },
    }


@pytest.fixture
def execute_ticket_k8s():
    """Sample EXECUTE ticket for Kubernetes runtime."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'EXECUTE',
        'parameters': {
            'command': ['python', '-c', 'print("test")'],
            'runtime': 'k8s',
            'image': 'python:3.11-slim',
            'cpu_limit': '1000m',
            'memory_limit': '512Mi',
            'timeout_seconds': 300,
        },
    }


@pytest.fixture
def execute_ticket_docker():
    """Sample EXECUTE ticket for Docker runtime."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'EXECUTE',
        'parameters': {
            'command': ['echo', 'docker-test'],
            'runtime': 'docker',
            'image': 'alpine:latest',
            'cpu_limit': 1.0,
            'memory_limit': '256m',
            'timeout_seconds': 120,
        },
    }


@pytest.fixture
def execute_ticket_lambda():
    """Sample EXECUTE ticket for Lambda runtime."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'EXECUTE',
        'parameters': {
            'command': 'handler',
            'runtime': 'lambda',
            'function_name': 'neural-hive-executor',
            'timeout_seconds': 60,
        },
    }


@pytest.fixture
def mock_argocd_client():
    """Mock ArgoCD client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockHealthStatus:
        status: str = 'Healthy'
        message: str = ''

    @dataclass
    class MockSyncStatus:
        status: str = 'Synced'
        revision: str = 'abc123'

    @dataclass
    class MockApplicationStatus:
        name: str = 'test-app'
        health: MockHealthStatus = None
        sync: MockSyncStatus = None

        def __post_init__(self):
            if self.health is None:
                self.health = MockHealthStatus()
            if self.sync is None:
                self.sync = MockSyncStatus()

    client = AsyncMock()
    client.create_application = AsyncMock(return_value='test-app')
    client.wait_for_health = AsyncMock(return_value=MockApplicationStatus())
    client.get_application_status = AsyncMock(return_value=MockApplicationStatus())
    client.delete_application = AsyncMock(return_value=True)
    client.sync_application = AsyncMock(return_value=MockApplicationStatus())
    return client


@pytest.fixture
def mock_flux_client():
    """Mock Flux client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockKustomizationStatus:
        ready: bool = True
        lastAppliedRevision: str = 'main/abc123'

    client = AsyncMock()
    client.create_kustomization = AsyncMock(return_value='test-kust')
    client.wait_for_ready = AsyncMock(return_value=MockKustomizationStatus())
    client.delete_kustomization = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_github_actions_client():
    """Mock GitHub Actions client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockWorkflowRunStatus:
        run_id: int = 12345
        status: str = 'completed'
        conclusion: str = 'success'
        success: bool = True
        passed: int = 50
        failed: int = 0
        skipped: int = 2
        coverage: float = 87.5
        duration_seconds: float = 120.0
        html_url: str = 'https://github.com/owner/repo/actions/runs/12345'
        logs: list = None

        def __post_init__(self):
            if self.logs is None:
                self.logs = ['Test run started', 'All tests passed']

    client = AsyncMock()
    client.trigger_workflow = AsyncMock(return_value=12345)
    client.wait_for_run = AsyncMock(return_value=MockWorkflowRunStatus())
    client.get_test_results = AsyncMock(return_value={'passed': 50, 'failed': 0})
    client.default_repo = 'owner/repo'
    return client


@pytest.fixture
def mock_gitlab_ci_client():
    """Mock GitLab CI client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockPipelineStatus:
        pipeline_id: int = 54321
        status: str = 'success'
        success: bool = True
        tests_passed: int = 75
        tests_failed: int = 0
        tests_skipped: int = 3
        tests_errors: int = 0
        coverage: float = 82.0
        duration_seconds: float = 180.0
        web_url: str = 'https://gitlab.com/project/-/pipelines/54321'
        logs: list = None

        def __post_init__(self):
            if self.logs is None:
                self.logs = ['Pipeline started', 'All jobs passed']

    client = AsyncMock()
    client.trigger_pipeline = AsyncMock(return_value=54321)
    client.wait_for_pipeline = AsyncMock(return_value=MockPipelineStatus())
    client.get_test_report = AsyncMock(return_value={'passed': 75, 'failed': 0})
    client.download_and_parse_artifacts = AsyncMock(return_value={
        'tests_passed': 75, 'tests_failed': 0, 'tests_skipped': 3, 'tests_errors': 0
    })
    return client


@pytest.fixture
def mock_jenkins_client():
    """Mock Jenkins client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockJenkinsBuildStatus:
        build_number: int = 100
        status: str = 'SUCCESS'
        success: bool = True
        tests_passed: int = 60
        tests_failed: int = 0
        tests_skipped: int = 5
        coverage: float = 78.5
        duration_seconds: float = 90.0
        url: str = 'https://jenkins.example.com/job/test-job/100/'
        logs: list = None

        def __post_init__(self):
            if self.logs is None:
                self.logs = ['Build started', 'Tests executed']

    client = AsyncMock()
    client.trigger_job = AsyncMock(return_value=500)
    client.wait_for_build_number = AsyncMock(return_value=100)
    client.wait_for_build = AsyncMock(return_value=MockJenkinsBuildStatus())
    client.get_test_report = AsyncMock(return_value={'passed': 60, 'failed': 0})
    return client


@pytest.fixture
def mock_opa_client():
    """Mock OPA client for integration tests."""
    from dataclasses import dataclass
    from enum import Enum

    class MockViolationSeverity(Enum):
        CRITICAL = 'CRITICAL'
        HIGH = 'HIGH'
        MEDIUM = 'MEDIUM'
        LOW = 'LOW'

    @dataclass
    class MockViolation:
        rule_id: str = 'rule-001'
        message: str = 'Test violation'
        severity: MockViolationSeverity = MockViolationSeverity.MEDIUM
        resource: str = None
        location: str = None

    @dataclass
    class MockPolicyEvaluationResponse:
        allow: bool = True
        violations: list = None
        metadata: dict = None

        def __post_init__(self):
            if self.violations is None:
                self.violations = []
            if self.metadata is None:
                self.metadata = {}

    client = AsyncMock()
    client.evaluate_policy = AsyncMock(return_value=MockPolicyEvaluationResponse())
    client.count_violations_by_severity = MagicMock(return_value={
        MockViolationSeverity.CRITICAL: 0,
        MockViolationSeverity.HIGH: 0,
        MockViolationSeverity.MEDIUM: 0,
        MockViolationSeverity.LOW: 0,
    })
    return client


@pytest.fixture
def mock_k8s_jobs_client():
    """Mock Kubernetes Jobs client for integration tests."""
    from dataclasses import dataclass
    from enum import Enum

    class MockK8sJobStatus(Enum):
        PENDING = 'pending'
        RUNNING = 'running'
        SUCCEEDED = 'succeeded'
        FAILED = 'failed'

    @dataclass
    class MockK8sJobResult:
        job_name: str = 'test-job-abc123'
        pod_name: str = 'test-job-abc123-pod'
        status: MockK8sJobStatus = MockK8sJobStatus.SUCCEEDED
        exit_code: int = 0
        logs: str = 'hello world'
        duration_ms: int = 5000

    client = AsyncMock()
    client.execute_job = AsyncMock(return_value=MockK8sJobResult())
    return client


@pytest.fixture
def mock_docker_runtime_client():
    """Mock Docker runtime client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockDockerExecutionResult:
        container_id: str = 'abc123def456'
        exit_code: int = 0
        stdout: str = 'docker-test'
        stderr: str = ''
        duration_ms: int = 3000
        image_pulled: bool = False

    client = AsyncMock()
    client.execute_command = AsyncMock(return_value=MockDockerExecutionResult())
    return client


@pytest.fixture
def mock_lambda_runtime_client():
    """Mock Lambda runtime client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockLambdaResponse:
        exit_code: int = 0
        stdout: str = 'lambda result'
        stderr: str = ''

    @dataclass
    class MockLambdaInvocationResult:
        request_id: str = 'req-abc123'
        status_code: int = 200
        function_error: str = None
        response: MockLambdaResponse = None
        duration_ms: int = 1500
        billed_duration_ms: int = 2000
        memory_used_mb: int = 128

        def __post_init__(self):
            if self.response is None:
                self.response = MockLambdaResponse()

    client = AsyncMock()
    client.invoke_lambda = AsyncMock(return_value=MockLambdaInvocationResult())
    return client


@pytest.fixture
def mock_local_runtime_client():
    """Mock Local runtime client for integration tests."""
    from dataclasses import dataclass

    @dataclass
    class MockLocalExecutionResult:
        exit_code: int = 0
        stdout: str = 'local output'
        stderr: str = ''
        command_executed: str = 'echo hello world'
        pid: int = 12345
        duration_ms: int = 100

    client = AsyncMock()
    client.execute_local = AsyncMock(return_value=MockLocalExecutionResult())
    return client


@pytest.fixture
def execute_executor(worker_config, mock_vault_client, mock_metrics):
    """ExecuteExecutor with mocked dependencies."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    return ExecuteExecutor(
        config=worker_config,
        vault_client=mock_vault_client,
        metrics=mock_metrics,
    )
