"""
Cliente GitLab CI para execucao de pipelines e obtencao de resultados de teste.

Este cliente implementa integracao com GitLab CI/CD API para disparar pipelines,
monitorar status e coletar resultados de testes/coverage.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


logger = structlog.get_logger()


class GitLabCIAPIError(Exception):
    """Erro de chamada a API do GitLab CI."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GitLabCITimeoutError(Exception):
    """Timeout aguardando pipeline do GitLab CI."""
    pass


@dataclass
class PipelineStatus:
    """Representa status de um pipeline GitLab CI."""
    pipeline_id: str
    status: str  # 'running', 'success', 'failed', 'canceled', 'pending'
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    coverage: Optional[float] = None
    duration_seconds: Optional[float] = None
    logs: Optional[List[str]] = field(default_factory=list)
    web_url: Optional[str] = None
    ref: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == 'success'

    @property
    def completed(self) -> bool:
        return self.status in ('success', 'failed', 'canceled', 'skipped')


@dataclass
class TestCase:
    """Representa um caso de teste individual."""
    name: str
    classname: str
    execution_time: float
    status: str  # 'passed', 'failed', 'skipped', 'error'
    message: Optional[str] = None
    stack_trace: Optional[str] = None
    system_output: Optional[str] = None


@dataclass
class TestSuiteReport:
    """Representa um relatorio de suite de testes."""
    name: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    total_time: float
    test_cases: List[TestCase] = field(default_factory=list)


