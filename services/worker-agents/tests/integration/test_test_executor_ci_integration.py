"""Integration tests for TEST Executor with CI providers.

These tests verify the integration between the TEST Executor and
the various CI providers (GitHub Actions, GitLab CI, Jenkins).

Note: These tests require environment variables or mocks for the
actual CI provider APIs. In CI environments, they use mocked responses.
"""
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from services.worker_agents.src.executors.test_executor import TestExecutor
from services.worker_agents.src.clients.github_actions_client import GitHubActionsClient, WorkflowRunStatus
from services.worker_agents.src.clients.gitlab_ci_client import GitLabCIClient, PipelineStatus
from services.worker_agents.src.clients.jenkins_client import JenkinsClient, JenkinsBuildStatus
from services.worker_agents.src.config.settings import WorkerAgentSettings


@pytest.fixture
def integration_config():
    """Create configuration for integration tests."""
    return WorkerAgentSettings(
        environment='test',
        test_execution_timeout_seconds=300,
        test_retry_attempts=2,
        github_actions_enabled=True,
        github_api_url='https://api.github.com',
        github_token=os.getenv('GITHUB_TOKEN', 'test-token'),
        github_actions_timeout_seconds=300,
        gitlab_ci_enabled=True,
        gitlab_url='https://gitlab.com',
        gitlab_token=os.getenv('GITLAB_TOKEN', 'test-token'),
        gitlab_timeout_seconds=300,
        jenkins_enabled=True,
        jenkins_url=os.getenv('JENKINS_URL', 'https://jenkins.example.com'),
        jenkins_user=os.getenv('JENKINS_USER', 'test-user'),
        jenkins_token=os.getenv('JENKINS_TOKEN', 'test-token'),
        jenkins_timeout_seconds=300,
        junit_xml_enabled=True,
        coverage_report_enabled=True,
        kafka_schema_registry_url='http://localhost:8081',
        otel_exporter_endpoint='http://localhost:4317',
    )


@pytest.fixture
def mock_metrics():
    """Create mock metrics for integration tests."""
    metrics = MagicMock()

    for metric_name in [
        'test_tasks_executed_total', 'test_duration_seconds',
        'tests_passed_total', 'tests_failed_total', 'test_coverage_percent',
        'github_actions_api_calls_total', 'gitlab_ci_api_calls_total',
        'jenkins_api_calls_total', 'test_report_parsing_total',
        'coverage_report_parsing_total'
    ]:
        metric = MagicMock()
        metric.labels = MagicMock(return_value=MagicMock(
            inc=MagicMock(),
            observe=MagicMock(),
            set=MagicMock()
        ))
        setattr(metrics, metric_name, metric)

    return metrics


