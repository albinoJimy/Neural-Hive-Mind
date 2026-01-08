import asyncio
import re
import subprocess
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING

import httpx
import structlog

from ..models.artifact import ValidationResult, ValidationType, ValidationStatus

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class SonarQubeClient:
    """Cliente para SonarQube (análise estática de código)"""

    SONARQUBE_VERSION = '9.0'

    def __init__(
        self,
        url: str,
        token: str,
        enabled: bool = True,
        scanner_timeout: int = 900,
        poll_interval: int = 5,
        poll_timeout: int = 300,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        self.url = url.rstrip('/')
        self.token = token
        self.enabled = enabled
        self.scanner_timeout = scanner_timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.metrics = metrics
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _ensure_http_client(self) -> httpx.AsyncClient:
        """Garante que o cliente HTTP está inicializado"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.url,
                headers={'Authorization': f'Basic {self._encode_token()}'},
                timeout=30.0
            )
        return self._http_client

    def _encode_token(self) -> str:
        """Codifica token para autenticação Basic"""
        import base64
        return base64.b64encode(f'{self.token}:'.encode()).decode()

    def _run_scanner(self, project_key: str, source_path: str) -> Optional[str]:
        """
        Executa SonarQube Scanner CLI

        Args:
            project_key: Chave do projeto
            source_path: Caminho do código-fonte

        Returns:
            Task ID do scan ou None se falhou
        """
        cmd = [
            'sonar-scanner',
            f'-Dsonar.projectKey={project_key}',
            f'-Dsonar.sources={source_path}',
            f'-Dsonar.host.url={self.url}',
            f'-Dsonar.login={self.token}'
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.scanner_timeout,
            cwd=source_path
        )

        if 'EXECUTION SUCCESS' in result.stdout:
            match = re.search(r'ceTaskId=([a-zA-Z0-9-]+)', result.stdout)
            if match:
                return match.group(1)

        logger.warning(
            'sonarqube_scanner_output',
            stdout=result.stdout[-1000:] if result.stdout else '',
            stderr=result.stderr[-500:] if result.stderr else '',
            returncode=result.returncode
        )
        return None

    async def _wait_for_analysis(self, task_id: str) -> bool:
        """
        Aguarda conclusão da análise via polling

        Args:
            task_id: ID da task do SonarQube

        Returns:
            True se análise completou com sucesso
        """
        client = await self._ensure_http_client()
        start_time = time.monotonic()

        while (time.monotonic() - start_time) < self.poll_timeout:
            try:
                response = await client.get(f'/api/ce/task?id={task_id}')
                response.raise_for_status()
                data = response.json()

                task_status = data.get('task', {}).get('status')
                logger.debug('sonarqube_task_status', task_id=task_id, status=task_status)

                if task_status == 'SUCCESS':
                    return True
                elif task_status in ('FAILED', 'CANCELED'):
                    logger.error('sonarqube_task_failed', task_id=task_id, status=task_status)
                    return False

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error('sonarqube_poll_error', error=str(e))
                await asyncio.sleep(self.poll_interval)

        logger.error('sonarqube_poll_timeout', task_id=task_id)
        return False

    async def _fetch_issues(self, project_key: str) -> Dict[str, int]:
        """
        Busca issues do projeto via API

        Args:
            project_key: Chave do projeto

        Returns:
            Dict com contagem por severidade
        """
        client = await self._ensure_http_client()
        counts = {
            'blocker': 0,
            'critical': 0,
            'major': 0,
            'minor': 0,
            'info': 0
        }

        try:
            response = await client.get(
                '/api/issues/search',
                params={
                    'componentKeys': project_key,
                    'resolved': 'false',
                    'ps': 500
                }
            )
            response.raise_for_status()
            data = response.json()

            for issue in data.get('issues', []):
                severity = issue.get('severity', 'INFO').lower()
                if severity in counts:
                    counts[severity] += 1

        except Exception as e:
            logger.error('sonarqube_fetch_issues_error', error=str(e))

        return counts

    async def _get_quality_gate_result(self, project_key: str) -> tuple:
        """
        Obtém resultado do quality gate

        Args:
            project_key: Chave do projeto

        Returns:
            Tuple (status, score) onde status é OK/WARN/ERROR
        """
        client = await self._ensure_http_client()

        try:
            response = await client.get(
                '/api/qualitygates/project_status',
                params={'projectKey': project_key}
            )
            response.raise_for_status()
            data = response.json()

            status = data.get('projectStatus', {}).get('status', 'ERROR')

            if status == 'OK':
                return status, 0.9
            elif status == 'WARN':
                return status, 0.7
            else:
                return status, 0.4

        except Exception as e:
            logger.error('sonarqube_quality_gate_error', error=str(e))
            return 'ERROR', 0.4

    def _map_severity_counts(self, counts: Dict[str, int]) -> Dict[str, int]:
        """
        Mapeia severidades SonarQube para ValidationResult

        BLOCKER + CRITICAL → critical_issues
        MAJOR → high_issues
        MINOR → medium_issues
        INFO → low_issues
        """
        return {
            'critical': counts.get('blocker', 0) + counts.get('critical', 0),
            'high': counts.get('major', 0),
            'medium': counts.get('minor', 0),
            'low': counts.get('info', 0)
        }

    def _create_result(
        self,
        status: ValidationStatus,
        score: float,
        counts: Dict[str, int],
        duration_ms: int,
        report_uri: Optional[str] = None
    ) -> ValidationResult:
        """Helper para criar ValidationResult"""
        mapped_counts = self._map_severity_counts(counts)
        return ValidationResult(
            validation_type=ValidationType.SAST,
            tool_name='SonarQube',
            tool_version=self.SONARQUBE_VERSION,
            status=status,
            score=score,
            issues_count=sum(mapped_counts.values()),
            critical_issues=mapped_counts['critical'],
            high_issues=mapped_counts['high'],
            medium_issues=mapped_counts['medium'],
            low_issues=mapped_counts['low'],
            report_uri=report_uri,
            executed_at=datetime.now(),
            duration_ms=duration_ms
        )

    def _create_skipped_result(self) -> ValidationResult:
        """Helper para resultado de análise pulada"""
        return ValidationResult(
            validation_type=ValidationType.SAST,
            tool_name='SonarQube',
            tool_version=self.SONARQUBE_VERSION,
            status=ValidationStatus.SKIPPED,
            score=None,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=0
        )

    def _create_failed_result(self, duration_ms: int, report_uri: Optional[str] = None) -> ValidationResult:
        """Helper para resultado de análise falha"""
        return ValidationResult(
            validation_type=ValidationType.SAST,
            tool_name='SonarQube',
            tool_version=self.SONARQUBE_VERSION,
            status=ValidationStatus.FAILED,
            score=0.0,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            report_uri=report_uri,
            executed_at=datetime.now(),
            duration_ms=duration_ms
        )

    async def analyze_code(self, project_key: str, source_path: str) -> ValidationResult:
        """
        Executa análise SonarQube

        Args:
            project_key: Chave do projeto
            source_path: Caminho do código-fonte

        Returns:
            ValidationResult com resultados da análise
        """
        if not self.enabled:
            return self._create_skipped_result()

        start_time = time.monotonic()
        report_uri = f'{self.url}/dashboard?id={project_key}'
        logger.info('sonarqube_analysis_started', project_key=project_key, path=source_path)

        try:
            task_id = self._run_scanner(project_key, source_path)
            if not task_id:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                duration_seconds = duration_ms / 1000.0
                if self.metrics:
                    self.metrics.sonarqube_analysis_duration_seconds.observe(duration_seconds)
                    self.metrics.external_tool_errors_total.labels(
                        tool='sonarqube', error_type='cli_error'
                    ).inc()
                logger.error('sonarqube_scanner_failed', project_key=project_key)
                return self._create_failed_result(duration_ms, report_uri)

            logger.info('sonarqube_scanner_completed', task_id=task_id)

            analysis_success = await self._wait_for_analysis(task_id)
            if not analysis_success:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                duration_seconds = duration_ms / 1000.0
                if self.metrics:
                    self.metrics.sonarqube_analysis_duration_seconds.observe(duration_seconds)
                    self.metrics.external_tool_errors_total.labels(
                        tool='sonarqube', error_type='api_error'
                    ).inc()
                logger.error('sonarqube_analysis_failed', task_id=task_id)
                return self._create_failed_result(duration_ms, report_uri)

            counts = await self._fetch_issues(project_key)
            qg_status, score = await self._get_quality_gate_result(project_key)

            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0

            if qg_status == 'OK':
                status = ValidationStatus.PASSED
            elif qg_status == 'WARN':
                status = ValidationStatus.WARNING
            else:
                status = ValidationStatus.FAILED

            # Observar métricas de duração e sucesso
            if self.metrics:
                self.metrics.sonarqube_analysis_duration_seconds.observe(duration_seconds)

            mapped_counts = self._map_severity_counts(counts)
            logger.info(
                'sonarqube_analysis_completed',
                project_key=project_key,
                quality_gate=qg_status,
                issues=sum(mapped_counts.values()),
                critical=mapped_counts['critical'],
                high=mapped_counts['high'],
                medium=mapped_counts['medium'],
                low=mapped_counts['low'],
                duration_ms=duration_ms
            )

            return self._create_result(status, score, counts, duration_ms, report_uri)

        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.sonarqube_analysis_duration_seconds.observe(duration_seconds)
                self.metrics.external_tool_errors_total.labels(
                    tool='sonarqube', error_type='timeout'
                ).inc()
            logger.error('sonarqube_scanner_timeout', timeout=self.scanner_timeout)
            return self._create_failed_result(duration_ms, report_uri)

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.sonarqube_analysis_duration_seconds.observe(duration_seconds)
                self.metrics.external_tool_errors_total.labels(
                    tool='sonarqube', error_type='api_error'
                ).inc()
            logger.error('sonarqube_analysis_failed', error=str(e), duration_ms=duration_ms)
            return self._create_failed_result(duration_ms, report_uri)

    async def get_quality_gate_status(self, project_key: str) -> bool:
        """
        Verifica se projeto passou no quality gate

        Args:
            project_key: Chave do projeto

        Returns:
            True se passou no quality gate
        """
        status, _ = await self._get_quality_gate_result(project_key)
        return status == 'OK'

    async def get_issues(self, project_key: str, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Busca issues do projeto

        Args:
            project_key: Chave do projeto
            severity: Filtro de severidade (optional)

        Returns:
            Lista de issues
        """
        client = await self._ensure_http_client()

        try:
            params = {
                'componentKeys': project_key,
                'resolved': 'false',
                'ps': 500
            }
            if severity:
                params['severities'] = severity.upper()

            response = await client.get('/api/issues/search', params=params)
            response.raise_for_status()
            data = response.json()

            return data.get('issues', [])

        except Exception as e:
            logger.error('sonarqube_get_issues_error', error=str(e))
            return []

    async def get_metrics(self, project_key: str) -> Dict[str, Any]:
        """
        Busca métricas do projeto

        Args:
            project_key: Chave do projeto

        Returns:
            Dict com métricas do projeto
        """
        client = await self._ensure_http_client()

        try:
            response = await client.get(
                '/api/measures/component',
                params={
                    'component': project_key,
                    'metricKeys': 'bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density,ncloc'
                }
            )
            response.raise_for_status()
            data = response.json()

            metrics = {}
            for measure in data.get('component', {}).get('measures', []):
                metrics[measure.get('metric')] = measure.get('value')

            return metrics

        except Exception as e:
            logger.error('sonarqube_get_metrics_error', error=str(e))
            return {}

    async def close(self):
        """Fecha o cliente HTTP"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