class GitLabCIClient:
    """
    Cliente REST para GitLab CI API.

    Suporta:
    - Trigger de pipelines
    - Polling de status com timeout
    - Obtencao de test reports (JUnit XML)
    - Obtencao de coverage reports
    - Retry automatico com exponential backoff
    """

    def __init__(
        self,
        token: str,
        base_url: str = 'https://gitlab.com',
        timeout: int = 900,
        verify_ssl: bool = True
    ):
        """
        Inicializa cliente GitLab CI.

        Args:
            token: Token de acesso privado GitLab (PAT ou CI_JOB_TOKEN)
            base_url: URL base da instancia GitLab
            timeout: Timeout padrao para operacoes em segundos
            verify_ssl: Verificar certificado SSL
        """
        self.token = token
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None
        self.logger = logger.bind(service='gitlab_ci_client')

    @classmethod
    def from_env(cls, config=None) -> 'GitLabCIClient':
        """
        Cria cliente a partir de variaveis de ambiente.

        Environment Variables:
            GITLAB_TOKEN: Token de acesso privado
            GITLAB_URL: URL da instancia GitLab (padrao: https://gitlab.com)

        Args:
            config: Objeto de configuracao opcional

        Returns:
            Instancia configurada do cliente

        Raises:
            ValueError: Se token nao estiver configurado
        """
        token = os.getenv('GITLAB_TOKEN') or getattr(config, 'gitlab_token', None)
        if not token:
            raise ValueError('GitLab token not configured (GITLAB_TOKEN or config.gitlab_token)')

        base_url = os.getenv('GITLAB_URL') or getattr(config, 'gitlab_url', 'https://gitlab.com')
        timeout = getattr(config, 'gitlab_timeout_seconds', 900)
        verify_ssl = getattr(config, 'gitlab_tls_verify', True)

        return cls(token, base_url=base_url, timeout=timeout, verify_ssl=verify_ssl)

    async def start(self):
        """Inicializa cliente HTTP assincrono."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    'PRIVATE-TOKEN': self.token,
                    'Content-Type': 'application/json'
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
                verify=self.verify_ssl
            )
            self.logger.info('gitlab_ci_client_started', base_url=self.base_url)

    async def close(self):
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self.logger.info('gitlab_ci_client_closed')

    @property
    def client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP, inicializando se necessario."""
        if self._client is None:
            raise RuntimeError('GitLabCIClient not started. Call start() first.')
        return self._client

    def _encode_project_id(self, project_id: str) -> str:
        """Codifica project_id para URL (namespace/project -> namespace%2Fproject)."""
        if '/' in project_id and not '%2F' in project_id:
            return project_id.replace('/', '%2F')
        return project_id

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def trigger_pipeline(
        self,
        project_id: str,
        ref: str = 'main',
        variables: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Dispara um novo pipeline no GitLab CI.

        Args:
            project_id: ID numerico ou path do projeto (ex: 'namespace/project')
            ref: Branch/tag para executar (padrao: 'main')
            variables: Variaveis CI/CD para o pipeline

        Returns:
            ID do pipeline criado

        Raises:
            GitLabCIAPIError: Erro na API
            GitLabCITimeoutError: Timeout na requisicao
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipeline'

        payload: Dict[str, Any] = {'ref': ref}
        if variables:
            payload['variables'] = [
                {'key': k, 'value': v} for k, v in variables.items()
            ]

        self.logger.info(
            'gitlab_trigger_pipeline',
            project_id=project_id,
            ref=ref,
            variables_count=len(variables) if variables else 0
        )

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            pipeline_id = str(data.get('id'))

            self.logger.info(
                'gitlab_pipeline_triggered',
                project_id=project_id,
                pipeline_id=pipeline_id,
                ref=ref,
                web_url=data.get('web_url')
            )

            return pipeline_id

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'gitlab_trigger_pipeline_failed',
                project_id=project_id,
                status_code=e.response.status_code,
                error=e.response.text
            )
            raise GitLabCIAPIError(
                f'Failed to trigger pipeline for {project_id}: {e.response.text}',
                status_code=e.response.status_code
            )
        except httpx.TimeoutException as e:
            self.logger.error('gitlab_trigger_pipeline_timeout', project_id=project_id)
            raise GitLabCITimeoutError(f'Timeout triggering pipeline for {project_id}')

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_pipeline_status(
        self,
        project_id: str,
        pipeline_id: str
    ) -> PipelineStatus:
        """
        Obtem status atual de um pipeline.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            Status do pipeline

        Raises:
            GitLabCIAPIError: Erro na API
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}'

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()

            return PipelineStatus(
                pipeline_id=str(data.get('id')),
                status=data.get('status', 'unknown'),
                coverage=float(data.get('coverage')) if data.get('coverage') else None,
                duration_seconds=float(data.get('duration')) if data.get('duration') else None,
                web_url=data.get('web_url'),
                ref=data.get('ref')
            )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'gitlab_get_pipeline_status_failed',
                project_id=project_id,
                pipeline_id=pipeline_id,
                status_code=e.response.status_code
            )
            raise GitLabCIAPIError(
                f'Failed to get pipeline status: {e.response.text}',
                status_code=e.response.status_code
            )

    async def wait_for_pipeline(
        self,
        project_id: str,
        pipeline_id: str,
        poll_interval: int = 15,
        timeout: Optional[int] = None
    ) -> PipelineStatus:
        """
        Aguarda pipeline completar via polling.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos (padrao: self.timeout)

        Returns:
            Status final do pipeline

        Raises:
            GitLabCITimeoutError: Timeout aguardando pipeline
        """
        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()

        self.logger.info(
            'gitlab_waiting_for_pipeline',
            project_id=project_id,
            pipeline_id=pipeline_id,
            timeout=timeout
        )

        while True:
            status = await self.get_pipeline_status(project_id, pipeline_id)

            self.logger.debug(
                'gitlab_pipeline_poll',
                pipeline_id=pipeline_id,
                status=status.status
            )

            if status.completed:
                # Tentar obter test report se pipeline completou
                try:
                    test_report = await self.get_test_report(project_id, pipeline_id)
                    status.tests_passed = test_report.get('total_count', 0) - test_report.get('failed_count', 0) - test_report.get('error_count', 0)
                    status.tests_failed = test_report.get('failed_count', 0)
                    status.tests_errors = test_report.get('error_count', 0)
                    status.tests_skipped = test_report.get('skipped_count', 0)
                except Exception as e:
                    self.logger.warning(
                        'gitlab_test_report_fetch_failed',
                        pipeline_id=pipeline_id,
                        error=str(e)
                    )

                self.logger.info(
                    'gitlab_pipeline_completed',
                    pipeline_id=pipeline_id,
                    status=status.status,
                    duration=status.duration_seconds,
                    tests_passed=status.tests_passed,
                    tests_failed=status.tests_failed
                )
                return status

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                self.logger.warning(
                    'gitlab_pipeline_timeout',
                    pipeline_id=pipeline_id,
                    last_status=status.status,
                    elapsed=elapsed
                )
                raise GitLabCITimeoutError(
                    f'Timeout waiting for pipeline {pipeline_id} '
                    f'(last status: {status.status}, elapsed: {elapsed:.1f}s)'
                )

            await asyncio.sleep(poll_interval)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_test_report(
        self,
        project_id: str,
        pipeline_id: str
    ) -> Dict[str, Any]:
        """
        Obtem relatorio de testes do pipeline (JUnit XML agregado).

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            Relatorio de testes agregado

        Raises:
            GitLabCIAPIError: Erro na API ou report nao disponivel
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}/test_report'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.logger.warning(
                    'gitlab_test_report_not_found',
                    project_id=project_id,
                    pipeline_id=pipeline_id
                )
                return {
                    'total_count': 0,
                    'success_count': 0,
                    'failed_count': 0,
                    'error_count': 0,
                    'skipped_count': 0,
                    'test_suites': []
                }
            raise GitLabCIAPIError(
                f'Failed to get test report: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_test_report_summary(
        self,
        project_id: str,
        pipeline_id: str
    ) -> Dict[str, Any]:
        """
        Obtem resumo do relatorio de testes.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            Resumo do relatorio de testes

        Raises:
            GitLabCIAPIError: Erro na API
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}/test_report_summary'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {
                    'total': {'count': 0, 'success': 0, 'failed': 0, 'skipped': 0, 'error': 0},
                    'test_suites': []
                }
            raise GitLabCIAPIError(
                f'Failed to get test report summary: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_pipeline_jobs(
        self,
        project_id: str,
        pipeline_id: str
    ) -> List[Dict[str, Any]]:
        """
        Lista jobs de um pipeline.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            Lista de jobs
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}/jobs'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise GitLabCIAPIError(
                f'Failed to get pipeline jobs: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_job_artifacts(
        self,
        project_id: str,
        job_id: str,
        artifact_path: Optional[str] = None
    ) -> bytes:
        """
        Baixa artifacts de um job.

        Args:
            project_id: ID ou path do projeto
            job_id: ID do job
            artifact_path: Caminho especifico dentro do artifact (opcional)

        Returns:
            Conteudo binario do artifact

        Raises:
            GitLabCIAPIError: Erro na API ou artifact nao encontrado
        """
        encoded_project = self._encode_project_id(project_id)

        if artifact_path:
            url = f'{self.base_url}/api/v4/projects/{encoded_project}/jobs/{job_id}/artifacts/{artifact_path}'
        else:
            url = f'{self.base_url}/api/v4/projects/{encoded_project}/jobs/{job_id}/artifacts'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.content

        except httpx.HTTPStatusError as e:
            raise GitLabCIAPIError(
                f'Failed to get job artifacts: {e.response.text}',
                status_code=e.response.status_code
            )

    async def get_job_trace(
        self,
        project_id: str,
        job_id: str
    ) -> str:
        """
        Obtem log de execucao de um job.

        Args:
            project_id: ID ou path do projeto
            job_id: ID do job

        Returns:
            Log do job em texto
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/jobs/{job_id}/trace'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text

        except httpx.HTTPStatusError as e:
            self.logger.warning(
                'gitlab_get_job_trace_failed',
                job_id=job_id,
                error=str(e)
            )
            return ''

    async def download_and_parse_artifacts(
        self,
        project_id: str,
        pipeline_id: str,
        junit_artifact_paths: Optional[List[str]] = None,
        coverage_artifact_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Baixa e parseia artifacts de jobs do pipeline para extrair test e coverage reports.

        Procura por arquivos JUnit XML e Cobertura/LCOV nos artifacts dos jobs.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline
            junit_artifact_paths: Caminhos especificos para JUnit XML (opcional)
            coverage_artifact_paths: Caminhos especificos para coverage (opcional)

        Returns:
            Dicionario com resultados parseados:
            {
                'tests_passed': int,
                'tests_failed': int,
                'tests_skipped': int,
                'tests_errors': int,
                'coverage': float or None
            }
        """
        import io
        import zipfile

        results = {
            'tests_passed': 0,
            'tests_failed': 0,
            'tests_skipped': 0,
            'tests_errors': 0,
            'coverage': None
        }

        # Paths padrao para procurar
        default_junit_paths = junit_artifact_paths or [
            'junit.xml', 'report.xml', 'test-results.xml',
            'results/junit.xml', 'test-reports/junit.xml',
            'reports/junit.xml', 'target/surefire-reports/*.xml'
        ]
        default_coverage_paths = coverage_artifact_paths or [
            'coverage.xml', 'cobertura.xml', 'coverage/cobertura.xml',
            'coverage.info', 'lcov.info', 'coverage/lcov.info'
        ]

        try:
            # Obter lista de jobs do pipeline
            jobs = await self.get_pipeline_jobs(project_id, pipeline_id)

            for job in jobs:
                job_id = str(job.get('id'))
                job_name = job.get('name', '')
                has_artifacts = job.get('artifacts', [])

                if not has_artifacts:
                    continue

                self.logger.debug(
                    'gitlab_checking_job_artifacts',
                    pipeline_id=pipeline_id,
                    job_id=job_id,
                    job_name=job_name
                )

                try:
                    # Baixar artifacts do job (ZIP)
                    artifact_content = await self.get_job_artifacts(project_id, job_id)

                    # Parsear conteudo do ZIP
                    parsed = self._parse_artifact_zip(
                        artifact_content,
                        default_junit_paths,
                        default_coverage_paths
                    )

                    # Agregar resultados
                    results['tests_passed'] += parsed.get('tests_passed', 0)
                    results['tests_failed'] += parsed.get('tests_failed', 0)
                    results['tests_skipped'] += parsed.get('tests_skipped', 0)
                    results['tests_errors'] += parsed.get('tests_errors', 0)

                    if parsed.get('coverage') is not None and results['coverage'] is None:
                        results['coverage'] = parsed['coverage']

                except Exception as e:
                    self.logger.warning(
                        'gitlab_artifact_parse_failed',
                        job_id=job_id,
                        error=str(e)
                    )
                    continue

            self.logger.info(
                'gitlab_artifacts_parsed',
                pipeline_id=pipeline_id,
                tests_passed=results['tests_passed'],
                tests_failed=results['tests_failed'],
                coverage=results['coverage']
            )

        except Exception as e:
            self.logger.warning(
                'gitlab_download_artifacts_failed',
                pipeline_id=pipeline_id,
                error=str(e)
            )

        return results

    def _parse_artifact_zip(
        self,
        zip_content: bytes,
        junit_paths: List[str],
        coverage_paths: List[str]
    ) -> Dict[str, Any]:
        """
        Parseia conteudo de um ZIP de artifacts.

        Args:
            zip_content: Conteudo binario do ZIP
            junit_paths: Padroes de caminho para JUnit XML
            coverage_paths: Padroes de caminho para coverage

        Returns:
            Resultados parseados
        """
        import io
        import zipfile
        import fnmatch

        results = {
            'tests_passed': 0,
            'tests_failed': 0,
            'tests_skipped': 0,
            'tests_errors': 0,
            'coverage': None
        }

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                for filename in zf.namelist():
                    # Verificar se e JUnit XML
                    is_junit = any(
                        fnmatch.fnmatch(filename, pattern) or filename.endswith(pattern.split('/')[-1])
                        for pattern in junit_paths
                    )

                    if is_junit and filename.endswith('.xml'):
                        try:
                            content = zf.read(filename).decode('utf-8', errors='replace')
                            if '<testsuite' in content or '<testsuites' in content:
                                parsed = self._parse_junit_xml(content)
                                results['tests_passed'] += parsed.get('passed', 0)
                                results['tests_failed'] += parsed.get('failed', 0)
                                results['tests_skipped'] += parsed.get('skipped', 0)
                                results['tests_errors'] += parsed.get('errors', 0)
                        except Exception:
                            pass

                    # Verificar se e coverage report
                    is_coverage = any(
                        fnmatch.fnmatch(filename, pattern) or filename.endswith(pattern.split('/')[-1])
                        for pattern in coverage_paths
                    )

                    if is_coverage and results['coverage'] is None:
                        try:
                            content = zf.read(filename).decode('utf-8', errors='replace')
                            coverage = self._parse_coverage_report(content, filename)
                            if coverage is not None:
                                results['coverage'] = coverage
                        except Exception:
                            pass

        except Exception as e:
            self.logger.warning('gitlab_parse_zip_failed', error=str(e))

        return results

    def _parse_junit_xml(self, content: str) -> Dict[str, int]:
        """
        Parseia conteudo JUnit XML.

        Args:
            content: Conteudo XML

        Returns:
            Contagem de testes
        """
        import xml.etree.ElementTree as ET

        results = {'passed': 0, 'failed': 0, 'skipped': 0, 'errors': 0}

        try:
            root = ET.fromstring(content)

            # Handle both <testsuites> e <testsuite> como root
            if root.tag == 'testsuites':
                suites = root.findall('testsuite')
            elif root.tag == 'testsuite':
                suites = [root]
            else:
                return results

            for suite in suites:
                tests = int(suite.get('tests', 0))
                failures = int(suite.get('failures', 0))
                errors = int(suite.get('errors', 0))
                skipped = int(suite.get('skipped', 0))

                results['failed'] += failures
                results['errors'] += errors
                results['skipped'] += skipped
                results['passed'] += max(0, tests - failures - errors - skipped)

        except Exception:
            pass

        return results

    def _parse_coverage_report(self, content: str, filename: str) -> Optional[float]:
        """
        Parseia relatorio de coverage (Cobertura XML ou LCOV).

        Args:
            content: Conteudo do relatorio
            filename: Nome do arquivo para detectar formato

        Returns:
            Percentual de line coverage ou None
        """
        import xml.etree.ElementTree as ET
        import re

        try:
            # Detectar formato Cobertura XML
            if '<coverage' in content and '<?xml' in content:
                root = ET.fromstring(content)
                line_rate = root.get('line-rate')
                if line_rate:
                    return float(line_rate) * 100

                # Fallback: calcular de packages
                lines_valid = int(root.get('lines-valid', 0))
                lines_covered = int(root.get('lines-covered', 0))
                if lines_valid > 0:
                    return (lines_covered / lines_valid) * 100

            # Detectar formato LCOV
            elif content.startswith('TN:') or content.startswith('SF:') or 'end_of_record' in content:
                lines_found = 0
                lines_hit = 0

                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('LF:'):
                        try:
                            lines_found += int(line[3:])
                        except ValueError:
                            pass
                    elif line.startswith('LH:'):
                        try:
                            lines_hit += int(line[3:])
                        except ValueError:
                            pass

                if lines_found > 0:
                    return (lines_hit / lines_found) * 100

        except Exception:
            pass

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def cancel_pipeline(
        self,
        project_id: str,
        pipeline_id: str
    ) -> bool:
        """
        Cancela um pipeline em execucao.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            True se cancelado com sucesso
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}/cancel'

        try:
            response = await self.client.post(url)
            response.raise_for_status()
            self.logger.info('gitlab_pipeline_cancelled', pipeline_id=pipeline_id)
            return True

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'gitlab_cancel_pipeline_failed',
                pipeline_id=pipeline_id,
                status_code=e.response.status_code
            )
            raise GitLabCIAPIError(
                f'Failed to cancel pipeline: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def retry_pipeline(
        self,
        project_id: str,
        pipeline_id: str
    ) -> str:
        """
        Retenta um pipeline falhado.

        Args:
            project_id: ID ou path do projeto
            pipeline_id: ID do pipeline

        Returns:
            ID do novo pipeline
        """
        encoded_project = self._encode_project_id(project_id)
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/pipelines/{pipeline_id}/retry'

        try:
            response = await self.client.post(url)
            response.raise_for_status()
            data = response.json()
            new_pipeline_id = str(data.get('id'))
            self.logger.info(
                'gitlab_pipeline_retried',
                old_pipeline_id=pipeline_id,
                new_pipeline_id=new_pipeline_id
            )
            return new_pipeline_id

        except httpx.HTTPStatusError as e:
            raise GitLabCIAPIError(
                f'Failed to retry pipeline: {e.response.text}',
                status_code=e.response.status_code
            )
