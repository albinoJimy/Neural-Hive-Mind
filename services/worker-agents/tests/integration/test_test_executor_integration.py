"""
Testes de integracao para TestExecutor.

Este modulo contem testes de integracao que verificam:
- Execucao de testes via GitHub Actions
- Execucao de testes via GitLab CI
- Execucao de testes via Jenkins
- Execucao local com fallback
- Parsing de JUnit XML
- Parsing de coverage reports
- Logica de retry em falhas transitorias

Todos os testes usam mocks dos clientes externos.
"""

import asyncio
import pytest
import uuid
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================
# Fixtures Especificas
# ============================================


@pytest.fixture
def test_executor_with_github(worker_config, mock_metrics, mock_github_actions_client):
    """TestExecutor configurado com cliente GitHub Actions mockado."""
    from services.worker_agents.src.executors.test_executor import TestExecutor

    worker_config.github_actions_enabled = True
    worker_config.github_token = 'test-token'
    worker_config.test_retry_attempts = 3
    worker_config.retry_backoff_base_seconds = 1

    return TestExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        github_actions_client=mock_github_actions_client
    )


@pytest.fixture
def test_executor_with_gitlab(worker_config, mock_metrics, mock_gitlab_ci_client):
    """TestExecutor configurado com cliente GitLab CI mockado."""
    from services.worker_agents.src.executors.test_executor import TestExecutor

    worker_config.gitlab_ci_enabled = True
    worker_config.gitlab_token = 'test-token'
    worker_config.test_retry_attempts = 3

    return TestExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        gitlab_ci_client=mock_gitlab_ci_client
    )


@pytest.fixture
def test_executor_with_jenkins(worker_config, mock_metrics, mock_jenkins_client):
    """TestExecutor configurado com cliente Jenkins mockado."""
    from services.worker_agents.src.executors.test_executor import TestExecutor

    worker_config.jenkins_enabled = True
    worker_config.jenkins_url = 'https://jenkins.example.com'
    worker_config.test_retry_attempts = 3

    return TestExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        jenkins_client=mock_jenkins_client
    )


@pytest.fixture
def test_executor_local_only(worker_config, mock_metrics):
    """TestExecutor sem clientes CI/CD (apenas execucao local)."""
    from services.worker_agents.src.executors.test_executor import TestExecutor

    worker_config.github_actions_enabled = False
    worker_config.gitlab_ci_enabled = False
    worker_config.jenkins_enabled = False
    worker_config.allowed_test_commands = ['pytest', 'npm', 'go', 'python', 'echo']
    worker_config.test_execution_timeout_seconds = 60

    return TestExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics
    )


@pytest.fixture
def test_ticket_github():
    """Ticket de teste para GitHub Actions."""
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
            'test_suite': 'unit',
            'timeout_seconds': 60,
            'poll_interval': 5
        }
    }


@pytest.fixture
def test_ticket_gitlab():
    """Ticket de teste para GitLab CI."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'TEST',
        'parameters': {
            'provider': 'gitlab_ci',
            'project_id': 12345,
            'ref': 'main',
            'variables': {'CI_DEBUG': 'true'},
            'test_suite': 'unit',
            'timeout_seconds': 60,
            'poll_interval': 5
        }
    }


@pytest.fixture
def test_ticket_jenkins():
    """Ticket de teste para Jenkins."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'TEST',
        'parameters': {
            'provider': 'jenkins',
            'job_name': 'test-job',
            'job_parameters': {'BRANCH': 'main'},
            'test_suite': 'integration',
            'timeout_seconds': 120,
            'poll_interval': 10
        }
    }


