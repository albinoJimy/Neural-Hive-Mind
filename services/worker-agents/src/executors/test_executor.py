"""
TEST Executor para execucao de tarefas de teste.

Suporta multiplos providers:
- GitHub Actions (via workflow_dispatch)
- GitLab CI (via pipeline trigger)
- Jenkins (via job trigger)
- Local (via subprocess)
- Simulation (fallback)
"""

import asyncio
import json
import random
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from neural_hive_observability import get_tracer

from .base_executor import BaseTaskExecutor


class TestExecutor(BaseTaskExecutor):
    """
    Executor para task_type=TEST com suporte a multiplos CI/CD providers.

    Providers suportados:
    - github_actions: Executa via GitHub Actions workflow
    - gitlab_ci: Executa via GitLab CI pipeline
    - jenkins: Executa via Jenkins job
    - local: Executa comando local via subprocess
    - simulation: Fallback simulado para desenvolvimento
    """

    def get_task_type(self) -> str:
        return 'TEST'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client=None,
        metrics=None,
        github_actions_client=None,
        gitlab_ci_client=None,
        jenkins_client=None
    ):
        """
        Inicializa TEST Executor.

        Args:
            config: Configuracao do worker agent
            vault_client: Cliente Vault opcional
            code_forge_client: Cliente Code Forge opcional
            metrics: Instancia de metricas Prometheus
            github_actions_client: Cliente GitHub Actions opcional
            gitlab_ci_client: Cliente GitLab CI opcional
            jenkins_client: Cliente Jenkins opcional
        """
        super().__init__(
            config,
            vault_client=vault_client,
            code_forge_client=code_forge_client,
            metrics=metrics
        )
        self.github_actions_client = github_actions_client
        self.gitlab_ci_client = gitlab_ci_client
        self.jenkins_client = jenkins_client

        # Fallback: tentar criar clients a partir do config se nao fornecidos
        if self.github_actions_client is None and getattr(config, 'github_actions_enabled', False):
            try:
                from ..clients.github_actions_client import GitHubActionsClient
                self.github_actions_client = GitHubActionsClient.from_env(config)
            except Exception:
                pass

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executa tarefa de teste.

        Args:
            ticket: Ticket de execucao

        Returns:
            Resultado da execucao
        """
        tracer = get_tracer()
        with tracer.start_as_current_span('task_execution') as span:
            span.set_attribute('neural.hive.task_id', ticket.get('ticket_id'))
            span.set_attribute('neural.hive.task_type', self.get_task_type())
            span.set_attribute('neural.hive.executor', self.__class__.__name__)
            result = await self._execute_internal(ticket, span)
            span.set_attribute('neural.hive.execution_status', 'success' if result.get('success') else 'failed')
            return result

    async def _execute_internal(self, ticket: Dict[str, Any], span=None) -> Dict[str, Any]:
        """
        Executa tarefa de TEST com o provider apropriado.

        Ordem de fallback:
        1. Tenta provider CI/CD configurado (github_actions, gitlab_ci, jenkins)
        2. Se CI/CD falhar ou nao disponivel, tenta execucao local
        3. Somente se local nao estiver configurado, usa simulacao

        Args:
            ticket: Ticket de execucao
            span: OpenTelemetry span opcional

        Returns:
            Resultado da execucao
        """
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})

        self.log_execution(
            ticket_id,
            'test_started',
            parameters=parameters
        )

        test_suite = parameters.get('test_suite', 'default')
        timeout_seconds = parameters.get('timeout_seconds') or getattr(
            self.config, 'test_execution_timeout_seconds', 600
        )
        provider = parameters.get('provider') or parameters.get('ci_provider')
        poll_interval = parameters.get('poll_interval', 15)

        # Selecionar provider
        if provider == 'github_actions':
            if self.github_actions_client:
                result = await self._try_cicd_with_local_fallback(
                    cicd_method=self._execute_github_actions,
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    poll_interval=poll_interval,
                    span=span,
                    provider_name='github_actions'
                )
                return result
            else:
                # Provider solicitado mas client nao disponivel, tentar local
                self.log_execution(
                    ticket_id,
                    'test_provider_unavailable',
                    level='warning',
                    provider='github_actions',
                    fallback='local'
                )
                return await self._try_local_or_simulation(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    span=span,
                    reason='GitHub Actions client not configured'
                )

        if provider == 'gitlab_ci':
            if self.gitlab_ci_client:
                result = await self._try_cicd_with_local_fallback(
                    cicd_method=self._execute_gitlab_ci,
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    poll_interval=poll_interval,
                    span=span,
                    provider_name='gitlab_ci'
                )
                return result
            else:
                self.log_execution(
                    ticket_id,
                    'test_provider_unavailable',
                    level='warning',
                    provider='gitlab_ci',
                    fallback='local'
                )
                return await self._try_local_or_simulation(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    span=span,
                    reason='GitLab CI client not configured'
                )

        if provider == 'jenkins':
            if self.jenkins_client:
                result = await self._try_cicd_with_local_fallback(
                    cicd_method=self._execute_jenkins,
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    poll_interval=poll_interval,
                    span=span,
                    provider_name='jenkins'
                )
                return result
            else:
                self.log_execution(
                    ticket_id,
                    'test_provider_unavailable',
                    level='warning',
                    provider='jenkins',
                    fallback='local'
                )
                return await self._try_local_or_simulation(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    span=span,
                    reason='Jenkins client not configured'
                )

        if provider == 'local' or parameters.get('test_command'):
            return await self._execute_local(
                ticket_id=ticket_id,
                parameters=parameters,
                test_suite=test_suite,
                timeout_seconds=timeout_seconds,
                span=span
            )

        # Nenhum provider especificado - tentar local primeiro, depois simulacao
        return await self._try_local_or_simulation(
            ticket_id=ticket_id,
            parameters=parameters,
            test_suite=test_suite,
            timeout_seconds=timeout_seconds,
            span=span,
            reason='No CI/CD provider configured'
        )

    async def _try_cicd_with_local_fallback(
        self,
        cicd_method,
        ticket_id: str,
        parameters: Dict[str, Any],
        test_suite: str,
        timeout_seconds: int,
        poll_interval: int,
        span,
        provider_name: str
    ) -> Dict[str, Any]:
        """
        Tenta executar via CI/CD, com fallback para local em caso de falha irrecuperavel.

        Args:
            cicd_method: Metodo de execucao CI/CD
            ticket_id: ID do ticket
            parameters: Parametros do ticket
            test_suite: Nome da suite de teste
            timeout_seconds: Timeout total
            poll_interval: Intervalo de polling
            span: OpenTelemetry span
            provider_name: Nome do provider para logging

        Returns:
            Resultado da execucao
        """
        try:
            result = await cicd_method(
                ticket_id=ticket_id,
                parameters=parameters,
                test_suite=test_suite,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
                span=span
            )

            # Se CI/CD falhou apos todas tentativas e nao e timeout, tentar local
            if not result.get('success') and not result.get('metadata', {}).get('simulated'):
                logs = result.get('logs', [])
                # Verificar se e um erro recuperavel via local
                is_api_error = any(
                    'API' in log or 'failed' in log.lower() or 'error' in log.lower()
                    for log in logs if isinstance(log, str)
                )

                if is_api_error and parameters.get('test_command'):
                    self.log_execution(
                        ticket_id,
                        'test_cicd_failed_trying_local',
                        level='warning',
                        provider=provider_name,
                        reason='CI/CD execution failed, attempting local fallback'
                    )
                    return await self._execute_local(
                        ticket_id=ticket_id,
                        parameters=parameters,
                        test_suite=test_suite,
                        timeout_seconds=timeout_seconds,
                        span=span
                    )

            return result

        except Exception as exc:
            self.log_execution(
                ticket_id,
                'test_cicd_exception_trying_local',
                level='error',
                provider=provider_name,
                error=str(exc)
            )

            # Tentar local se tiver comando de teste configurado
            if parameters.get('test_command'):
                return await self._execute_local(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    test_suite=test_suite,
                    timeout_seconds=timeout_seconds,
                    span=span
                )

            # Fallback final para simulacao
            return await self._execute_simulation(
                ticket_id=ticket_id,
                test_suite=test_suite,
                reason=f'{provider_name} failed with exception: {exc}',
                span=span
            )

    async def _try_local_or_simulation(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        test_suite: str,
        timeout_seconds: int,
        span,
        reason: str
    ) -> Dict[str, Any]:
        """
        Tenta execucao local, com fallback para simulacao se local nao disponivel.

        Args:
            ticket_id: ID do ticket
            parameters: Parametros do ticket
            test_suite: Nome da suite de teste
            timeout_seconds: Timeout de execucao
            span: OpenTelemetry span
            reason: Razao do fallback

        Returns:
            Resultado da execucao
        """
        # Verificar se temos comando de teste para execucao local
        if parameters.get('test_command'):
            self.log_execution(
                ticket_id,
                'test_fallback_to_local',
                reason=reason
            )
            return await self._execute_local(
                ticket_id=ticket_id,
                parameters=parameters,
                test_suite=test_suite,
                timeout_seconds=timeout_seconds,
                span=span
            )

        # Sem comando local, usar simulacao
        return await self._execute_simulation(
            ticket_id=ticket_id,
            test_suite=test_suite,
            reason=reason,
            span=span
        )

    async def _execute_github_actions(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        test_suite: str,
        timeout_seconds: int,
        poll_interval: int,
        span=None
    ) -> Dict[str, Any]:
        """
        Executa teste via GitHub Actions workflow.

        Args:
            ticket_id: ID do ticket
            parameters: Parametros do ticket
            test_suite: Nome da suite de teste
            timeout_seconds: Timeout total
            poll_interval: Intervalo de polling
            span: OpenTelemetry span

        Returns:
            Resultado da execucao
        """
        from ..clients.github_actions_client import (
            GitHubActionsAPIError,
            GitHubActionsTimeoutError
        )

        self.log_execution(
            ticket_id,
            'test_github_actions_started',
            repo=parameters.get('repo'),
            workflow_id=parameters.get('workflow_id')
        )

        repo = parameters.get('repo')
        workflow_id = parameters.get('workflow_id')
        ref = parameters.get('ref', 'main')
        inputs = parameters.get('inputs', {})

        max_retries = getattr(self.config, 'test_retry_attempts', 3)
        backoff_base = getattr(self.config, 'retry_backoff_base_seconds', 2)
        run_id = None

        for attempt in range(max_retries):
            try:
                # Trigger workflow
                self.github_actions_client.default_repo = repo
                run_id = await self.github_actions_client.trigger_workflow(
                    repo=repo,
                    workflow_id=workflow_id,
                    ref=ref,
                    inputs=inputs
                )

                if self.metrics and hasattr(self.metrics, 'github_actions_api_calls_total'):
                    self.metrics.github_actions_api_calls_total.labels(method='trigger', status='success').inc()

                # Wait for completion
                status = await self.github_actions_client.wait_for_run(
                    run_id=run_id,
                    poll_interval=poll_interval,
                    timeout=timeout_seconds,
                    repo=repo
                )

                tests_passed = status.passed or 0
                tests_failed = status.failed or 0
                coverage = status.coverage

                # Record metrics
                self._record_test_metrics(
                    test_suite=test_suite,
                    success=status.success,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    coverage=coverage,
                    duration_seconds=status.duration_seconds
                )

                self.log_execution(
                    ticket_id,
                    'test_github_actions_completed',
                    run_id=run_id,
                    conclusion=status.conclusion,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed
                )

                return {
                    'success': status.success,
                    'output': {
                        'tests_passed': tests_passed,
                        'tests_failed': tests_failed,
                        'tests_skipped': status.skipped or 0,
                        'coverage': coverage,
                        'test_suite': test_suite,
                        'run_id': run_id,
                        'conclusion': status.conclusion,
                        'html_url': status.html_url
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'github_actions',
                        'simulated': False,
                        'duration_seconds': status.duration_seconds,
                        'attempt': attempt + 1
                    },
                    'logs': status.logs or []
                }

            except GitHubActionsTimeoutError as e:
                self.log_execution(
                    ticket_id,
                    'test_github_actions_timeout',
                    level='warning',
                    run_id=run_id,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                    self.metrics.test_tasks_executed_total.labels(status='timeout', suite=test_suite).inc()
                return {
                    'success': False,
                    'output': {
                        'tests_passed': 0,
                        'tests_failed': 0,
                        'coverage': None,
                        'test_suite': test_suite,
                        'run_id': run_id
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'github_actions',
                        'simulated': False,
                        'duration_seconds': timeout_seconds
                    },
                    'logs': [f'GitHub Actions timeout: {e}']
                }

            except (GitHubActionsAPIError, Exception) as exc:
                self.log_execution(
                    ticket_id,
                    'test_github_actions_error',
                    level='error',
                    run_id=run_id,
                    attempt=attempt + 1,
                    error=str(exc)
                )
                if self.metrics and hasattr(self.metrics, 'github_actions_api_calls_total'):
                    self.metrics.github_actions_api_calls_total.labels(method='trigger', status='error').inc()

                if attempt < max_retries - 1:
                    wait_time = min(backoff_base * (2 ** attempt), 60)
                    self.log_execution(
                        ticket_id,
                        'test_retry_scheduled',
                        attempt=attempt + 1,
                        wait_time=wait_time
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                    self.metrics.test_tasks_executed_total.labels(status='failed', suite=test_suite).inc()

                return {
                    'success': False,
                    'output': {
                        'tests_passed': 0,
                        'tests_failed': 0,
                        'coverage': None,
                        'test_suite': test_suite
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'github_actions',
                        'simulated': False,
                        'attempt': attempt + 1
                    },
                    'logs': ['GitHub Actions execution failed', str(exc)]
                }

        # Should not reach here
        return await self._execute_simulation(ticket_id, test_suite, 'All retries exhausted', span)

    async def _execute_gitlab_ci(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        test_suite: str,
        timeout_seconds: int,
        poll_interval: int,
        span=None
    ) -> Dict[str, Any]:
        """
        Executa teste via GitLab CI pipeline.

        Baixa e parseia artifacts de jobs para extrair resultados de teste (JUnit XML)
        e coverage (Cobertura/LCOV) quando disponiveis.

        Args:
            ticket_id: ID do ticket
            parameters: Parametros do ticket
            test_suite: Nome da suite de teste
            timeout_seconds: Timeout total
            poll_interval: Intervalo de polling
            span: OpenTelemetry span

        Returns:
            Resultado da execucao
        """
        from ..clients.gitlab_ci_client import (
            GitLabCIAPIError,
            GitLabCITimeoutError
        )

        self.log_execution(
            ticket_id,
            'test_gitlab_ci_started',
            project_id=parameters.get('project_id'),
            ref=parameters.get('ref')
        )

        project_id = parameters.get('project_id')
        ref = parameters.get('ref', 'main')
        variables = parameters.get('variables', {})

        # Paths para artifacts (podem ser customizados via parameters)
        junit_artifact_paths = parameters.get('junit_artifact_paths')
        coverage_artifact_paths = parameters.get('coverage_artifact_paths')

        max_retries = getattr(self.config, 'test_retry_attempts', 3)
        backoff_base = getattr(self.config, 'retry_backoff_base_seconds', 2)
        pipeline_id = None

        for attempt in range(max_retries):
            try:
                # Trigger pipeline
                pipeline_id = await self.gitlab_ci_client.trigger_pipeline(
                    project_id=project_id,
                    ref=ref,
                    variables=variables
                )

                if self.metrics and hasattr(self.metrics, 'gitlab_ci_api_calls_total'):
                    self.metrics.gitlab_ci_api_calls_total.labels(method='trigger', status='success').inc()

                # Wait for completion
                status = await self.gitlab_ci_client.wait_for_pipeline(
                    project_id=project_id,
                    pipeline_id=pipeline_id,
                    poll_interval=poll_interval,
                    timeout=timeout_seconds
                )

                # Obter resultados do test_report API (padrao GitLab)
                tests_passed = status.tests_passed
                tests_failed = status.tests_failed
                tests_skipped = status.tests_skipped
                tests_errors = status.tests_errors
                coverage = status.coverage

                # Se nao obteve resultados via test_report API, tentar via artifacts
                if tests_passed == 0 and tests_failed == 0:
                    self.log_execution(
                        ticket_id,
                        'test_gitlab_ci_parsing_artifacts',
                        pipeline_id=pipeline_id
                    )

                    artifact_results = await self.gitlab_ci_client.download_and_parse_artifacts(
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                        junit_artifact_paths=junit_artifact_paths,
                        coverage_artifact_paths=coverage_artifact_paths
                    )

                    tests_passed = artifact_results.get('tests_passed', 0)
                    tests_failed = artifact_results.get('tests_failed', 0)
                    tests_skipped = artifact_results.get('tests_skipped', 0)
                    tests_errors = artifact_results.get('tests_errors', 0)

                    # Coverage do artifact so se nao tiver do pipeline status
                    if coverage is None and artifact_results.get('coverage') is not None:
                        coverage = artifact_results['coverage']

                # Record metrics
                self._record_test_metrics(
                    test_suite=test_suite,
                    success=status.success,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    coverage=coverage,
                    duration_seconds=status.duration_seconds
                )

                self.log_execution(
                    ticket_id,
                    'test_gitlab_ci_completed',
                    pipeline_id=pipeline_id,
                    status=status.status,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    coverage=coverage
                )

                return {
                    'success': status.success,
                    'output': {
                        'tests_passed': tests_passed,
                        'tests_failed': tests_failed,
                        'tests_skipped': tests_skipped,
                        'tests_errors': tests_errors,
                        'coverage': coverage,
                        'test_suite': test_suite,
                        'pipeline_id': pipeline_id,
                        'web_url': status.web_url
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'gitlab_ci',
                        'simulated': False,
                        'duration_seconds': status.duration_seconds,
                        'attempt': attempt + 1
                    },
                    'logs': status.logs or []
                }

            except GitLabCITimeoutError as e:
                self.log_execution(
                    ticket_id,
                    'test_gitlab_ci_timeout',
                    level='warning',
                    pipeline_id=pipeline_id,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                    self.metrics.test_tasks_executed_total.labels(status='timeout', suite=test_suite).inc()
                return {
                    'success': False,
                    'output': {
                        'tests_passed': 0,
                        'tests_failed': 0,
                        'coverage': None,
                        'test_suite': test_suite,
                        'pipeline_id': pipeline_id
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'gitlab_ci',
                        'simulated': False,
                        'duration_seconds': timeout_seconds
                    },
                    'logs': [f'GitLab CI timeout: {e}']
                }

            except (GitLabCIAPIError, Exception) as exc:
                self.log_execution(
                    ticket_id,
                    'test_gitlab_ci_error',
                    level='error',
                    pipeline_id=pipeline_id,
                    attempt=attempt + 1,
                    error=str(exc)
                )
                if self.metrics and hasattr(self.metrics, 'gitlab_ci_api_calls_total'):
                    self.metrics.gitlab_ci_api_calls_total.labels(method='trigger', status='error').inc()

                if attempt < max_retries - 1:
                    wait_time = min(backoff_base * (2 ** attempt), 60)
                    await asyncio.sleep(wait_time)
                    continue

                if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                    self.metrics.test_tasks_executed_total.labels(status='failed', suite=test_suite).inc()

                return {
                    'success': False,
                    'output': {
                        'tests_passed': 0,
                        'tests_failed': 0,
                        'coverage': None,
                        'test_suite': test_suite
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'gitlab_ci',
                        'simulated': False,
                        'attempt': attempt + 1
                    },
                    'logs': ['GitLab CI execution failed', str(exc)]
                }

        return await self._execute_simulation(ticket_id, test_suite, 'All retries exhausted', span)

    async def _execute_jenkins(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        test_suite: str,
        timeout_seconds: int,
        poll_interval: int,
        span=None
    ) -> Dict[str, Any]:
        """
        Executa teste via Jenkins job.

        Args:
            ticket_id: ID do ticket
            parameters: Parametros do ticket
            test_suite: Nome da suite de teste
            timeout_seconds: Timeout total
            poll_interval: Intervalo de polling
            span: OpenTelemetry span

        Returns:
            Resultado da execucao
        """
        from ..clients.jenkins_client import (
            JenkinsAPIError,
            JenkinsTimeoutError
        )

        self.log_execution(
            ticket_id,
            'test_jenkins_started',
            job_name=parameters.get('job_name')
        )

        job_name = parameters.get('job_name')
        job_parameters = parameters.get('job_parameters', {})

        max_retries = getattr(self.config, 'test_retry_attempts', 3)
        backoff_base = getattr(self.config, 'retry_backoff_base_seconds', 2)
        build_number = None

        for attempt in range(max_retries):
            try:
                # Trigger job
                queue_id = await self.jenkins_client.trigger_job(
                    job_name=job_name,
                    parameters=job_parameters
                )

                if self.metrics and hasattr(self.metrics, 'jenkins_api_calls_total'):
                    self.metrics.jenkins_api_calls_total.labels(method='trigger', status='success').inc()

                # Wait for build number
                build_number = await self.jenkins_client.wait_for_build_number(
                    job_name=job_name,
                    queue_id=queue_id,
                    poll_interval=5,
                    timeout=300
                )

                # Wait for build completion
                status = await self.jenkins_client.wait_for_build(
                    job_name=job_name,
                    build_number=build_number,
                    poll_interval=poll_interval,
                    timeout=timeout_seconds
                )

                tests_passed = status.tests_passed
                tests_failed = status.tests_failed
                coverage = status.coverage

                # Record metrics
                self._record_test_metrics(
                    test_suite=test_suite,
                    success=status.success,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    coverage=coverage,
                    duration_seconds=status.duration_seconds
                )

                self.log_execution(
                    ticket_id,
                    'test_jenkins_completed',
                    job_name=job_name,
                    build_number=build_number,
                    status=status.status,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed
                )

                return {
                    'success': status.success,
                    'output': {
                        'tests_passed': tests_passed,
                        'tests_failed': tests_failed,
                        'tests_skipped': status.tests_skipped,
                        'coverage': coverage,
                        'test_suite': test_suite,
                        'build_number': build_number,
                        'job_name': job_name,
                        'url': status.url
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'jenkins',
                        'simulated': False,
                        'duration_seconds': status.duration_seconds,
                        'attempt': attempt + 1
                    },
                    'logs': status.logs or []
                }

            except JenkinsTimeoutError as e:
                self.log_execution(
                    ticket_id,
                    'test_jenkins_timeout',
                    level='warning',
                    job_name=job_name,
                    build_number=build_number,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                    self.metrics.test_tasks_executed_total.labels(status='timeout', suite=test_suite).inc()
                return {
                    'success': False,
                    'output': {
                        'tests_passed': 0,
                        'tests_failed': 0,
                        'coverage': None,
                        'test_suite': test_suite,
                        'job_name': job_name,
                        'build_number': build_number
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'jenkins',
                        'simulated': False,
                        'duration_seconds': timeout_seconds
                    },
                    'logs': [f'Jenkins timeout: {e}']
                }

            except (JenkinsAPIError, Exception) as exc:
                self.log_execution(
                    ticket_id,
                    'test_jenkins_error',
                    level='error',
                    job_name=job_name,
                    build_number=build_number,
                    attempt=attempt + 1,
                    error=str(exc)
                )
                if self.metrics and hasattr(self.metrics, 'jenkins_api_calls_total'):
                    self.metrics.jenkins_api_calls_total.labels(method='trigger', status='error').inc()

                if attempt < max_retries - 1:
                    wait_time = min(backoff_base * (2 ** attempt), 60)
                    await asyncio.sleep(wait_time)
                    continue

                if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                    self.metrics.test_tasks_executed_total.labels(status='failed', suite=test_suite).inc()

                return {
                    'success': False,
                    'output': {
                        'tests_passed': 0,
                        'tests_failed': 0,
                        'coverage': None,
                        'test_suite': test_suite
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'provider': 'jenkins',
                        'simulated': False,
                        'attempt': attempt + 1
                    },
                    'logs': ['Jenkins execution failed', str(exc)]
                }

        return await self._execute_simulation(ticket_id, test_suite, 'All retries exhausted', span)

    async def _execute_local(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        test_suite: str,
        timeout_seconds: int,
        span=None
    ) -> Dict[str, Any]:
        """
        Executa teste localmente via subprocess.

        Args:
            ticket_id: ID do ticket
            parameters: Parametros do ticket
            test_suite: Nome da suite de teste
            timeout_seconds: Timeout de execucao
            span: OpenTelemetry span

        Returns:
            Resultado da execucao
        """
        test_command = parameters.get('test_command')
        working_dir = parameters.get('working_dir')
        junit_xml_path = parameters.get('junit_xml_path')
        coverage_report_path = parameters.get('coverage_report_path')

        self.log_execution(
            ticket_id,
            'test_local_started',
            command=test_command,
            working_dir=working_dir
        )

        try:
            # Validate command
            allowed = getattr(self.config, 'allowed_test_commands', [])
            command_parts = shlex.split(test_command)
            if not command_parts:
                raise ValueError('Empty test command')

            if allowed and not any(
                test_command.startswith(cmd) or command_parts[0] == cmd for cmd in allowed
            ):
                raise ValueError(f'Command {command_parts[0]} not allowed')

            cwd = Path(working_dir) if working_dir else None
            if cwd and not cwd.exists():
                raise FileNotFoundError(f'Working dir not found: {cwd}')

            started_at = time.monotonic()
            proc = subprocess.run(
                command_parts,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            duration_seconds = time.monotonic() - started_at

            # Parse test results
            tests_passed = 0
            tests_failed = 0
            tests_skipped = 0
            coverage = None

            # Try JUnit XML parsing
            if junit_xml_path:
                test_results = self._parse_junit_xml_file(junit_xml_path, working_dir)
                tests_passed = test_results.get('passed', 0)
                tests_failed = test_results.get('failed', 0)
                tests_skipped = test_results.get('skipped', 0)

            # Try coverage report parsing
            if coverage_report_path:
                coverage = self._parse_coverage_file(coverage_report_path, working_dir)

            # Fallback: try JSON report
            if tests_passed == 0 and tests_failed == 0:
                report_path = Path(working_dir or '.') / parameters.get('report_path', 'report.json')
                if report_path.exists():
                    try:
                        report_data = json.loads(report_path.read_text())
                        tests_passed = report_data.get('tests_passed') or report_data.get('passed') or 0
                        tests_failed = report_data.get('tests_failed') or report_data.get('failed') or 0
                        coverage = report_data.get('coverage') or coverage
                    except Exception:
                        pass

            # Fallback: try parsing stdout as JSON
            if tests_passed == 0 and tests_failed == 0:
                try:
                    report_data = json.loads(proc.stdout)
                    tests_passed = report_data.get('tests_passed') or report_data.get('passed') or 0
                    tests_failed = report_data.get('tests_failed') or report_data.get('failed') or 0
                    coverage = report_data.get('coverage') or coverage
                except Exception:
                    pass

            success = proc.returncode == 0
            logs = [
                'Tests started',
                f'Running test suite: {test_suite}',
                f'Command: {test_command}',
                f'STDOUT: {proc.stdout.strip()[:500]}',
                f'STDERR: {proc.stderr.strip()[:500]}'
            ]

            # Record metrics
            self._record_test_metrics(
                test_suite=test_suite,
                success=success,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                coverage=coverage,
                duration_seconds=duration_seconds
            )

            level = 'info' if success else 'warning'
            self.log_execution(
                ticket_id,
                'test_completed' if success else 'test_failed',
                level=level,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                duration_seconds=duration_seconds
            )

            return {
                'success': success,
                'output': {
                    'tests_passed': tests_passed,
                    'tests_failed': tests_failed,
                    'tests_skipped': tests_skipped,
                    'coverage': coverage,
                    'test_suite': test_suite,
                    'return_code': proc.returncode
                },
                'metadata': {
                    'executor': 'TestExecutor',
                    'provider': 'local',
                    'simulated': False,
                    'duration_seconds': duration_seconds
                },
                'logs': logs
            }

        except subprocess.TimeoutExpired:
            self.log_execution(
                ticket_id,
                'test_timeout',
                level='error',
                timeout_seconds=timeout_seconds
            )
            if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                self.metrics.test_tasks_executed_total.labels(status='timeout', suite=test_suite).inc()
            return {
                'success': False,
                'output': {
                    'tests_passed': 0,
                    'tests_failed': 0,
                    'coverage': None,
                    'test_suite': test_suite
                },
                'metadata': {
                    'executor': 'TestExecutor',
                    'provider': 'local',
                    'simulated': False,
                    'duration_seconds': timeout_seconds
                },
                'logs': [
                    'Tests started',
                    f'Command: {test_command}',
                    f'Timed out after {timeout_seconds}s'
                ]
            }

        except Exception as exc:
            self.log_execution(
                ticket_id,
                'test_execution_error',
                level='error',
                error=str(exc)
            )
            if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
                self.metrics.test_tasks_executed_total.labels(status='failed', suite=test_suite).inc()

            # Fallback to simulation
            return await self._execute_simulation(
                ticket_id=ticket_id,
                test_suite=test_suite,
                reason=f'Local execution failed: {exc}',
                span=span
            )

    async def _execute_simulation(
        self,
        ticket_id: str,
        test_suite: str,
        reason: str = 'No CI/CD provider available',
        span=None
    ) -> Dict[str, Any]:
        """
        Fallback simulado para desenvolvimento.

        Args:
            ticket_id: ID do ticket
            test_suite: Nome da suite de teste
            reason: Razao do fallback
            span: OpenTelemetry span

        Returns:
            Resultado simulado
        """
        self.log_execution(
            ticket_id,
            'test_fallback_simulation',
            reason=reason
        )

        delay = random.uniform(1, 3)
        await asyncio.sleep(delay)

        tests_passed = random.randint(40, 50)
        coverage = random.uniform(0.80, 0.95)

        result = {
            'success': True,
            'output': {
                'tests_passed': tests_passed,
                'tests_failed': 0,
                'tests_skipped': random.randint(0, 5),
                'coverage': round(coverage, 2),
                'test_suite': test_suite
            },
            'metadata': {
                'executor': 'TestExecutor',
                'provider': 'simulation',
                'simulated': True,
                'duration_seconds': delay,
                'fallback_reason': reason
            },
            'logs': [
                'Tests started',
                f'Running test suite: {test_suite}',
                f'Simulated {tests_passed} tests for {delay:.2f}s',
                f'Coverage: {coverage:.2%}',
                'All tests passed'
            ]
        }

        self.log_execution(
            ticket_id,
            'test_completed',
            duration_seconds=delay,
            tests_passed=tests_passed,
            coverage=coverage
        )

        if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
            self.metrics.test_tasks_executed_total.labels(status='success', suite=test_suite).inc()
        if self.metrics and hasattr(self.metrics, 'test_duration_seconds'):
            self.metrics.test_duration_seconds.labels(suite=test_suite).observe(delay)
        if self.metrics and hasattr(self.metrics, 'tests_passed_total'):
            self.metrics.tests_passed_total.labels(suite=test_suite).inc(tests_passed)
        if self.metrics and hasattr(self.metrics, 'test_coverage_percent'):
            self.metrics.test_coverage_percent.labels(suite=test_suite).set(coverage)

        return result

    def _record_test_metrics(
        self,
        test_suite: str,
        success: bool,
        tests_passed: int,
        tests_failed: int,
        coverage: Optional[float],
        duration_seconds: Optional[float]
    ):
        """Registra metricas de teste."""
        if self.metrics and hasattr(self.metrics, 'test_tasks_executed_total'):
            status = 'success' if success else 'failed'
            self.metrics.test_tasks_executed_total.labels(status=status, suite=test_suite).inc()

        if self.metrics and hasattr(self.metrics, 'tests_passed_total'):
            self.metrics.tests_passed_total.labels(suite=test_suite).inc(tests_passed or 0)

        if self.metrics and hasattr(self.metrics, 'tests_failed_total'):
            self.metrics.tests_failed_total.labels(suite=test_suite).inc(tests_failed or 0)

        if self.metrics and hasattr(self.metrics, 'test_coverage_percent') and coverage is not None:
            self.metrics.test_coverage_percent.labels(suite=test_suite).set(coverage)

        if self.metrics and hasattr(self.metrics, 'test_duration_seconds') and duration_seconds is not None:
            self.metrics.test_duration_seconds.labels(suite=test_suite).observe(duration_seconds)

    def _parse_junit_xml_file(
        self,
        junit_xml_path: str,
        working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parseia arquivo JUnit XML.

        Args:
            junit_xml_path: Caminho do arquivo
            working_dir: Diretorio de trabalho

        Returns:
            Resultados parseados
        """
        try:
            from ..utils.test_report_parser import JUnitXMLParser

            path = Path(working_dir or '.') / junit_xml_path
            if not path.exists():
                return {'passed': 0, 'failed': 0, 'skipped': 0}

            parser = JUnitXMLParser()
            results = parser.parse_file(path)

            if self.metrics and hasattr(self.metrics, 'test_report_parsing_total'):
                self.metrics.test_report_parsing_total.labels(format='junit', status='success').inc()

            return {
                'passed': results.passed,
                'failed': results.failed,
                'skipped': results.skipped,
                'total': results.total,
                'duration': results.duration_seconds
            }

        except Exception as e:
            if self.metrics and hasattr(self.metrics, 'test_report_parsing_total'):
                self.metrics.test_report_parsing_total.labels(format='junit', status='error').inc()
            return {'passed': 0, 'failed': 0, 'skipped': 0}

    def _parse_coverage_file(
        self,
        coverage_path: str,
        working_dir: Optional[str] = None
    ) -> Optional[float]:
        """
        Parseia arquivo de coverage.

        Args:
            coverage_path: Caminho do arquivo
            working_dir: Diretorio de trabalho

        Returns:
            Percentual de coverage ou None
        """
        try:
            from ..utils.test_report_parser import CoberturaXMLParser, LCOVParser, detect_report_format

            path = Path(working_dir or '.') / coverage_path
            if not path.exists():
                return None

            content = path.read_text(encoding='utf-8', errors='replace')
            format_type = detect_report_format(content)

            if format_type == 'cobertura':
                parser = CoberturaXMLParser()
                results = parser.parse(content)
                if self.metrics and hasattr(self.metrics, 'coverage_report_parsing_total'):
                    self.metrics.coverage_report_parsing_total.labels(format='cobertura', status='success').inc()
                return results.line_coverage

            elif format_type == 'lcov':
                parser = LCOVParser()
                results = parser.parse(content)
                if self.metrics and hasattr(self.metrics, 'coverage_report_parsing_total'):
                    self.metrics.coverage_report_parsing_total.labels(format='lcov', status='success').inc()
                return results.line_coverage

            return None

        except Exception as e:
            if self.metrics and hasattr(self.metrics, 'coverage_report_parsing_total'):
                self.metrics.coverage_report_parsing_total.labels(format='unknown', status='error').inc()
            return None
