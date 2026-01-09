"""
Cliente CI/CD unificado para execucao de pipelines e obtencao de resultados de teste.

Este cliente implementa uma interface unificada que delega para os clientes especificos
(GitHub Actions, GitLab CI, Jenkins) e fornece operacoes compartilhadas:
- Trigger de pipelines/workflows/jobs
- Polling de status com timeout
- Fetch de test reports (JUnit XML)
- Fetch de coverage reports (Cobertura/LCOV)
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import structlog


logger = structlog.get_logger()


class CICDProvider(str, Enum):
    """Provedores CI/CD suportados."""
    GITHUB_ACTIONS = 'github_actions'
    GITLAB_CI = 'gitlab_ci'
    JENKINS = 'jenkins'


class CICDClientError(Exception):
    """Erro generico do cliente CI/CD."""
    def __init__(self, message: str, provider: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class CICDTimeoutError(Exception):
    """Timeout aguardando pipeline/workflow/job."""
    def __init__(self, message: str, provider: Optional[str] = None):
        super().__init__(message)
        self.provider = provider


@dataclass
class CICDRunStatus:
    """
    Representa status unificado de uma execucao CI/CD.

    Compativel com GitHub Actions, GitLab CI e Jenkins.
    """
    run_id: str
    provider: str
    status: str  # 'pending', 'running', 'success', 'failed', 'cancelled', 'timeout'
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    coverage: Optional[float] = None
    duration_seconds: Optional[float] = None
    logs: List[str] = field(default_factory=list)
    url: Optional[str] = None
    raw_status: Optional[str] = None  # Status original do provider

    @property
    def success(self) -> bool:
        return self.status == 'success'

    @property
    def completed(self) -> bool:
        return self.status in ('success', 'failed', 'cancelled', 'timeout')

    @property
    def total_tests(self) -> int:
        return self.tests_passed + self.tests_failed + self.tests_skipped + self.tests_errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            'run_id': self.run_id,
            'provider': self.provider,
            'status': self.status,
            'success': self.success,
            'tests_passed': self.tests_passed,
            'tests_failed': self.tests_failed,
            'tests_skipped': self.tests_skipped,
            'tests_errors': self.tests_errors,
            'total_tests': self.total_tests,
            'coverage': self.coverage,
            'duration_seconds': self.duration_seconds,
            'url': self.url
        }


@dataclass
class TestReport:
    """Relatorio de testes unificado."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    test_cases: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100.0

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0


@dataclass
class CoverageReport:
    """Relatorio de coverage unificado."""
    line_coverage: float = 0.0
    branch_coverage: Optional[float] = None
    function_coverage: Optional[float] = None
    lines_covered: int = 0
    lines_total: int = 0


