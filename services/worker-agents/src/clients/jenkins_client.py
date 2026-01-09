"""
Cliente Jenkins para execucao de jobs e obtencao de resultados de teste.

Este cliente implementa integracao com Jenkins REST API para disparar jobs,
monitorar status, buscar test reports e coverage.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


logger = structlog.get_logger()


class JenkinsAPIError(Exception):
    """Erro de chamada a API do Jenkins."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class JenkinsTimeoutError(Exception):
    """Timeout aguardando build do Jenkins."""
    pass


@dataclass
class JenkinsBuildStatus:
    """Representa status de um build Jenkins."""
    build_number: int
    status: str  # 'SUCCESS', 'FAILURE', 'UNSTABLE', 'ABORTED', 'NOT_BUILT', 'BUILDING'
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    coverage: Optional[float] = None
    duration_seconds: float = 0.0
    logs: Optional[List[str]] = field(default_factory=list)
    url: Optional[str] = None
    result: Optional[str] = None
    building: bool = False

    @property
    def success(self) -> bool:
        return self.status == 'SUCCESS'

    @property
    def completed(self) -> bool:
        return not self.building and self.status not in ('BUILDING', None)


@dataclass
class JenkinsQueueItem:
    """Representa um item na fila do Jenkins."""
    queue_id: int
    blocked: bool = False
    buildable: bool = False
    why: Optional[str] = None
    build_number: Optional[int] = None
    url: Optional[str] = None


