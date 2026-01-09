"""Unit tests for refactored TEST Executor with multiple providers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.executors.test_executor import TestExecutor
from src.clients.github_actions_client import WorkflowRunStatus
from src.clients.gitlab_ci_client import PipelineStatus
from src.clients.jenkins_client import JenkinsBuildStatus


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = MagicMock()
    config.test_execution_timeout_seconds = 600
    config.test_retry_attempts = 3
    config.github_actions_enabled = False
    config.gitlab_ci_enabled = False
    config.jenkins_enabled = False
    config.junit_xml_enabled = True
    config.coverage_report_enabled = True
    config.allowed_test_commands = ['pytest', 'npm test']
    return config


@pytest.fixture
def mock_metrics():
    """Create mock metrics."""
    metrics = MagicMock()
    metrics.test_tasks_executed_total = MagicMock()
    metrics.test_tasks_executed_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.test_duration_seconds = MagicMock()
    metrics.test_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
    metrics.tests_passed_total = MagicMock()
    metrics.tests_passed_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.tests_failed_total = MagicMock()
    metrics.tests_failed_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.test_coverage_percent = MagicMock()
    metrics.test_coverage_percent.labels = MagicMock(return_value=MagicMock(set=MagicMock()))
    metrics.github_actions_api_calls_total = MagicMock()
    metrics.github_actions_api_calls_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.gitlab_ci_api_calls_total = MagicMock()
    metrics.gitlab_ci_api_calls_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.jenkins_api_calls_total = MagicMock()
    metrics.jenkins_api_calls_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.test_report_parsing_total = MagicMock()
    metrics.test_report_parsing_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.coverage_report_parsing_total = MagicMock()
    metrics.coverage_report_parsing_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    return metrics


@pytest.fixture
def mock_github_actions_client():
    """Create mock GitHub Actions client."""
    client = AsyncMock()
    client.trigger_workflow = AsyncMock()
    client.wait_for_workflow = AsyncMock()
    client.get_test_results = AsyncMock()
    client.get_coverage_report = AsyncMock()
    return client


@pytest.fixture
def mock_gitlab_ci_client():
    """Create mock GitLab CI client."""
    client = AsyncMock()
    client.trigger_pipeline = AsyncMock()
    client.wait_for_pipeline = AsyncMock()
    client.get_test_report = AsyncMock()
    return client


@pytest.fixture
def mock_jenkins_client():
    """Create mock Jenkins client."""
    client = AsyncMock()
    client.trigger_build = AsyncMock()
    client.wait_for_build = AsyncMock()
    client.get_test_report = AsyncMock()
    client.get_coverage_report = AsyncMock()
    return client


@pytest.fixture
def test_executor(mock_config, mock_metrics, mock_github_actions_client, mock_gitlab_ci_client, mock_jenkins_client):
    """Create TEST executor with all clients."""
    return TestExecutor(
        config=mock_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        github_actions_client=mock_github_actions_client,
        gitlab_ci_client=mock_gitlab_ci_client,
        jenkins_client=mock_jenkins_client
    )


class TestTestExecutorInit:
    """Tests for TestExecutor initialization."""

    def test_init_with_all_clients(self, mock_config, mock_metrics, mock_github_actions_client, mock_gitlab_ci_client, mock_jenkins_client):
        """Test initialization with all clients."""
        executor = TestExecutor(
            config=mock_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            github_actions_client=mock_github_actions_client,
            gitlab_ci_client=mock_gitlab_ci_client,
            jenkins_client=mock_jenkins_client
        )

        assert executor.task_type == 'TEST'
        assert executor.github_actions_client == mock_github_actions_client
        assert executor.gitlab_ci_client == mock_gitlab_ci_client
        assert executor.jenkins_client == mock_jenkins_client

    def test_init_without_clients(self, mock_config, mock_metrics):
        """Test initialization without optional clients."""
        executor = TestExecutor(
            config=mock_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics
        )

        assert executor.github_actions_client is None
        assert executor.gitlab_ci_client is None
        assert executor.jenkins_client is None


class TestProviderSelection:
    """Tests for provider selection."""

    @pytest.mark.asyncio
    async def test_select_github_actions_provider(self, test_executor, mock_config):
        """Test GitHub Actions provider selection."""
        mock_config.github_actions_enabled = True
        test_executor.github_actions_client = AsyncMock()

        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'github_actions',
            'repository': 'owner/repo',
            'workflow_id': 'test.yml',
        }

        with patch.object(test_executor, '_execute_github_actions', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'status': 'success'}
            result = await test_executor.execute(ticket)

            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_gitlab_ci_provider(self, test_executor, mock_config):
        """Test GitLab CI provider selection."""
        mock_config.gitlab_ci_enabled = True
        test_executor.gitlab_ci_client = AsyncMock()

        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'gitlab_ci',
            'project_id': 123,
            'ref': 'main',
        }

        with patch.object(test_executor, '_execute_gitlab_ci', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'status': 'success'}
            result = await test_executor.execute(ticket)

            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_jenkins_provider(self, test_executor, mock_config):
        """Test Jenkins provider selection."""
        mock_config.jenkins_enabled = True
        test_executor.jenkins_client = AsyncMock()

        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'jenkins',
            'job_name': 'test-job',
        }

        with patch.object(test_executor, '_execute_jenkins', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'status': 'success'}
            result = await test_executor.execute(ticket)

            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_local_provider(self, test_executor):
        """Test local provider selection."""
        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'local',
            'command': 'pytest',
            'working_dir': '/app',
        }

        with patch.object(test_executor, '_execute_local', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'status': 'success'}
            result = await test_executor.execute(ticket)

            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_simulation(self, test_executor):
        """Test fallback to simulation when no provider available."""
        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'unknown_provider',
        }

        with patch.object(test_executor, '_execute_simulation', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'status': 'success', 'simulated': True}
            result = await test_executor.execute(ticket)

            mock_execute.assert_called_once()


class TestGitHubActionsExecution:
    """Tests for GitHub Actions execution."""

    @pytest.mark.asyncio
    async def test_execute_github_actions_success(self, test_executor, mock_github_actions_client, mock_metrics):
        """Test successful GitHub Actions execution."""
        mock_github_actions_client.trigger_workflow.return_value = {'id': 12345}
        mock_github_actions_client.wait_for_workflow.return_value = WorkflowRunStatus(
            run_id=12345,
            status='completed',
            conclusion='success',
            html_url='https://github.com/owner/repo/actions/runs/12345',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tests_passed=10,
            tests_failed=0,
            tests_skipped=0,
            coverage_percent=85.0
        )

        payload = {
            'repository': 'owner/repo',
            'workflow_id': 'test.yml',
            'ref': 'main',
        }

        result = await test_executor._execute_github_actions(payload)

        assert result['status'] == 'success'
        assert result['tests_passed'] == 10
        assert result['tests_failed'] == 0
        mock_github_actions_client.trigger_workflow.assert_called_once()
        mock_github_actions_client.wait_for_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_github_actions_failure(self, test_executor, mock_github_actions_client):
        """Test GitHub Actions execution with test failures."""
        mock_github_actions_client.trigger_workflow.return_value = {'id': 12345}
        mock_github_actions_client.wait_for_workflow.return_value = WorkflowRunStatus(
            run_id=12345,
            status='completed',
            conclusion='failure',
            html_url='https://github.com/owner/repo/actions/runs/12345',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tests_passed=8,
            tests_failed=2,
            tests_skipped=0,
            coverage_percent=75.0
        )

        payload = {
            'repository': 'owner/repo',
            'workflow_id': 'test.yml',
        }

        result = await test_executor._execute_github_actions(payload)

        assert result['status'] == 'failure'
        assert result['tests_failed'] == 2


class TestGitLabCIExecution:
    """Tests for GitLab CI execution."""

    @pytest.mark.asyncio
    async def test_execute_gitlab_ci_success(self, test_executor, mock_gitlab_ci_client):
        """Test successful GitLab CI execution."""
        mock_gitlab_ci_client.trigger_pipeline.return_value = {'id': 12345}
        mock_gitlab_ci_client.wait_for_pipeline.return_value = PipelineStatus(
            pipeline_id=12345,
            project_id=999,
            status='success',
            ref='main',
            sha='abc123',
            web_url='https://gitlab.com/project/-/pipelines/12345',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            duration=300
        )
        mock_gitlab_ci_client.get_test_report.return_value = {
            'total_count': 10,
            'success_count': 10,
            'failed_count': 0,
            'skipped_count': 0,
        }

        payload = {
            'project_id': 999,
            'ref': 'main',
        }

        result = await test_executor._execute_gitlab_ci(payload)

        assert result['status'] == 'success'
        mock_gitlab_ci_client.trigger_pipeline.assert_called_once()
        mock_gitlab_ci_client.wait_for_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_gitlab_ci_with_variables(self, test_executor, mock_gitlab_ci_client):
        """Test GitLab CI execution with variables."""
        mock_gitlab_ci_client.trigger_pipeline.return_value = {'id': 12345}
        mock_gitlab_ci_client.wait_for_pipeline.return_value = PipelineStatus(
            pipeline_id=12345,
            project_id=999,
            status='success',
            ref='main',
            sha='abc123',
            web_url='https://gitlab.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_gitlab_ci_client.get_test_report.return_value = {}

        payload = {
            'project_id': 999,
            'ref': 'feature-branch',
            'variables': {'CI_VAR': 'value'},
        }

        await test_executor._execute_gitlab_ci(payload)

        mock_gitlab_ci_client.trigger_pipeline.assert_called_once_with(
            project_id=999,
            ref='feature-branch',
            variables={'CI_VAR': 'value'}
        )


class TestJenkinsExecution:
    """Tests for Jenkins execution."""

    @pytest.mark.asyncio
    async def test_execute_jenkins_success(self, test_executor, mock_jenkins_client):
        """Test successful Jenkins execution."""
        mock_jenkins_client.trigger_build.return_value = {'queue_id': 100}
        mock_jenkins_client.wait_for_build.return_value = JenkinsBuildStatus(
            build_number=50,
            result='SUCCESS',
            building=False,
            url='https://jenkins.example.com/job/test/50/',
            duration=120000,
            timestamp=datetime.now(timezone.utc),
            tests_passed=20,
            tests_failed=0,
            tests_skipped=1
        )
        mock_jenkins_client.get_coverage_report.return_value = {
            'line_coverage': 80.0,
            'branch_coverage': 75.0,
        }

        payload = {
            'job_name': 'test-job',
        }

        result = await test_executor._execute_jenkins(payload)

        assert result['status'] == 'success'
        assert result['tests_passed'] == 20
        mock_jenkins_client.trigger_build.assert_called_once()
        mock_jenkins_client.wait_for_build.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_jenkins_with_parameters(self, test_executor, mock_jenkins_client):
        """Test Jenkins execution with build parameters."""
        mock_jenkins_client.trigger_build.return_value = {'queue_id': 100}
        mock_jenkins_client.wait_for_build.return_value = JenkinsBuildStatus(
            build_number=50,
            result='SUCCESS',
            building=False,
            url='https://jenkins.example.com/job/test/50/',
            duration=60000,
            timestamp=datetime.now(timezone.utc),
        )
        mock_jenkins_client.get_coverage_report.return_value = {}

        payload = {
            'job_name': 'test-job',
            'parameters': {'BRANCH': 'main', 'DEBUG': 'true'},
        }

        await test_executor._execute_jenkins(payload)

        mock_jenkins_client.trigger_build.assert_called_once_with(
            job_name='test-job',
            parameters={'BRANCH': 'main', 'DEBUG': 'true'}
        )


class TestLocalExecution:
    """Tests for local test execution."""

    @pytest.mark.asyncio
    async def test_execute_local_pytest_success(self, test_executor):
        """Test successful local pytest execution."""
        payload = {
            'command': 'pytest',
            'working_dir': '/app/tests',
            'args': ['-v', '--cov=src'],
        }

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b'test output', b'')
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await test_executor._execute_local(payload)

            assert result['status'] == 'success'
            assert result['return_code'] == 0

    @pytest.mark.asyncio
    async def test_execute_local_command_not_allowed(self, test_executor):
        """Test local execution with disallowed command."""
        payload = {
            'command': 'rm -rf /',
            'working_dir': '/app',
        }

        result = await test_executor._execute_local(payload)

        assert result['status'] == 'error'
        assert 'not allowed' in result.get('error', '').lower()


class TestSimulationExecution:
    """Tests for simulation mode."""

    @pytest.mark.asyncio
    async def test_execute_simulation(self, test_executor):
        """Test simulation execution."""
        payload = {
            'test_suite': 'unit',
        }

        result = await test_executor._execute_simulation(payload)

        assert result['status'] == 'success'
        assert result['simulated'] is True
        assert 'tests_passed' in result
        assert 'tests_failed' in result


class TestMetricsRecording:
    """Tests for metrics recording."""

    @pytest.mark.asyncio
    async def test_record_test_metrics_success(self, test_executor, mock_metrics):
        """Test metrics recording for successful tests."""
        result = {
            'status': 'success',
            'tests_passed': 10,
            'tests_failed': 0,
            'tests_skipped': 2,
            'coverage_percent': 85.0,
            'duration': 120.5,
        }

        test_executor._record_test_metrics(result, 'unit')

        mock_metrics.test_tasks_executed_total.labels.assert_called_with(status='success', suite='unit')
        mock_metrics.tests_passed_total.labels.assert_called_with(suite='unit')
        mock_metrics.test_coverage_percent.labels.assert_called_with(suite='unit')

    @pytest.mark.asyncio
    async def test_record_test_metrics_failure(self, test_executor, mock_metrics):
        """Test metrics recording for failed tests."""
        result = {
            'status': 'failure',
            'tests_passed': 8,
            'tests_failed': 2,
            'tests_skipped': 0,
        }

        test_executor._record_test_metrics(result, 'integration')

        mock_metrics.test_tasks_executed_total.labels.assert_called_with(status='failure', suite='integration')
        mock_metrics.tests_failed_total.labels.assert_called_with(suite='integration')


class TestRetryLogic:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self, test_executor, mock_github_actions_client):
        """Test retry on transient failure."""
        call_count = 0

        async def mock_trigger(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception('Transient error')
            return {'id': 12345}

        mock_github_actions_client.trigger_workflow = mock_trigger
        mock_github_actions_client.wait_for_workflow.return_value = WorkflowRunStatus(
            run_id=12345,
            status='completed',
            conclusion='success',
            html_url='https://github.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        payload = {
            'repository': 'owner/repo',
            'workflow_id': 'test.yml',
        }

        result = await test_executor._execute_github_actions(payload)

        assert call_count == 3
        assert result['status'] == 'success'

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, test_executor, mock_github_actions_client):
        """Test behavior when max retries exceeded."""
        mock_github_actions_client.trigger_workflow = AsyncMock(side_effect=Exception('Persistent error'))

        payload = {
            'repository': 'owner/repo',
            'workflow_id': 'test.yml',
        }

        result = await test_executor._execute_github_actions(payload)

        assert result['status'] == 'error'
        assert 'error' in result