class CICDClient:
    """
    Cliente CI/CD unificado que delega para provedores especificos.

    Fornece interface comum para:
    - Trigger de execucoes
    - Polling de status
    - Fetch de test e coverage reports

    Uso:
        client = CICDClient(
            github_actions_client=gh_client,
            gitlab_ci_client=gl_client,
            jenkins_client=jenkins_client
        )
        await client.start()

        # Trigger
        run_id = await client.trigger(
            provider='github_actions',
            repo='owner/repo',
            workflow_id='test.yml',
            ref='main'
        )

        # Poll
        status = await client.wait_for_completion(
            provider='github_actions',
            run_id=run_id,
            repo='owner/repo'
        )

        # Fetch reports
        test_report = await client.fetch_test_report(
            provider='github_actions',
            run_id=run_id,
            repo='owner/repo'
        )
    """

    def __init__(
        self,
        github_actions_client=None,
        gitlab_ci_client=None,
        jenkins_client=None,
        default_timeout: int = 900,
        default_poll_interval: int = 15
    ):
        """
        Inicializa cliente CI/CD unificado.

        Args:
            github_actions_client: Cliente GitHub Actions opcional
            gitlab_ci_client: Cliente GitLab CI opcional
            jenkins_client: Cliente Jenkins opcional
            default_timeout: Timeout padrao em segundos
            default_poll_interval: Intervalo de polling padrao em segundos
        """
        self.github_actions_client = github_actions_client
        self.gitlab_ci_client = gitlab_ci_client
        self.jenkins_client = jenkins_client
        self.default_timeout = default_timeout
        self.default_poll_interval = default_poll_interval
        self.logger = logger.bind(service='cicd_client')

    def has_provider(self, provider: str) -> bool:
        """Verifica se um provider esta disponivel."""
        if provider == CICDProvider.GITHUB_ACTIONS:
            return self.github_actions_client is not None
        elif provider == CICDProvider.GITLAB_CI:
            return self.gitlab_ci_client is not None
        elif provider == CICDProvider.JENKINS:
            return self.jenkins_client is not None
        return False

    def available_providers(self) -> List[str]:
        """Lista providers disponiveis."""
        providers = []
        if self.github_actions_client:
            providers.append(CICDProvider.GITHUB_ACTIONS)
        if self.gitlab_ci_client:
            providers.append(CICDProvider.GITLAB_CI)
        if self.jenkins_client:
            providers.append(CICDProvider.JENKINS)
        return providers

    async def start(self):
        """Inicializa todos os clientes disponiveis."""
        if self.github_actions_client and hasattr(self.github_actions_client, 'start'):
            await self.github_actions_client.start()
        if self.gitlab_ci_client and hasattr(self.gitlab_ci_client, 'start'):
            await self.gitlab_ci_client.start()
        if self.jenkins_client and hasattr(self.jenkins_client, 'start'):
            await self.jenkins_client.start()
        self.logger.info('cicd_client_started', providers=self.available_providers())

    async def close(self):
        """Fecha todos os clientes."""
        if self.github_actions_client and hasattr(self.github_actions_client, 'close'):
            await self.github_actions_client.close()
        if self.gitlab_ci_client and hasattr(self.gitlab_ci_client, 'close'):
            await self.gitlab_ci_client.close()
        if self.jenkins_client and hasattr(self.jenkins_client, 'close'):
            await self.jenkins_client.close()
        self.logger.info('cicd_client_closed')

    async def trigger(
        self,
        provider: str,
        **kwargs
    ) -> str:
        """
        Dispara uma execucao CI/CD.

        Args:
            provider: Provider a usar ('github_actions', 'gitlab_ci', 'jenkins')
            **kwargs: Argumentos especificos do provider

        Returns:
            ID da execucao (run_id, pipeline_id, ou queue_id)

        Raises:
            CICDClientError: Provider nao disponivel ou erro na API
        """
        self.logger.info('cicd_trigger', provider=provider, kwargs_keys=list(kwargs.keys()))

        if provider == CICDProvider.GITHUB_ACTIONS:
            if not self.github_actions_client:
                raise CICDClientError('GitHub Actions client not configured', provider=provider)

            repo = kwargs.get('repo')
            workflow_id = kwargs.get('workflow_id')
            ref = kwargs.get('ref', 'main')
            inputs = kwargs.get('inputs', {})

            try:
                run_id = await self.github_actions_client.trigger_workflow(
                    repo=repo,
                    workflow_id=workflow_id,
                    ref=ref,
                    inputs=inputs
                )
                return run_id
            except Exception as e:
                raise CICDClientError(f'GitHub Actions trigger failed: {e}', provider=provider)

        elif provider == CICDProvider.GITLAB_CI:
            if not self.gitlab_ci_client:
                raise CICDClientError('GitLab CI client not configured', provider=provider)

            project_id = kwargs.get('project_id')
            ref = kwargs.get('ref', 'main')
            variables = kwargs.get('variables', {})

            try:
                pipeline_id = await self.gitlab_ci_client.trigger_pipeline(
                    project_id=project_id,
                    ref=ref,
                    variables=variables
                )
                return pipeline_id
            except Exception as e:
                raise CICDClientError(f'GitLab CI trigger failed: {e}', provider=provider)

        elif provider == CICDProvider.JENKINS:
            if not self.jenkins_client:
                raise CICDClientError('Jenkins client not configured', provider=provider)

            job_name = kwargs.get('job_name')
            parameters = kwargs.get('parameters', {})

            try:
                queue_id = await self.jenkins_client.trigger_job(
                    job_name=job_name,
                    parameters=parameters
                )
                return str(queue_id)
            except Exception as e:
                raise CICDClientError(f'Jenkins trigger failed: {e}', provider=provider)

        else:
            raise CICDClientError(f'Unknown provider: {provider}', provider=provider)

    async def poll_status(
        self,
        provider: str,
        run_id: str,
        **kwargs
    ) -> CICDRunStatus:
        """
        Obtem status atual de uma execucao.

        Args:
            provider: Provider a usar
            run_id: ID da execucao
            **kwargs: Argumentos especificos do provider

        Returns:
            Status atual da execucao
        """
        if provider == CICDProvider.GITHUB_ACTIONS:
            if not self.github_actions_client:
                raise CICDClientError('GitHub Actions client not configured', provider=provider)

            repo = kwargs.get('repo')
            status = await self.github_actions_client.get_workflow_run(repo, run_id)

            return CICDRunStatus(
                run_id=status.run_id,
                provider=provider,
                status=self._normalize_github_status(status.status, status.conclusion),
                tests_passed=status.passed,
                tests_failed=status.failed,
                tests_skipped=status.skipped,
                tests_errors=status.errors,
                coverage=status.coverage,
                duration_seconds=status.duration_seconds,
                url=status.html_url,
                raw_status=f'{status.status}/{status.conclusion}'
            )

        elif provider == CICDProvider.GITLAB_CI:
            if not self.gitlab_ci_client:
                raise CICDClientError('GitLab CI client not configured', provider=provider)

            project_id = kwargs.get('project_id')
            status = await self.gitlab_ci_client.get_pipeline_status(project_id, run_id)

            return CICDRunStatus(
                run_id=status.pipeline_id,
                provider=provider,
                status=self._normalize_gitlab_status(status.status),
                tests_passed=status.tests_passed,
                tests_failed=status.tests_failed,
                tests_skipped=status.tests_skipped,
                tests_errors=status.tests_errors,
                coverage=status.coverage,
                duration_seconds=status.duration_seconds,
                url=status.web_url,
                raw_status=status.status
            )

        elif provider == CICDProvider.JENKINS:
            if not self.jenkins_client:
                raise CICDClientError('Jenkins client not configured', provider=provider)

            job_name = kwargs.get('job_name')
            build_number = kwargs.get('build_number')

            if build_number is None:
                # Precisamos obter o build_number do queue_id
                queue_id = int(run_id)
                build_number = await self.jenkins_client.wait_for_build_number(
                    job_name=job_name,
                    queue_id=queue_id,
                    poll_interval=5,
                    timeout=300
                )

            status = await self.jenkins_client.get_build_status(job_name, build_number)

            return CICDRunStatus(
                run_id=str(status.build_number),
                provider=provider,
                status=self._normalize_jenkins_status(status.status),
                tests_passed=status.tests_passed,
                tests_failed=status.tests_failed,
                tests_skipped=status.tests_skipped,
                coverage=status.coverage,
                duration_seconds=status.duration_seconds,
                url=status.url,
                raw_status=status.status
            )

        else:
            raise CICDClientError(f'Unknown provider: {provider}', provider=provider)

    async def wait_for_completion(
        self,
        provider: str,
        run_id: str,
        poll_interval: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> CICDRunStatus:
        """
        Aguarda execucao completar via polling.

        Args:
            provider: Provider a usar
            run_id: ID da execucao
            poll_interval: Intervalo de polling em segundos
            timeout: Timeout total em segundos
            **kwargs: Argumentos especificos do provider

        Returns:
            Status final da execucao

        Raises:
            CICDTimeoutError: Timeout aguardando execucao
        """
        poll_interval = poll_interval or self.default_poll_interval
        timeout = timeout or self.default_timeout

        self.logger.info(
            'cicd_waiting_for_completion',
            provider=provider,
            run_id=run_id,
            timeout=timeout
        )

        if provider == CICDProvider.GITHUB_ACTIONS:
            if not self.github_actions_client:
                raise CICDClientError('GitHub Actions client not configured', provider=provider)

            repo = kwargs.get('repo')
            try:
                status = await self.github_actions_client.wait_for_run(
                    run_id=run_id,
                    poll_interval=poll_interval,
                    timeout=timeout,
                    repo=repo
                )

                return CICDRunStatus(
                    run_id=status.run_id,
                    provider=provider,
                    status=self._normalize_github_status(status.status, status.conclusion),
                    tests_passed=status.passed,
                    tests_failed=status.failed,
                    tests_skipped=status.skipped,
                    tests_errors=status.errors,
                    coverage=status.coverage,
                    duration_seconds=status.duration_seconds,
                    url=status.html_url,
                    raw_status=f'{status.status}/{status.conclusion}'
                )
            except Exception as e:
                if 'timeout' in str(e).lower():
                    raise CICDTimeoutError(str(e), provider=provider)
                raise CICDClientError(str(e), provider=provider)

        elif provider == CICDProvider.GITLAB_CI:
            if not self.gitlab_ci_client:
                raise CICDClientError('GitLab CI client not configured', provider=provider)

            project_id = kwargs.get('project_id')
            try:
                status = await self.gitlab_ci_client.wait_for_pipeline(
                    project_id=project_id,
                    pipeline_id=run_id,
                    poll_interval=poll_interval,
                    timeout=timeout
                )

                return CICDRunStatus(
                    run_id=status.pipeline_id,
                    provider=provider,
                    status=self._normalize_gitlab_status(status.status),
                    tests_passed=status.tests_passed,
                    tests_failed=status.tests_failed,
                    tests_skipped=status.tests_skipped,
                    tests_errors=status.tests_errors,
                    coverage=status.coverage,
                    duration_seconds=status.duration_seconds,
                    url=status.web_url,
                    raw_status=status.status
                )
            except Exception as e:
                if 'timeout' in str(e).lower():
                    raise CICDTimeoutError(str(e), provider=provider)
                raise CICDClientError(str(e), provider=provider)

        elif provider == CICDProvider.JENKINS:
            if not self.jenkins_client:
                raise CICDClientError('Jenkins client not configured', provider=provider)

            job_name = kwargs.get('job_name')
            build_number = kwargs.get('build_number')

            if build_number is None:
                queue_id = int(run_id)
                build_number = await self.jenkins_client.wait_for_build_number(
                    job_name=job_name,
                    queue_id=queue_id,
                    poll_interval=5,
                    timeout=300
                )

            try:
                status = await self.jenkins_client.wait_for_build(
                    job_name=job_name,
                    build_number=build_number,
                    poll_interval=poll_interval,
                    timeout=timeout
                )

                return CICDRunStatus(
                    run_id=str(status.build_number),
                    provider=provider,
                    status=self._normalize_jenkins_status(status.status),
                    tests_passed=status.tests_passed,
                    tests_failed=status.tests_failed,
                    tests_skipped=status.tests_skipped,
                    coverage=status.coverage,
                    duration_seconds=status.duration_seconds,
                    url=status.url,
                    raw_status=status.status
                )
            except Exception as e:
                if 'timeout' in str(e).lower():
                    raise CICDTimeoutError(str(e), provider=provider)
                raise CICDClientError(str(e), provider=provider)

        else:
            raise CICDClientError(f'Unknown provider: {provider}', provider=provider)

    async def fetch_test_report(
        self,
        provider: str,
        run_id: str,
        **kwargs
    ) -> TestReport:
        """
        Obtem relatorio de testes de uma execucao.

        Args:
            provider: Provider a usar
            run_id: ID da execucao
            **kwargs: Argumentos especificos do provider

        Returns:
            Relatorio de testes
        """
        if provider == CICDProvider.GITHUB_ACTIONS:
            if not self.github_actions_client:
                raise CICDClientError('GitHub Actions client not configured', provider=provider)

            repo = kwargs.get('repo')
            results = await self.github_actions_client.get_test_results(repo, run_id)

            return TestReport(
                total=results.get('total', 0),
                passed=results.get('passed', 0),
                failed=results.get('failed', 0),
                skipped=results.get('skipped', 0),
                errors=results.get('errors', 0),
                test_cases=results.get('test_cases', [])
            )

        elif provider == CICDProvider.GITLAB_CI:
            if not self.gitlab_ci_client:
                raise CICDClientError('GitLab CI client not configured', provider=provider)

            project_id = kwargs.get('project_id')
            report = await self.gitlab_ci_client.get_test_report(project_id, run_id)

            total = report.get('total_count', 0)
            failed = report.get('failed_count', 0)
            error = report.get('error_count', 0)
            skipped = report.get('skipped_count', 0)
            passed = total - failed - error - skipped

            return TestReport(
                total=total,
                passed=passed,
                failed=failed,
                skipped=skipped,
                errors=error
            )

        elif provider == CICDProvider.JENKINS:
            if not self.jenkins_client:
                raise CICDClientError('Jenkins client not configured', provider=provider)

            job_name = kwargs.get('job_name')
            build_number = int(run_id)
            report = await self.jenkins_client.get_test_report(job_name, build_number)

            return TestReport(
                total=report.get('totalCount', 0),
                passed=report.get('passCount', 0),
                failed=report.get('failCount', 0),
                skipped=report.get('skipCount', 0),
                duration_seconds=report.get('duration', 0)
            )

        else:
            raise CICDClientError(f'Unknown provider: {provider}', provider=provider)

    async def fetch_coverage_report(
        self,
        provider: str,
        run_id: str,
        **kwargs
    ) -> Optional[CoverageReport]:
        """
        Obtem relatorio de coverage de uma execucao.

        Args:
            provider: Provider a usar
            run_id: ID da execucao
            **kwargs: Argumentos especificos do provider

        Returns:
            Relatorio de coverage ou None se nao disponivel
        """
        if provider == CICDProvider.GITHUB_ACTIONS:
            if not self.github_actions_client:
                raise CICDClientError('GitHub Actions client not configured', provider=provider)

            repo = kwargs.get('repo')
            report = await self.github_actions_client.get_coverage_report(repo, run_id)

            if report is None:
                return None

            return CoverageReport(line_coverage=report.get('line_coverage', 0.0))

        elif provider == CICDProvider.GITLAB_CI:
            if not self.gitlab_ci_client:
                raise CICDClientError('GitLab CI client not configured', provider=provider)

            project_id = kwargs.get('project_id')

            # GitLab pode ter coverage no pipeline status
            status = await self.gitlab_ci_client.get_pipeline_status(project_id, run_id)
            if status.coverage is not None:
                return CoverageReport(line_coverage=status.coverage)

            return None

        elif provider == CICDProvider.JENKINS:
            if not self.jenkins_client:
                raise CICDClientError('Jenkins client not configured', provider=provider)

            job_name = kwargs.get('job_name')
            build_number = int(run_id)
            coverage = await self.jenkins_client.get_coverage_report(job_name, build_number)

            if coverage is None:
                return None

            return CoverageReport(line_coverage=coverage)

        else:
            raise CICDClientError(f'Unknown provider: {provider}', provider=provider)

    def _normalize_github_status(self, status: str, conclusion: Optional[str]) -> str:
        """Normaliza status GitHub Actions para formato padrao."""
        if status == 'completed':
            if conclusion == 'success':
                return 'success'
            elif conclusion in ('failure', 'timed_out'):
                return 'failed'
            elif conclusion == 'cancelled':
                return 'cancelled'
            else:
                return 'failed'
        elif status in ('queued', 'waiting', 'pending'):
            return 'pending'
        elif status == 'in_progress':
            return 'running'
        return 'pending'

    def _normalize_gitlab_status(self, status: str) -> str:
        """Normaliza status GitLab CI para formato padrao."""
        status_map = {
            'success': 'success',
            'failed': 'failed',
            'canceled': 'cancelled',
            'skipped': 'cancelled',
            'pending': 'pending',
            'running': 'running',
            'created': 'pending',
            'waiting_for_resource': 'pending',
            'preparing': 'pending',
            'manual': 'pending'
        }
        return status_map.get(status, 'pending')

    def _normalize_jenkins_status(self, status: str) -> str:
        """Normaliza status Jenkins para formato padrao."""
        status_map = {
            'SUCCESS': 'success',
            'FAILURE': 'failed',
            'UNSTABLE': 'failed',
            'ABORTED': 'cancelled',
            'NOT_BUILT': 'cancelled',
            'BUILDING': 'running'
        }
        return status_map.get(status, 'pending')