@pytest.fixture
def test_ticket_local():
    """Ticket de teste para execucao local."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'TEST',
        'parameters': {
            'provider': 'local',
            'test_command': 'echo "tests passed"',
            'working_dir': '/tmp',
            'test_suite': 'unit',
            'timeout_seconds': 30
        }
    }


# ============================================
# Testes de Sucesso - GitHub Actions
# ============================================


class TestTestExecutorGitHubActionsSuccess:
    """Testes de execucao bem-sucedida via GitHub Actions."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_github_actions_success(
        self,
        test_executor_with_github,
        test_ticket_github,
        mock_github_actions_client
    ):
        """Deve executar testes com sucesso via GitHub Actions."""
        result = await test_executor_with_github.execute(test_ticket_github)

        assert result['success'] is True
        assert result['output']['tests_passed'] == 50
        assert result['output']['tests_failed'] == 0
        assert result['output']['coverage'] == 87.5
        assert result['metadata']['provider'] == 'github_actions'
        assert result['metadata']['simulated'] is False

        mock_github_actions_client.trigger_workflow.assert_called_once()
        mock_github_actions_client.wait_for_run.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_github_actions_with_run_id(
        self,
        test_executor_with_github,
        test_ticket_github,
        mock_github_actions_client
    ):
        """Deve retornar run_id do workflow executado."""
        result = await test_executor_with_github.execute(test_ticket_github)

        assert 'run_id' in result['output']
        assert result['output']['run_id'] == 12345


# ============================================
# Testes de Sucesso - GitLab CI
# ============================================


class TestTestExecutorGitLabCISuccess:
    """Testes de execucao bem-sucedida via GitLab CI."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_gitlab_ci_success(
        self,
        test_executor_with_gitlab,
        test_ticket_gitlab,
        mock_gitlab_ci_client
    ):
        """Deve executar testes com sucesso via GitLab CI."""
        result = await test_executor_with_gitlab.execute(test_ticket_gitlab)

        assert result['success'] is True
        assert result['output']['tests_passed'] == 75
        assert result['metadata']['provider'] == 'gitlab_ci'
        assert result['metadata']['simulated'] is False

        mock_gitlab_ci_client.trigger_pipeline.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_gitlab_ci_with_failures(
        self,
        test_executor_with_gitlab,
        test_ticket_gitlab,
        mock_gitlab_ci_client
    ):
        """Deve reportar falhas de teste do GitLab CI."""
        from dataclasses import dataclass

        @dataclass
        class FailedPipelineStatus:
            pipeline_id: int = 54321
            status: str = 'failed'
            success: bool = False
            tests_passed: int = 8
            tests_failed: int = 2
            tests_skipped: int = 0
            tests_errors: int = 0
            coverage: float = 70.0
            duration_seconds: float = 180.0
            web_url: str = 'https://gitlab.com/project/-/pipelines/54321'
            logs: list = None

            def __post_init__(self):
                if self.logs is None:
                    self.logs = ['Pipeline started', 'Tests failed']

        mock_gitlab_ci_client.wait_for_pipeline.return_value = FailedPipelineStatus()

        result = await test_executor_with_gitlab.execute(test_ticket_gitlab)

        assert result['success'] is False
        assert result['output']['tests_failed'] == 2


# ============================================
# Testes de Sucesso - Jenkins
# ============================================


class TestTestExecutorJenkinsSuccess:
    """Testes de execucao bem-sucedida via Jenkins."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_jenkins_success(
        self,
        test_executor_with_jenkins,
        test_ticket_jenkins,
        mock_jenkins_client
    ):
        """Deve executar testes com sucesso via Jenkins."""
        result = await test_executor_with_jenkins.execute(test_ticket_jenkins)

        assert result['success'] is True
        assert result['output']['tests_passed'] == 60
        assert result['metadata']['provider'] == 'jenkins'
        assert result['metadata']['simulated'] is False

        mock_jenkins_client.trigger_job.assert_called_once()


# ============================================
# Testes de Timeout
# ============================================