class TestGitHubActionsIntegration:
    """Integration tests for GitHub Actions provider."""

    @pytest.fixture
    def github_client(self, integration_config):
        """Create GitHub Actions client."""
        return GitHubActionsClient.from_env(integration_config)

    @pytest.fixture
    def executor_with_github(self, integration_config, mock_metrics, github_client):
        """Create executor with GitHub Actions client."""
        return TestExecutor(
            config=integration_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            github_actions_client=github_client
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_github_actions_workflow_trigger(self, executor_with_github):
        """Test triggering a GitHub Actions workflow."""
        with patch.object(executor_with_github.github_actions_client, 'trigger_workflow', new_callable=AsyncMock) as mock_trigger:
            with patch.object(executor_with_github.github_actions_client, 'wait_for_workflow', new_callable=AsyncMock) as mock_wait:
                mock_trigger.return_value = {'id': 12345}
                mock_wait.return_value = WorkflowRunStatus(
                    run_id=12345,
                    status='completed',
                    conclusion='success',
                    html_url='https://github.com/owner/repo/actions/runs/12345',
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    tests_passed=50,
                    tests_failed=0,
                    tests_skipped=2,
                    coverage_percent=87.5
                )

                ticket = MagicMock()
                ticket.ticket_id = 'test-ticket-001'
                ticket.task_payload = {
                    'test_provider': 'github_actions',
                    'repository': 'owner/repo',
                    'workflow_id': 'test.yml',
                    'ref': 'main',
                    'inputs': {'debug': 'true'}
                }

                result = await executor_with_github.execute(ticket)

                assert result['status'] == 'success'
                assert result['tests_passed'] == 50
                assert result['coverage_percent'] == 87.5
                mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_github_actions_with_test_artifacts(self, executor_with_github):
        """Test GitHub Actions with test report artifacts."""
        with patch.object(executor_with_github.github_actions_client, 'trigger_workflow', new_callable=AsyncMock) as mock_trigger:
            with patch.object(executor_with_github.github_actions_client, 'wait_for_workflow', new_callable=AsyncMock) as mock_wait:
                with patch.object(executor_with_github.github_actions_client, 'get_test_results', new_callable=AsyncMock) as mock_results:
                    mock_trigger.return_value = {'id': 12345}
                    mock_wait.return_value = WorkflowRunStatus(
                        run_id=12345,
                        status='completed',
                        conclusion='success',
                        html_url='https://github.com',
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    mock_results.return_value = {
                        'total': 100,
                        'passed': 95,
                        'failed': 3,
                        'skipped': 2,
                    }

                    ticket = MagicMock()
                    ticket.ticket_id = 'test-ticket-002'
                    ticket.task_payload = {
                        'test_provider': 'github_actions',
                        'repository': 'owner/repo',
                        'workflow_id': 'test.yml',
                        'collect_artifacts': True,
                    }

                    result = await executor_with_github.execute(ticket)

                    assert result['status'] == 'success'


class TestGitLabCIIntegration:
    """Integration tests for GitLab CI provider."""

    @pytest.fixture
    def gitlab_client(self, integration_config):
        """Create GitLab CI client."""
        return GitLabCIClient.from_env(integration_config)

    @pytest.fixture
    def executor_with_gitlab(self, integration_config, mock_metrics, gitlab_client):
        """Create executor with GitLab CI client."""
        return TestExecutor(
            config=integration_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            gitlab_ci_client=gitlab_client
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_gitlab_ci_pipeline_trigger(self, executor_with_gitlab):
        """Test triggering a GitLab CI pipeline."""
        with patch.object(executor_with_gitlab.gitlab_ci_client, 'trigger_pipeline', new_callable=AsyncMock) as mock_trigger:
            with patch.object(executor_with_gitlab.gitlab_ci_client, 'wait_for_pipeline', new_callable=AsyncMock) as mock_wait:
                with patch.object(executor_with_gitlab.gitlab_ci_client, 'get_test_report', new_callable=AsyncMock) as mock_report:
                    mock_trigger.return_value = {'id': 54321, 'web_url': 'https://gitlab.com/project/-/pipelines/54321'}
                    mock_wait.return_value = PipelineStatus(
                        pipeline_id=54321,
                        project_id=999,
                        status='success',
                        ref='main',
                        sha='abc123def',
                        web_url='https://gitlab.com/project/-/pipelines/54321',
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                        duration=180
                    )
                    mock_report.return_value = {
                        'total_count': 75,
                        'success_count': 73,
                        'failed_count': 2,
                        'skipped_count': 0,
                    }

                    ticket = MagicMock()
                    ticket.ticket_id = 'test-ticket-003'
                    ticket.task_payload = {
                        'test_provider': 'gitlab_ci',
                        'project_id': 999,
                        'ref': 'main',
                        'variables': {'CI_DEBUG': 'true'}
                    }

                    result = await executor_with_gitlab.execute(ticket)

                    assert result['status'] == 'success'
                    mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_gitlab_ci_pipeline_failure(self, executor_with_gitlab):
        """Test GitLab CI pipeline with failures."""
        with patch.object(executor_with_gitlab.gitlab_ci_client, 'trigger_pipeline', new_callable=AsyncMock) as mock_trigger:
            with patch.object(executor_with_gitlab.gitlab_ci_client, 'wait_for_pipeline', new_callable=AsyncMock) as mock_wait:
                with patch.object(executor_with_gitlab.gitlab_ci_client, 'get_test_report', new_callable=AsyncMock) as mock_report:
                    mock_trigger.return_value = {'id': 54322}
                    mock_wait.return_value = PipelineStatus(
                        pipeline_id=54322,
                        project_id=999,
                        status='failed',
                        ref='feature-branch',
                        sha='xyz789',
                        web_url='https://gitlab.com/project/-/pipelines/54322',
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    mock_report.return_value = {
                        'total_count': 50,
                        'success_count': 40,
                        'failed_count': 10,
                        'skipped_count': 0,
                    }

                    ticket = MagicMock()
                    ticket.ticket_id = 'test-ticket-004'
                    ticket.task_payload = {
                        'test_provider': 'gitlab_ci',
                        'project_id': 999,
                        'ref': 'feature-branch',
                    }

                    result = await executor_with_gitlab.execute(ticket)

                    assert result['status'] == 'failure'
                    assert result.get('tests_failed', 0) > 0


class TestJenkinsIntegration:
    """Integration tests for Jenkins provider."""

    @pytest.fixture
    def jenkins_client(self, integration_config):
        """Create Jenkins client."""
        return JenkinsClient.from_env(integration_config)

    @pytest.fixture
    def executor_with_jenkins(self, integration_config, mock_metrics, jenkins_client):
        """Create executor with Jenkins client."""
        return TestExecutor(
            config=integration_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            jenkins_client=jenkins_client
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_jenkins_build_trigger(self, executor_with_jenkins):
        """Test triggering a Jenkins build."""
        with patch.object(executor_with_jenkins.jenkins_client, 'trigger_build', new_callable=AsyncMock) as mock_trigger:
            with patch.object(executor_with_jenkins.jenkins_client, 'wait_for_build', new_callable=AsyncMock) as mock_wait:
                with patch.object(executor_with_jenkins.jenkins_client, 'get_coverage_report', new_callable=AsyncMock) as mock_coverage:
                    mock_trigger.return_value = {'queue_id': 500}
                    mock_wait.return_value = JenkinsBuildStatus(
                        build_number=100,
                        result='SUCCESS',
                        building=False,
                        url='https://jenkins.example.com/job/test-job/100/',
                        duration=90000,
                        timestamp=datetime.now(timezone.utc),
                        tests_passed=60,
                        tests_failed=0,
                        tests_skipped=5
                    )
                    mock_coverage.return_value = {
                        'line_coverage': 82.5,
                        'branch_coverage': 70.0,
                    }

                    ticket = MagicMock()
                    ticket.ticket_id = 'test-ticket-005'
                    ticket.task_payload = {
                        'test_provider': 'jenkins',
                        'job_name': 'test-job',
                        'parameters': {'BRANCH': 'main'}
                    }

                    result = await executor_with_jenkins.execute(ticket)

                    assert result['status'] == 'success'
                    assert result['tests_passed'] == 60
                    mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_jenkins_parameterized_build(self, executor_with_jenkins):
        """Test Jenkins parameterized build."""
        with patch.object(executor_with_jenkins.jenkins_client, 'trigger_build', new_callable=AsyncMock) as mock_trigger:
            with patch.object(executor_with_jenkins.jenkins_client, 'wait_for_build', new_callable=AsyncMock) as mock_wait:
                with patch.object(executor_with_jenkins.jenkins_client, 'get_coverage_report', new_callable=AsyncMock) as mock_coverage:
                    mock_trigger.return_value = {'queue_id': 501}
                    mock_wait.return_value = JenkinsBuildStatus(
                        build_number=101,
                        result='SUCCESS',
                        building=False,
                        url='https://jenkins.example.com/job/test-job/101/',
                        duration=120000,
                        timestamp=datetime.now(timezone.utc),
                    )
                    mock_coverage.return_value = {}

                    ticket = MagicMock()
                    ticket.ticket_id = 'test-ticket-006'
                    ticket.task_payload = {
                        'test_provider': 'jenkins',
                        'job_name': 'parameterized-job',
                        'parameters': {
                            'BRANCH': 'feature-x',
                            'TEST_SUITE': 'integration',
                            'DEBUG': 'true'
                        }
                    }

                    result = await executor_with_jenkins.execute(ticket)

                    assert result['status'] == 'success'
                    mock_trigger.assert_called_once_with(
                        job_name='parameterized-job',
                        parameters={
                            'BRANCH': 'feature-x',
                            'TEST_SUITE': 'integration',
                            'DEBUG': 'true'
                        }
                    )


class TestMultiProviderIntegration:
    """Integration tests for multi-provider scenarios."""

    @pytest.fixture
    def executor_all_providers(self, integration_config, mock_metrics):
        """Create executor with all providers."""
        github_client = MagicMock(spec=GitHubActionsClient)
        gitlab_client = MagicMock(spec=GitLabCIClient)
        jenkins_client = MagicMock(spec=JenkinsClient)

        return TestExecutor(
            config=integration_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            github_actions_client=github_client,
            gitlab_ci_client=gitlab_client,
            jenkins_client=jenkins_client
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_provider_selection_github(self, executor_all_providers):
        """Test correct provider selection for GitHub Actions."""
        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'github_actions',
            'repository': 'owner/repo',
            'workflow_id': 'test.yml',
        }

        with patch.object(executor_all_providers, '_execute_github_actions', new_callable=AsyncMock) as mock_github:
            mock_github.return_value = {'status': 'success'}
            await executor_all_providers.execute(ticket)
            mock_github.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_provider_selection_gitlab(self, executor_all_providers):
        """Test correct provider selection for GitLab CI."""
        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'gitlab_ci',
            'project_id': 123,
            'ref': 'main',
        }

        with patch.object(executor_all_providers, '_execute_gitlab_ci', new_callable=AsyncMock) as mock_gitlab:
            mock_gitlab.return_value = {'status': 'success'}
            await executor_all_providers.execute(ticket)
            mock_gitlab.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_provider_selection_jenkins(self, executor_all_providers):
        """Test correct provider selection for Jenkins."""
        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'jenkins',
            'job_name': 'test-job',
        }

        with patch.object(executor_all_providers, '_execute_jenkins', new_callable=AsyncMock) as mock_jenkins:
            mock_jenkins.return_value = {'status': 'success'}
            await executor_all_providers.execute(ticket)
            mock_jenkins.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fallback_when_provider_unavailable(self, integration_config, mock_metrics):
        """Test fallback to simulation when provider is unavailable."""
        executor = TestExecutor(
            config=integration_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
        )

        ticket = MagicMock()
        ticket.task_payload = {
            'test_provider': 'github_actions',
            'repository': 'owner/repo',
        }

        with patch.object(executor, '_execute_simulation', new_callable=AsyncMock) as mock_sim:
            mock_sim.return_value = {'status': 'success', 'simulated': True}
            result = await executor.execute(ticket)
            mock_sim.assert_called_once()
            assert result['simulated'] is True


class TestEndToEndFlow:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_test_flow_with_metrics(self, integration_config, mock_metrics):
        """Test complete test flow with metrics recording."""
        github_client = AsyncMock(spec=GitHubActionsClient)
        github_client.trigger_workflow.return_value = {'id': 99999}
        github_client.wait_for_workflow.return_value = WorkflowRunStatus(
            run_id=99999,
            status='completed',
            conclusion='success',
            html_url='https://github.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tests_passed=100,
            tests_failed=0,
            tests_skipped=5,
            coverage_percent=90.0
        )

        executor = TestExecutor(
            config=integration_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            github_actions_client=github_client
        )

        ticket = MagicMock()
        ticket.ticket_id = 'e2e-test-001'
        ticket.task_payload = {
            'test_provider': 'github_actions',
            'repository': 'neural-hive/test-repo',
            'workflow_id': 'ci.yml',
            'ref': 'main',
        }

        result = await executor.execute(ticket)

        assert result['status'] == 'success'
        assert result['tests_passed'] == 100
        assert result['coverage_percent'] == 90.0

        mock_metrics.test_tasks_executed_total.labels.assert_called()
        mock_metrics.tests_passed_total.labels.assert_called()
        mock_metrics.test_coverage_percent.labels.assert_called()
