import json
import subprocess
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import structlog

from ..models.artifact import ValidationResult, ValidationType, ValidationStatus

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class TrivyClient:
    """Cliente para Trivy (scanner de vulnerabilidades em containers e IaC)"""

    TRIVY_VERSION = '0.45.0'

    def __init__(
        self,
        enabled: bool = True,
        severity: str = 'CRITICAL,HIGH',
        timeout: int = 600,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        self.enabled = enabled
        self.severity = severity
        self.timeout = timeout
        self.metrics = metrics

    def _run_trivy_cli(self, scan_type: str, target: str) -> dict:
        """
        Executa Trivy CLI via subprocess

        Args:
            scan_type: Tipo de scan (image, fs, config)
            target: Alvo do scan (imagem, path, etc.)

        Returns:
            Dict com resultado do scan
        """
        cmd = [
            'trivy', scan_type,
            '--format', 'json',
            '--severity', self.severity,
            target
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout
        )

        if result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning('trivy_json_parse_failed', stdout=result.stdout[:500])
                return {'error': 'JSON parse failed', 'stdout': result.stdout}

        if result.returncode != 0:
            return {'error': result.stderr or 'Unknown error', 'returncode': result.returncode}

        return {'Results': []}

    def _parse_vulnerabilities(self, trivy_output: dict) -> dict:
        """
        Parseia output do Trivy para contagem por severidade

        Args:
            trivy_output: Output JSON do Trivy

        Returns:
            Dict com contagem por severidade
        """
        counts = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }

        results = trivy_output.get('Results', [])
        for result in results:
            vulnerabilities = result.get('Vulnerabilities', [])
            if vulnerabilities is None:
                continue

            for vuln in vulnerabilities:
                severity = vuln.get('Severity', 'LOW').upper()
                if severity == 'CRITICAL':
                    counts['critical'] += 1
                elif severity == 'HIGH':
                    counts['high'] += 1
                elif severity == 'MEDIUM':
                    counts['medium'] += 1
                elif severity == 'LOW':
                    counts['low'] += 1

            misconfigurations = result.get('Misconfigurations', [])
            if misconfigurations is None:
                continue

            for misconfig in misconfigurations:
                severity = misconfig.get('Severity', 'LOW').upper()
                if severity == 'CRITICAL':
                    counts['critical'] += 1
                elif severity == 'HIGH':
                    counts['high'] += 1
                elif severity == 'MEDIUM':
                    counts['medium'] += 1
                elif severity == 'LOW':
                    counts['low'] += 1

        return counts

    def _create_result(
        self,
        status: ValidationStatus,
        score: float,
        counts: dict,
        duration_ms: int
    ) -> ValidationResult:
        """Helper para criar ValidationResult"""
        return ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Trivy',
            tool_version=self.TRIVY_VERSION,
            status=status,
            score=score,
            issues_count=sum(counts.values()),
            critical_issues=counts['critical'],
            high_issues=counts['high'],
            medium_issues=counts['medium'],
            low_issues=counts['low'],
            executed_at=datetime.now(),
            duration_ms=duration_ms
        )

    def _create_skipped_result(self) -> ValidationResult:
        """Helper para resultado de scan pulado"""
        return ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Trivy',
            tool_version=self.TRIVY_VERSION,
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

    def _create_failed_result(self, duration_ms: int) -> ValidationResult:
        """Helper para resultado de scan falho"""
        return ValidationResult(
            validation_type=ValidationType.SECURITY_SCAN,
            tool_name='Trivy',
            tool_version=self.TRIVY_VERSION,
            status=ValidationStatus.FAILED,
            score=0.0,
            issues_count=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            executed_at=datetime.now(),
            duration_ms=duration_ms
        )

    def _determine_status_and_score(self, counts: dict) -> tuple:
        """Determina status e score baseado nas contagens"""
        if counts['critical'] > 0:
            return ValidationStatus.FAILED, 0.3
        elif counts['high'] > 0:
            return ValidationStatus.WARNING, 0.6
        elif counts['medium'] > 0:
            return ValidationStatus.WARNING, 0.8
        elif counts['low'] > 0:
            return ValidationStatus.PASSED, 0.9
        else:
            return ValidationStatus.PASSED, 1.0

    async def _execute_scan(self, scan_type: str, target: str, context_info: str) -> ValidationResult:
        """
        Executa scan genérico do Trivy

        Args:
            scan_type: Tipo de scan (image, fs, config)
            target: Alvo do scan
            context_info: Informação de contexto para logs

        Returns:
            ValidationResult com vulnerabilidades encontradas
        """
        if not self.enabled:
            return self._create_skipped_result()

        start_time = time.monotonic()
        logger.info(f'trivy_{scan_type}_scan_started', target=context_info)

        try:
            trivy_output = self._run_trivy_cli(scan_type, target)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0

            if 'error' in trivy_output and 'Results' not in trivy_output:
                if self.metrics:
                    self.metrics.trivy_scan_duration_seconds.labels(
                        scan_type=scan_type
                    ).observe(duration_seconds)
                    self.metrics.external_tool_errors_total.labels(
                        tool='trivy', error_type='cli_error'
                    ).inc()
                logger.error(
                    f'trivy_{scan_type}_scan_failed',
                    error=trivy_output.get('error'),
                    duration_ms=duration_ms
                )
                return self._create_failed_result(duration_ms)

            counts = self._parse_vulnerabilities(trivy_output)
            status, score = self._determine_status_and_score(counts)

            # Observar métricas de duração e sucesso
            if self.metrics:
                self.metrics.trivy_scan_duration_seconds.labels(
                    scan_type=scan_type
                ).observe(duration_seconds)

            logger.info(
                f'trivy_{scan_type}_scan_completed',
                target=context_info,
                issues=sum(counts.values()),
                critical=counts['critical'],
                high=counts['high'],
                medium=counts['medium'],
                low=counts['low'],
                duration_ms=duration_ms
            )

            return self._create_result(status, score, counts, duration_ms)

        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.trivy_scan_duration_seconds.labels(
                    scan_type=scan_type
                ).observe(duration_seconds)
                self.metrics.external_tool_errors_total.labels(
                    tool='trivy', error_type='timeout'
                ).inc()
            logger.error(f'trivy_{scan_type}_scan_timeout', timeout=self.timeout, duration_ms=duration_ms)
            return self._create_failed_result(duration_ms)

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.trivy_scan_duration_seconds.labels(
                    scan_type=scan_type
                ).observe(duration_seconds)
                self.metrics.external_tool_errors_total.labels(
                    tool='trivy', error_type='cli_error'
                ).inc()
            logger.error(f'trivy_{scan_type}_scan_failed', error=str(e), duration_ms=duration_ms)
            return self._create_failed_result(duration_ms)

    async def scan_container_image(self, image_uri: str) -> ValidationResult:
        """
        Escaneia imagem Docker

        Args:
            image_uri: URI da imagem

        Returns:
            ValidationResult com vulnerabilidades
        """
        return await self._execute_scan('image', image_uri, image_uri)

    async def scan_iac(self, iac_path: str) -> ValidationResult:
        """
        Escaneia Terraform/Helm/Kubernetes configs

        Args:
            iac_path: Caminho dos arquivos IaC

        Returns:
            ValidationResult com misconfigurations
        """
        return await self._execute_scan('config', iac_path, iac_path)

    async def scan_filesystem(self, path: str) -> ValidationResult:
        """
        Escaneia filesystem para vulnerabilidades

        Args:
            path: Caminho do filesystem

        Returns:
            ValidationResult com vulnerabilidades
        """
        return await self._execute_scan('fs', path, path)