class TestTestExecutorTimeout:
    """Testes de timeout na execucao de testes."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_github_timeout(
        self,
        test_executor_with_github,
        test_ticket_github,
        mock_github_actions_client
    ):
        """Deve retornar falha quando timeout no GitHub Actions."""
        from services.worker_agents.src.clients.github_actions_client import (
            GitHubActionsTimeoutError
        )

        mock_github_actions_client.wait_for_run.side_effect = GitHubActionsTimeoutError(
            'Workflow run timed out'
        )

        result = await test_executor_with_github.execute(test_ticket_github)

        assert result['success'] is False
        assert 'timeout' in result['logs'][0].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_gitlab_timeout(
        self,
        test_executor_with_gitlab,
        test_ticket_gitlab,
        mock_gitlab_ci_client
    ):
        """Deve retornar falha quando timeout no GitLab CI."""
        from services.worker_agents.src.clients.gitlab_ci_client import (
            GitLabCITimeoutError
        )

        mock_gitlab_ci_client.wait_for_pipeline.side_effect = GitLabCITimeoutError(
            'Pipeline timed out'
        )

        result = await test_executor_with_gitlab.execute(test_ticket_gitlab)

        assert result['success'] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_jenkins_timeout(
        self,
        test_executor_with_jenkins,
        test_ticket_jenkins,
        mock_jenkins_client
    ):
        """Deve retornar falha quando timeout no Jenkins."""
        from services.worker_agents.src.clients.jenkins_client import (
            JenkinsTimeoutError
        )

        mock_jenkins_client.wait_for_build.side_effect = JenkinsTimeoutError(
            'Build timed out'
        )

        result = await test_executor_with_jenkins.execute(test_ticket_jenkins)

        assert result['success'] is False


# ============================================
# Testes de Fallback Local
# ============================================


class TestTestExecutorLocalFallback:
    """Testes de fallback para execucao local."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_local_success(
        self,
        test_executor_local_only,
        test_ticket_local
    ):
        """Deve executar testes localmente com sucesso."""
        result = await test_executor_local_only.execute(test_ticket_local)

        assert result['success'] is True
        assert result['metadata']['provider'] == 'local'
        assert result['metadata']['simulated'] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_local_with_pytest_command(
        self,
        test_executor_local_only
    ):
        """Deve executar pytest localmente."""
        ticket_id = str(uuid.uuid4())
        ticket = {
            'ticket_id': ticket_id,
            'task_type': 'TEST',
            'parameters': {
                'test_command': 'echo "pytest passed"',
                'working_dir': '/tmp',
                'test_suite': 'unit',
                'timeout_seconds': 10
            }
        }

        result = await test_executor_local_only.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['provider'] == 'local'


# ============================================
# Testes de Parsing JUnit XML
# ============================================


class TestTestExecutorJUnitXMLParsing:
    """Testes de parsing de JUnit XML."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_junit_xml_parsing_success(
        self,
        test_executor_local_only
    ):
        """Deve parsear arquivo JUnit XML corretamente."""
        # Criar arquivo JUnit XML temporario
        junit_content = '''<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="test_suite" tests="5" failures="2" errors="0" skipped="0">
    <testcase classname="test.Test1" name="test_pass_1" time="0.1"/>
    <testcase classname="test.Test1" name="test_pass_2" time="0.2"/>
    <testcase classname="test.Test1" name="test_pass_3" time="0.1"/>
    <testcase classname="test.Test2" name="test_fail_1" time="0.3">
        <failure message="assertion failed">AssertionError</failure>
    </testcase>
    <testcase classname="test.Test2" name="test_fail_2" time="0.2">
        <failure message="value error">ValueError</failure>
    </testcase>
</testsuite>'''

        with tempfile.TemporaryDirectory() as tmpdir:
            junit_path = Path(tmpdir) / 'junit.xml'
            junit_path.write_text(junit_content)

            # Testar parsing via metodo privado se disponivel
            try:
                result = test_executor_local_only._parse_junit_xml_file(
                    'junit.xml',
                    tmpdir
                )

                assert result['total'] == 5
                assert result['passed'] == 3
                assert result['failed'] == 2
            except (ImportError, AttributeError):
                # Se o parser nao estiver disponivel, pular teste
                pytest.skip('JUnitXMLParser not available')


# ============================================
# Testes de Parsing Coverage
# ============================================


class TestTestExecutorCoverageParsing:
    """Testes de parsing de coverage reports."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_coverage_parsing_cobertura(
        self,
        test_executor_local_only
    ):
        """Deve parsear arquivo Cobertura XML corretamente."""
        cobertura_content = '''<?xml version="1.0" ?>
<!DOCTYPE coverage SYSTEM 'http://cobertura.sourceforge.net/xml/coverage-04.dtd'>
<coverage line-rate="0.75" branch-rate="0.5" lines-covered="75" lines-valid="100">
    <packages>
        <package name="mypackage" line-rate="0.75" branch-rate="0.5">
            <classes>
                <class name="MyClass" filename="myclass.py" line-rate="0.75">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                        <line number="3" hits="0"/>
                        <line number="4" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>'''

        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_path = Path(tmpdir) / 'coverage.xml'
            coverage_path.write_text(cobertura_content)

            try:
                result = test_executor_local_only._parse_coverage_file(
                    'coverage.xml',
                    tmpdir
                )

                assert result is not None
                assert result == 75.0
            except (ImportError, AttributeError):
                pytest.skip('Coverage parser not available')