class JenkinsClient:
    """
    Cliente REST para Jenkins API.

    Suporta:
    - Trigger de jobs com parametros
    - Polling de status de builds
    - Obtencao de test reports (JUnit)
    - Obtencao de coverage reports (Jacoco/Cobertura)
    - Retry automatico com exponential backoff
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        user: Optional[str] = None,
        timeout: int = 600,
        verify_ssl: bool = True
    ):
        """
        Inicializa cliente Jenkins.

        Args:
            base_url: URL base do Jenkins
            token: API Token do Jenkins
            user: Username para autenticacao
            timeout: Timeout padrao para operacoes em segundos
            verify_ssl: Verificar certificado SSL
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.user = user or os.getenv('JENKINS_USER', '')
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None
        self.logger = logger.bind(service='jenkins_client')

    @classmethod
    def from_env(cls, config=None) -> 'JenkinsClient':
        """
        Cria cliente a partir de variaveis de ambiente.

        Environment Variables:
            JENKINS_URL: URL do Jenkins
            JENKINS_TOKEN: API Token
            JENKINS_USER: Username

        Args:
            config: Objeto de configuracao opcional

        Returns:
            Instancia configurada do cliente

        Raises:
            ValueError: Se credenciais nao estiverem configuradas
        """
        base_url = os.getenv('JENKINS_URL') or getattr(config, 'jenkins_url', None)
        token = os.getenv('JENKINS_TOKEN') or getattr(config, 'jenkins_token', None)
        user = os.getenv('JENKINS_USER') or getattr(config, 'jenkins_user', None)

        if not base_url or not token:
            raise ValueError('Jenkins credentials not configured (JENKINS_URL, JENKINS_TOKEN)')

        timeout = getattr(config, 'jenkins_timeout_seconds', 600)
        verify_ssl = getattr(config, 'jenkins_tls_verify', True)

        return cls(base_url, token, user=user, timeout=timeout, verify_ssl=verify_ssl)

    async def start(self):
        """Inicializa cliente HTTP assincrono."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=(self.user, self.token) if self.user else None,
                timeout=httpx.Timeout(60.0, connect=10.0),
                verify=self.verify_ssl
            )
            self.logger.info('jenkins_client_started', base_url=self.base_url)

    async def close(self):
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self.logger.info('jenkins_client_closed')

    @property
    def client(self) -> httpx.AsyncClient:
        """Retorna cliente HTTP, criando se necessario."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=(self.user, self.token) if self.user else None,
                timeout=httpx.Timeout(self.timeout),
                verify=self.verify_ssl
            )
        return self._client

    def _get_crumb(self) -> Optional[Dict[str, str]]:
        """Obtem CSRF crumb se necessario (sincrono fallback)."""
        # Jenkins moderno pode exigir CSRF token
        # Por ora retornamos None; podemos implementar se necessario
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def trigger_job(
        self,
        job_name: str,
        parameters: Optional[Dict[str, str]] = None
    ) -> int:
        """
        Dispara um job no Jenkins.

        Args:
            job_name: Nome do job (pode incluir folders: folder/job)
            parameters: Parametros para o job

        Returns:
            Queue ID do build iniciado

        Raises:
            JenkinsAPIError: Erro na API
        """
        # Encode job name for URL (handle folders)
        encoded_job = job_name.replace('/', '/job/')
        if parameters:
            url = f'{self.base_url}/job/{encoded_job}/buildWithParameters'
        else:
            url = f'{self.base_url}/job/{encoded_job}/build'

        self.logger.info(
            'jenkins_trigger_job',
            job_name=job_name,
            parameters_count=len(parameters) if parameters else 0
        )

        try:
            response = await self.client.post(url, params=parameters or {})
            response.raise_for_status()

            # Obter queue ID do header Location
            location = response.headers.get('Location', '')
            queue_id = 0
            if '/queue/item/' in location:
                try:
                    queue_id = int(location.split('/queue/item/')[-1].rstrip('/'))
                except ValueError:
                    pass

            # Fallback: usar X-Queue-Id header
            if queue_id == 0:
                queue_id = int(response.headers.get('X-Queue-Id', 0))

            self.logger.info(
                'jenkins_job_triggered',
                job_name=job_name,
                queue_id=queue_id
            )

            return queue_id

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'jenkins_trigger_job_failed',
                job_name=job_name,
                status_code=e.response.status_code,
                error=e.response.text
            )
            raise JenkinsAPIError(
                f'Failed to trigger job {job_name}: {e.response.text}',
                status_code=e.response.status_code
            )
        except httpx.TimeoutException:
            raise JenkinsTimeoutError(f'Timeout triggering job {job_name}')

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_queue_item(self, queue_id: int) -> JenkinsQueueItem:
        """
        Obtem informacoes de um item na fila.

        Args:
            queue_id: ID do item na fila

        Returns:
            Informacoes do item
        """
        url = f'{self.base_url}/queue/item/{queue_id}/api/json'

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()

            build_number = None
            executable = data.get('executable')
            if executable:
                build_number = executable.get('number')

            return JenkinsQueueItem(
                queue_id=queue_id,
                blocked=data.get('blocked', False),
                buildable=data.get('buildable', False),
                why=data.get('why'),
                build_number=build_number,
                url=data.get('url')
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Item saiu da fila, build ja iniciou
                return JenkinsQueueItem(
                    queue_id=queue_id,
                    blocked=False,
                    buildable=False,
                    why=None
                )
            raise JenkinsAPIError(
                f'Failed to get queue item: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_build_status(
        self,
        job_name: str,
        build_number: int
    ) -> JenkinsBuildStatus:
        """
        Obtem status de um build.

        Args:
            job_name: Nome do job
            build_number: Numero do build

        Returns:
            Status do build

        Raises:
            JenkinsAPIError: Erro na API
        """
        encoded_job = job_name.replace('/', '/job/')
        url = f'{self.base_url}/job/{encoded_job}/{build_number}/api/json'

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()

            duration_ms = data.get('duration', 0)
            duration_seconds = duration_ms / 1000 if duration_ms else 0

            # Status pode ser None se build ainda esta em execucao
            result = data.get('result')
            status = result if result else ('BUILDING' if data.get('building') else 'UNKNOWN')

            return JenkinsBuildStatus(
                build_number=build_number,
                status=status,
                result=result,
                building=data.get('building', False),
                duration_seconds=duration_seconds,
                url=data.get('url')
            )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'jenkins_get_build_status_failed',
                job_name=job_name,
                build_number=build_number,
                status_code=e.response.status_code
            )
            raise JenkinsAPIError(
                f'Failed to get build status: {e.response.text}',
                status_code=e.response.status_code
            )

    async def wait_for_build_number(
        self,
        job_name: str,
        queue_id: int,
        poll_interval: int = 5,
        timeout: int = 300
    ) -> int:
        """
        Aguarda um item na fila se tornar um build.

        Args:
            job_name: Nome do job
            queue_id: ID do item na fila
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos

        Returns:
            Numero do build

        Raises:
            JenkinsTimeoutError: Timeout aguardando build
        """
        start_time = asyncio.get_event_loop().time()

        self.logger.info(
            'jenkins_waiting_for_build_number',
            job_name=job_name,
            queue_id=queue_id
        )

        while True:
            item = await self.get_queue_item(queue_id)

            if item.build_number:
                self.logger.info(
                    'jenkins_build_number_obtained',
                    job_name=job_name,
                    build_number=item.build_number
                )
                return item.build_number

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise JenkinsTimeoutError(
                    f'Timeout waiting for build to start (queue_id: {queue_id})'
                )

            await asyncio.sleep(poll_interval)

    async def wait_for_build(
        self,
        job_name: str,
        build_number: int,
        poll_interval: int = 15,
        timeout: Optional[int] = None
    ) -> JenkinsBuildStatus:
        """
        Aguarda build completar via polling.

        Args:
            job_name: Nome do job
            build_number: Numero do build
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos

        Returns:
            Status final do build

        Raises:
            JenkinsTimeoutError: Timeout aguardando build
        """
        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()

        self.logger.info(
            'jenkins_waiting_for_build',
            job_name=job_name,
            build_number=build_number,
            timeout=timeout
        )

        while True:
            status = await self.get_build_status(job_name, build_number)

            self.logger.debug(
                'jenkins_build_poll',
                job_name=job_name,
                build_number=build_number,
                status=status.status,
                building=status.building
            )

            if status.completed:
                # Tentar obter test results
                try:
                    test_report = await self.get_test_report(job_name, build_number)
                    status.tests_passed = test_report.get('passCount', 0)
                    status.tests_failed = test_report.get('failCount', 0)
                    status.tests_skipped = test_report.get('skipCount', 0)
                except Exception as e:
                    self.logger.warning(
                        'jenkins_test_report_fetch_failed',
                        job_name=job_name,
                        build_number=build_number,
                        error=str(e)
                    )

                # Tentar obter coverage
                try:
                    coverage = await self.get_coverage_report(job_name, build_number)
                    if coverage is not None:
                        status.coverage = coverage
                except Exception as e:
                    self.logger.warning(
                        'jenkins_coverage_fetch_failed',
                        job_name=job_name,
                        build_number=build_number,
                        error=str(e)
                    )

                self.logger.info(
                    'jenkins_build_completed',
                    job_name=job_name,
                    build_number=build_number,
                    status=status.status,
                    duration=status.duration_seconds,
                    tests_passed=status.tests_passed,
                    tests_failed=status.tests_failed
                )
                return status

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                self.logger.warning(
                    'jenkins_build_timeout',
                    job_name=job_name,
                    build_number=build_number,
                    last_status=status.status,
                    elapsed=elapsed
                )
                raise JenkinsTimeoutError(
                    f'Timeout waiting for build {job_name}#{build_number} '
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
        job_name: str,
        build_number: int
    ) -> Dict[str, Any]:
        """
        Obtem relatorio de testes de um build (JUnit).

        Args:
            job_name: Nome do job
            build_number: Numero do build

        Returns:
            Relatorio de testes
        """
        encoded_job = job_name.replace('/', '/job/')
        url = f'{self.base_url}/job/{encoded_job}/{build_number}/testReport/api/json'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Nao ha test report para este build
                return {
                    'passCount': 0,
                    'failCount': 0,
                    'skipCount': 0,
                    'totalCount': 0
                }
            raise JenkinsAPIError(
                f'Failed to get test report: {e.response.text}',
                status_code=e.response.status_code
            )

    async def get_junit_results(
        self,
        job_name: str,
        build_number: int
    ) -> Dict[str, Any]:
        """
        Alias para get_test_report (compatibilidade).

        Args:
            job_name: Nome do job
            build_number: Numero do build

        Returns:
            Resultados JUnit
        """
        return await self.get_test_report(job_name, build_number)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_coverage_report(
        self,
        job_name: str,
        build_number: int
    ) -> Optional[float]:
        """
        Obtem coverage de um build (Jacoco ou Cobertura).

        Args:
            job_name: Nome do job
            build_number: Numero do build

        Returns:
            Percentual de line coverage ou None
        """
        encoded_job = job_name.replace('/', '/job/')

        # Tentar Jacoco primeiro
        jacoco_url = f'{self.base_url}/job/{encoded_job}/{build_number}/jacoco/api/json'
        try:
            response = await self.client.get(jacoco_url)
            if response.status_code == 200:
                data = response.json()
                line_coverage = data.get('lineCoverage', {})
                if isinstance(line_coverage, dict):
                    percentage = line_coverage.get('percentageFloat', line_coverage.get('percentage'))
                    if percentage is not None:
                        return float(percentage)
                elif isinstance(line_coverage, (int, float)):
                    return float(line_coverage)
        except Exception:
            pass

        # Tentar Cobertura
        cobertura_url = f'{self.base_url}/job/{encoded_job}/{build_number}/cobertura/api/json'
        try:
            response = await self.client.get(cobertura_url)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', {})
                elements = results.get('elements', [])
                for elem in elements:
                    if elem.get('name') == 'Lines':
                        ratio = elem.get('ratio')
                        if ratio is not None:
                            return float(ratio)
        except Exception:
            pass

        # Tentar Code Coverage API plugin
        coverage_url = f'{self.base_url}/job/{encoded_job}/{build_number}/coverage/result/api/json'
        try:
            response = await self.client.get(coverage_url)
            if response.status_code == 200:
                data = response.json()
                line_coverage = data.get('lineCoverage')
                if line_coverage is not None:
                    return float(line_coverage)
        except Exception:
            pass

        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_console_output(
        self,
        job_name: str,
        build_number: int
    ) -> str:
        """
        Obtem log de console de um build.

        Args:
            job_name: Nome do job
            build_number: Numero do build

        Returns:
            Log do console em texto
        """
        encoded_job = job_name.replace('/', '/job/')
        url = f'{self.base_url}/job/{encoded_job}/{build_number}/consoleText'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text

        except httpx.HTTPStatusError as e:
            self.logger.warning(
                'jenkins_get_console_failed',
                job_name=job_name,
                build_number=build_number,
                status_code=e.response.status_code
            )
            return ''

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def stop_build(
        self,
        job_name: str,
        build_number: int
    ) -> bool:
        """
        Para um build em execucao.

        Args:
            job_name: Nome do job
            build_number: Numero do build

        Returns:
            True se parado com sucesso
        """
        encoded_job = job_name.replace('/', '/job/')
        url = f'{self.base_url}/job/{encoded_job}/{build_number}/stop'

        try:
            response = await self.client.post(url)
            response.raise_for_status()
            self.logger.info(
                'jenkins_build_stopped',
                job_name=job_name,
                build_number=build_number
            )
            return True

        except httpx.HTTPStatusError as e:
            self.logger.error(
                'jenkins_stop_build_failed',
                job_name=job_name,
                build_number=build_number,
                status_code=e.response.status_code
            )
            raise JenkinsAPIError(
                f'Failed to stop build: {e.response.text}',
                status_code=e.response.status_code
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException))
    )
    async def get_last_build(self, job_name: str) -> Optional[JenkinsBuildStatus]:
        """
        Obtem informacoes do ultimo build de um job.

        Args:
            job_name: Nome do job

        Returns:
            Status do ultimo build ou None
        """
        encoded_job = job_name.replace('/', '/job/')
        url = f'{self.base_url}/job/{encoded_job}/lastBuild/api/json'

        try:
            response = await self.client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()

            data = response.json()
            build_number = data.get('number')

            if build_number:
                return await self.get_build_status(job_name, build_number)
            return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise JenkinsAPIError(
                f'Failed to get last build: {e.response.text}',
                status_code=e.response.status_code
            )

    async def get_job_info(self, job_name: str) -> Dict[str, Any]:
        """
        Obtem informacoes de um job.

        Args:
            job_name: Nome do job

        Returns:
            Informacoes do job
        """
        encoded_job = job_name.replace('/', '/job/')
        url = f'{self.base_url}/job/{encoded_job}/api/json'

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise JenkinsAPIError(
                f'Failed to get job info: {e.response.text}',
                status_code=e.response.status_code
            )

    def parse_test_report(self, test_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converte relatorio de teste Jenkins para formato padronizado.

        Args:
            test_report: Relatorio bruto do Jenkins

        Returns:
            Relatorio padronizado
        """
        return {
            'total': test_report.get('totalCount', 0),
            'passed': test_report.get('passCount', 0),
            'failed': test_report.get('failCount', 0),
            'skipped': test_report.get('skipCount', 0),
            'duration': test_report.get('duration', 0),
            'suites': test_report.get('suites', [])
        }
