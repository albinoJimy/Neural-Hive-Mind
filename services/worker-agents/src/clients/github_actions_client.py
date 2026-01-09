"""
Cliente GitHub Actions para execucao de workflows e obtencao de resultados de teste.

Este cliente implementa integracao com GitHub Actions REST API para disparar workflows,
monitorar status, baixar artifacts e coletar resultados de testes/coverage.
"""

import asyncio
import os
import zipfile
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


logger = structlog.get_logger()


class GitHubActionsAPIError(Exception):
    """Erro de chamada a API do GitHub Actions."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubActionsTimeoutError(Exception):
    """Timeout aguardando workflow do GitHub Actions."""
    pass


@dataclass
class WorkflowRunStatus:
    """Representa status resumido de um workflow GitHub Actions."""
    run_id: str
    status: str  # 'queued', 'in_progress', 'completed'
    conclusion: Optional[str]  # 'success', 'failure', 'cancelled', 'skipped', 'timed_out'
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    coverage: Optional[float] = None
    duration_seconds: Optional[float] = None
    logs: Optional[List[str]] = field(default_factory=list)
    html_url: Optional[str] = None
    workflow_id: Optional[str] = None
    head_branch: Optional[str] = None
    head_sha: Optional[str] = None
    artifacts: Optional[List[Dict[str, Any]]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.conclusion == 'success'

    @property
    def completed(self) -> bool:
        return self.status == 'completed'


@dataclass
class ArtifactInfo:
    """Informacoes de um artifact."""
    id: int
    name: str
    size_in_bytes: int
    archive_download_url: str
    expired: bool
    created_at: str
    expires_at: Optional[str] = None


class GitHubActionsClient:
    """
    Cliente REST para GitHub Actions API.

    Suporta:
    - Trigger de workflows via workflow_dispatch
    - Polling de status com timeout
    - Download de artifacts
    - Parsing de test results (JUnit XML)
    - Obtencao de coverage reports
    - Retry automatico com exponential backoff
    """

    def __init__(
        self,
        token: str,
        base_url: str = 'https://api.github.com',
        timeout: int = 900,
        default_repo: Optional[str] = None
    ):
        """
        Inicializa cliente GitHub Actions.

        Args:
            token: GitHub Personal Access Token ou GitHub App Token
            base_url: URL base da API (padrao: api.github.com)
            timeout: Timeout padrao para operacoes em segundos
            default_repo: Repositorio padrao (formato: owner/repo)
        """
        self.token = token
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.default_repo = default_repo
        self._client: Optional[httpx.AsyncClient] = None
        self.logger = logger.bind(service='github_actions_client')

    @classmethod
    def from_env(cls, config=None) -> 'GitHubActionsClient':
        """
        Cria cliente a partir de variaveis de ambiente.

        Environment Variables:
            GITHUB_TOKEN: Personal Access Token ou App Token
            GITHUB_API_URL: URL da API (padrao: https://api.github.com)

        Args:
            config: Objeto de configuracao opcional

        Returns:
            Instancia configurada do cliente

        Raises:
            ValueError: Se token nao estiver configurado
        """
        token = os.getenv('GITHUB_TOKEN') or getattr(config, 'github_token', None)
        if not token:
            raise ValueError('GitHub token not configured (GITHUB_TOKEN or config.github_token)')

        base_url = getattr(config, 'github_api_url', 'https://api.github.com')
        timeout = getattr(config, 'github_actions_timeout_seconds', 900)

        return cls(token, base_url=base_url, timeout=timeout)

    async def start(self):
        """Inicializa cliente HTTP assincrono."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28'
                },
                timeout=httpx.Timeout(60.0, connect=10.0)
            )
            self.logger.info('github_actions_client_started', base_url=self.base_url)

    async def close(self):
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self.logger.info('github_actions_client_closed')

    @property
    def client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP, criando se necessario (modo sincrono fallback)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28'
                },
                timeout=httpx.Timeout(self.timeout)
            )
        return self._client

    def _parse_repo(self, repo: str) -> tuple:
        """Separa owner/repo em tupla."""
        if '/' not in repo:
            raise ValueError(f'Invalid repo format: {repo}. Expected owner/repo')
        parts = repo.split('/')
        return parts[0], parts[1]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def trigger_workflow(
        self,
        repo: str,
        workflow_id: str,
        ref: str = 'main',
        inputs: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Dispara um workflow via workflow_dispatch event.

        Args:
            repo: Repositorio no formato owner/repo
            workflow_id: Nome do arquivo workflow ou ID numerico
            ref: Branch/tag para executar
            inputs: Inputs para o workflow

        Returns:
            ID do workflow run (ou ID temporario se dispatch for async)

        Raises:
            GitHubActionsAPIError: Erro na API
            ValueError: Parametros invalidos
        """
        if not repo or not workflow_id:
            raise ValueError('repo and workflow_id are required')

        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/workflows/{workflow_id}/dispatches'

        payload = {'ref': ref}
        if inputs:
            payload['inputs'] = inputs

        self.logger.info(
            'github_actions_trigger_workflow',
            repo=repo,
            workflow_id=workflow_id,
            ref=ref,
            inputs_count=len(inputs) if inputs else 0
        )

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()

            # workflow_dispatch retorna 204 No Content
            # Precisamos buscar o run_id mais recente
            run_id = await self._get_latest_run_id(repo, workflow_id, ref)

            self.logger.info(
                'github_actions_workflow_triggered',
                repo=repo,
                workflow_id=workflow_id,
                run_id=run_id
            )

            return run_id

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'github_actions_trigger_failed',
                repo=repo,
                workflow_id=workflow_id,
                status_code=e.response.status_code,
                error=e.response.text
            )
            raise GitHubActionsAPIError(
                f'Failed to trigger workflow: {e.response.text}',
                status_code=e.response.status_code
            )
        except httpx.TimeoutException:
            raise GitHubActionsTimeoutError(f'Timeout triggering workflow for {repo}')

    async def _get_latest_run_id(
        self,
        repo: str,
        workflow_id: str,
        branch: str
    ) -> str:
        """Busca ID do run mais recente de um workflow."""
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/workflows/{workflow_id}/runs'

        # Aguardar um pouco para o run ser criado
        await asyncio.sleep(2)

        params = {
            'branch': branch,
            'per_page': 1,
            'status': 'queued,in_progress'
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            runs = data.get('workflow_runs', [])

            if runs:
                return str(runs[0]['id'])

            # Se nao encontrar em queued/in_progress, buscar o mais recente
            params['status'] = None
            response = await self.client.get(url, params={'branch': branch, 'per_page': 1})
            response.raise_for_status()

            data = response.json()
            runs = data.get('workflow_runs', [])

            if runs:
                return str(runs[0]['id'])

            # Fallback: gerar ID temporario (sera substituido pelo real no polling)
            import uuid
            return f'pending-{uuid.uuid4().hex[:8]}'

        except Exception as e:
            self.logger.warning(
                'github_actions_get_latest_run_failed',
                error=str(e)
            )
            import uuid
            return f'pending-{uuid.uuid4().hex[:8]}'

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_workflow_run(
        self,
        repo: str,
        run_id: str
    ) -> WorkflowRunStatus:
        """
        Obtem status de um workflow run.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            Status do workflow run

        Raises:
            GitHubActionsAPIError: Erro na API
        """
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/runs/{run_id}'

        try:
            response = await self.client.get(url)

            if response.status_code == 404:
                # Workflow ainda nao foi criado ou ID invalido
                return WorkflowRunStatus(
                    run_id=run_id,
                    status='queued',
                    conclusion=None,
                    logs=['Workflow run not found yet, may still be initializing']
                )

            response.raise_for_status()
            data = response.json()

            # Calcular duracao se completou
            duration_seconds = None
            if data.get('run_started_at') and data.get('updated_at'):
                from datetime import datetime
                try:
                    started = datetime.fromisoformat(data['run_started_at'].replace('Z', '+00:00'))
                    updated = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
                    duration_seconds = (updated - started).total_seconds()
                except Exception:
                    pass

            return WorkflowRunStatus(
                run_id=str(data.get('id')),
                status=data.get('status', 'unknown'),
                conclusion=data.get('conclusion'),
                duration_seconds=duration_seconds,
                html_url=data.get('html_url'),
                workflow_id=str(data.get('workflow_id')),
                head_branch=data.get('head_branch'),
                head_sha=data.get('head_sha')
            )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'github_actions_get_run_failed',
                repo=repo,
                run_id=run_id,
                status_code=e.response.status_code
            )
            raise GitHubActionsAPIError(
                f'Failed to get workflow run: {e.response.text}',
                status_code=e.response.status_code
            )

    async def wait_for_run(
        self,
        run_id: str,
        poll_interval: int = 15,
        timeout: Optional[int] = None,
        repo: Optional[str] = None
    ) -> WorkflowRunStatus:
        """
        Aguarda workflow run completar via polling.

        Args:
            run_id: ID do workflow run
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos
            repo: Repositorio (usa default_repo se nao especificado)

        Returns:
            Status final do workflow

        Raises:
            GitHubActionsTimeoutError: Timeout aguardando workflow
            ValueError: Se repo nao especificado e default_repo nao configurado
        """
        repo = repo or self.default_repo
        if not repo:
            raise ValueError('repo is required (either as parameter or default_repo)')

        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()

        self.logger.info(
            'github_actions_waiting_for_run',
            repo=repo,
            run_id=run_id,
            timeout=timeout
        )

        while True:
            status = await self.get_workflow_run(repo, run_id)

            self.logger.debug(
                'github_actions_poll',
                run_id=run_id,
                status=status.status,
                conclusion=status.conclusion
            )

            if status.completed:
                # Tentar obter test results e coverage
                try:
                    test_results = await self.get_test_results(repo, run_id)
                    status.passed = test_results.get('passed', 0)
                    status.failed = test_results.get('failed', 0)
                    status.skipped = test_results.get('skipped', 0)
                    status.errors = test_results.get('errors', 0)
                    status.coverage = test_results.get('coverage')
                except Exception as e:
                    self.logger.warning(
                        'github_actions_test_results_fetch_failed',
                        run_id=run_id,
                        error=str(e)
                    )

                # Obter artifacts
                try:
                    artifacts = await self.list_artifacts(repo, run_id)
                    status.artifacts = artifacts
                except Exception as e:
                    self.logger.warning(
                        'github_actions_artifacts_fetch_failed',
                        run_id=run_id,
                        error=str(e)
                    )

                self.logger.info(
                    'github_actions_run_completed',
                    run_id=run_id,
                    conclusion=status.conclusion,
                    duration=status.duration_seconds,
                    passed=status.passed,
                    failed=status.failed
                )
                return status

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                self.logger.warning(
                    'github_actions_run_timeout',
                    run_id=run_id,
                    last_status=status.status,
                    elapsed=elapsed
                )
                raise GitHubActionsTimeoutError(
                    f'Timeout waiting for workflow run {run_id} '
                    f'(last status: {status.status}, elapsed: {elapsed:.1f}s)'
                )

            await asyncio.sleep(poll_interval)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def list_artifacts(
        self,
        repo: str,
        run_id: str
    ) -> List[Dict[str, Any]]:
        """
        Lista artifacts de um workflow run.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            Lista de artifacts
        """
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/runs/{run_id}/artifacts'

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()
            return data.get('artifacts', [])

        except httpx.HTTPStatusError as e:
            self.logger.warning(
                'github_actions_list_artifacts_failed',
                run_id=run_id,
                status_code=e.response.status_code
            )
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def download_artifact(
        self,
        repo: str,
        artifact_id: int
    ) -> bytes:
        """
        Baixa um artifact.

        Args:
            repo: Repositorio no formato owner/repo
            artifact_id: ID do artifact

        Returns:
            Conteudo binario do artifact (ZIP)

        Raises:
            GitHubActionsAPIError: Erro na API
        """
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/artifacts/{artifact_id}/zip'

        try:
            response = await self.client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.content

        except httpx.HTTPStatusError as e:
            raise GitHubActionsAPIError(
                f'Failed to download artifact: {e.response.text}',
                status_code=e.response.status_code
            )

    async def get_test_results(
        self,
        repo: str,
        run_id: str
    ) -> Dict[str, Any]:
        """
        Obtem resultados de testes de um workflow run.

        Busca artifacts com nomes comuns de test reports (junit, test-results, etc)
        e faz parsing do conteudo.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            Dicionario com resultados agregados
        """
        from ..utils.test_report_parser import JUnitXMLParser, CoberturaXMLParser

        artifacts = await self.list_artifacts(repo, run_id)

        results = {
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'errors': 0,
            'total': 0,
            'coverage': None,
            'test_cases': []
        }

        test_artifact_names = [
            'test-results', 'junit', 'test-report', 'pytest',
            'test_results', 'junit_results', 'test_report'
        ]
        coverage_artifact_names = [
            'coverage', 'coverage-report', 'code-coverage',
            'coverage_report', 'codecov'
        ]

        for artifact in artifacts:
            name = artifact.get('name', '').lower()
            artifact_id = artifact.get('id')

            # Check for test results
            if any(tn in name for tn in test_artifact_names):
                try:
                    zip_content = await self.download_artifact(repo, artifact_id)
                    test_results = self._parse_artifact_tests(zip_content)
                    results['passed'] += test_results.get('passed', 0)
                    results['failed'] += test_results.get('failed', 0)
                    results['skipped'] += test_results.get('skipped', 0)
                    results['errors'] += test_results.get('errors', 0)
                    results['total'] += test_results.get('total', 0)
                except Exception as e:
                    self.logger.warning(
                        'github_actions_parse_test_artifact_failed',
                        artifact=name,
                        error=str(e)
                    )

            # Check for coverage
            if any(cn in name for cn in coverage_artifact_names) and results['coverage'] is None:
                try:
                    zip_content = await self.download_artifact(repo, artifact_id)
                    coverage = self._parse_artifact_coverage(zip_content)
                    if coverage is not None:
                        results['coverage'] = coverage
                except Exception as e:
                    self.logger.warning(
                        'github_actions_parse_coverage_artifact_failed',
                        artifact=name,
                        error=str(e)
                    )

        return results

    def _parse_artifact_tests(self, zip_content: bytes) -> Dict[str, Any]:
        """Parseia test results de um artifact ZIP."""
        from ..utils.test_report_parser import JUnitXMLParser

        results = {
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'errors': 0,
            'total': 0
        }

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                for filename in zf.namelist():
                    if filename.endswith('.xml'):
                        try:
                            content = zf.read(filename).decode('utf-8', errors='replace')
                            if '<testsuite' in content or '<testsuites' in content:
                                parser = JUnitXMLParser()
                                parsed = parser.parse(content)
                                results['passed'] += parsed.passed
                                results['failed'] += parsed.failed
                                results['skipped'] += parsed.skipped
                                results['errors'] += parsed.errors
                                results['total'] += parsed.total
                        except Exception:
                            pass
        except Exception as e:
            self.logger.warning('github_actions_parse_zip_failed', error=str(e))

        return results

    def _parse_artifact_coverage(self, zip_content: bytes) -> Optional[float]:
        """Parseia coverage de um artifact ZIP."""
        from ..utils.test_report_parser import CoberturaXMLParser, LCOVParser

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                for filename in zf.namelist():
                    content = zf.read(filename).decode('utf-8', errors='replace')

                    # Try Cobertura XML
                    if filename.endswith('.xml') and '<coverage' in content:
                        try:
                            parser = CoberturaXMLParser()
                            parsed = parser.parse(content)
                            return parsed.line_coverage
                        except Exception:
                            pass

                    # Try LCOV
                    if filename.endswith('.info') or 'lcov' in filename.lower():
                        try:
                            parser = LCOVParser()
                            parsed = parser.parse(content)
                            return parsed.line_coverage
                        except Exception:
                            pass
        except Exception as e:
            self.logger.warning('github_actions_parse_coverage_zip_failed', error=str(e))

        return None

    async def get_coverage_report(
        self,
        repo: str,
        run_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtem relatorio de coverage de um workflow run.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            Dicionario com dados de coverage ou None
        """
        artifacts = await self.list_artifacts(repo, run_id)

        coverage_artifact_names = [
            'coverage', 'coverage-report', 'code-coverage',
            'coverage_report', 'codecov'
        ]

        for artifact in artifacts:
            name = artifact.get('name', '').lower()
            artifact_id = artifact.get('id')

            if any(cn in name for cn in coverage_artifact_names):
                try:
                    zip_content = await self.download_artifact(repo, artifact_id)
                    coverage = self._parse_artifact_coverage(zip_content)
                    if coverage is not None:
                        return {
                            'line_coverage': coverage,
                            'artifact_name': artifact.get('name'),
                            'artifact_id': artifact_id
                        }
                except Exception as e:
                    self.logger.warning(
                        'github_actions_get_coverage_failed',
                        artifact=name,
                        error=str(e)
                    )

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def cancel_workflow_run(
        self,
        repo: str,
        run_id: str
    ) -> bool:
        """
        Cancela um workflow run em execucao.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            True se cancelado com sucesso
        """
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/runs/{run_id}/cancel'

        try:
            response = await self.client.post(url)
            response.raise_for_status()
            self.logger.info('github_actions_run_cancelled', run_id=run_id)
            return True

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'github_actions_cancel_failed',
                run_id=run_id,
                status_code=e.response.status_code
            )
            raise GitHubActionsAPIError(
                f'Failed to cancel workflow run: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def rerun_workflow(
        self,
        repo: str,
        run_id: str
    ) -> str:
        """
        Re-executa um workflow run.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            ID do novo workflow run
        """
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/runs/{run_id}/rerun'

        try:
            response = await self.client.post(url)
            response.raise_for_status()

            # Buscar novo run_id
            await asyncio.sleep(2)
            status = await self.get_workflow_run(repo, run_id)
            new_run_id = status.run_id

            self.logger.info(
                'github_actions_run_rerun',
                old_run_id=run_id,
                new_run_id=new_run_id
            )
            return new_run_id

        except httpx.HTTPStatusError as e:
            raise GitHubActionsAPIError(
                f'Failed to rerun workflow: {e.response.text}',
                status_code=e.response.status_code
            )

    async def get_workflow_run_logs(
        self,
        repo: str,
        run_id: str
    ) -> Optional[bytes]:
        """
        Baixa logs de um workflow run.

        Args:
            repo: Repositorio no formato owner/repo
            run_id: ID do workflow run

        Returns:
            Conteudo binario dos logs (ZIP) ou None
        """
        owner, repo_name = self._parse_repo(repo)
        url = f'{self.base_url}/repos/{owner}/{repo_name}/actions/runs/{run_id}/logs'

        try:
            response = await self.client.get(url, follow_redirects=True)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.content

        except httpx.HTTPStatusError as e:
            self.logger.warning(
                'github_actions_get_logs_failed',
                run_id=run_id,
                status_code=e.response.status_code
            )
            return None