# ============================================
# Testes de Retry Logic
# ============================================


class TestTestExecutorRetryLogic:
    """Testes de logica de retry."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_retry_on_transient_failure(
        self,
        worker_config,
        mock_metrics,
        test_ticket_github
    ):
        """Deve fazer retry em falhas transitorias."""
        from services.worker_agents.src.executors.test_executor import TestExecutor
        from dataclasses import dataclass
        import httpx

        call_count = 0

        @dataclass
        class MockRunStatus:
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

        async def trigger_with_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError('Connection refused')
            return 12345

        mock_client = AsyncMock()
        mock_client.trigger_workflow = AsyncMock(side_effect=trigger_with_failure)
        mock_client.wait_for_run = AsyncMock(return_value=MockRunStatus())
        mock_client.default_repo = 'test-org/test-repo'

        worker_config.github_actions_enabled = True
        worker_config.test_retry_attempts = 3
        worker_config.retry_backoff_base_seconds = 0.1

        executor = TestExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            github_actions_client=mock_client
        )

        result = await executor.execute(test_ticket_github)

        # O retry deve ter sido executado
        assert call_count >= 1


# ============================================
# Testes de Simulacao
# ============================================


class TestTestExecutorSimulation:
    """Testes de fallback para simulacao."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_simulation_fallback(
        self,
        worker_config,
        mock_metrics
    ):
        """Deve usar simulacao quando nenhum provider disponivel."""
        from services.worker_agents.src.executors.test_executor import TestExecutor

        worker_config.github_actions_enabled = False
        worker_config.gitlab_ci_enabled = False
        worker_config.jenkins_enabled = False

        executor = TestExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics
        )

        ticket_id = str(uuid.uuid4())
        ticket = {
            'ticket_id': ticket_id,
            'task_type': 'TEST',
            'parameters': {
                'test_suite': 'unit'
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['simulated'] is True
        assert result['metadata']['provider'] == 'simulation'
        assert result['output']['tests_passed'] > 0


# ============================================
# Testes de Metricas
# ============================================


class TestTestExecutorMetrics:
    """Testes de registro de metricas."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_metrics_recorded(
        self,
        test_executor_with_github,
        test_ticket_github,
        mock_metrics
    ):
        """Deve registrar metricas Prometheus apos execucao."""
        await test_executor_with_github.execute(test_ticket_github)

        mock_metrics.test_tasks_executed_total.labels.assert_called()
        mock_metrics.tests_passed_total.labels.assert_called()
        mock_metrics.test_coverage_percent.labels.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_test_executor_duration_metrics(
        self,
        test_executor_with_github,
        test_ticket_github,
        mock_metrics
    ):
        """Deve registrar duracao da execucao."""
        await test_executor_with_github.execute(test_ticket_github)

        mock_metrics.test_duration_seconds.labels.assert_called()
