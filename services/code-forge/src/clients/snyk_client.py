import json
import os
import subprocess
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import structlog

from ..models.artifact import ValidationResult, ValidationType, ValidationStatus

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class SnykClient:
    """Cliente para Snyk (análise de vulnerabilidades em dependências)"""

    def __init__(
        self,
        token: str,
        enabled: bool = True,
        timeout: int = 300,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        self.token = token
        self.enabled = enabled
        self.timeout = timeout
        self.metrics = metrics

    def _run_snyk_cli(self, project_path: str, language: str) -> dict:
        """
        Executa Snyk CLI via subprocess

        Args:
            project_path: Caminho do projeto
            language: Linguagem do projeto

        Returns:
            Dict com resultado do scan
        """
        env = os.environ.copy()
        env['SNYK_TOKEN'] = self.token

        cmd = [
            'snyk', 'test',
            '--json',
            '--severity-threshold=low',
            project_path
        ]

        if language == 'python':
            cmd.extend(['--file=requirements.txt'])
        elif language == 'javascript':
            cmd.extend(['--file=package.json'])
        elif language == 'go':
            cmd.extend(['--file=go.mod'])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            env=env,
            cwd=project_path
        )

        if result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning('snyk_json_parse_failed', stdout=result.stdout[:500])
                return {'error': 'JSON parse failed', 'stdout': result.stdout}

        return {'error': result.stderr or 'No output', 'returncode': result.returncode}

    def _parse_vulnerabilities(self, snyk_output: dict) -> dict:
        """
        Parseia output do Snyk para contagem por severidade

        Args:
            snyk_output: Output JSON do Snyk

        Returns:
            Dict com contagem por severidade
        """
        counts = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }

        vulnerabilities = snyk_output.get('vulnerabilities', [])
        for vuln in vulnerabilities:
            severity = vuln.get('severity', 'low').lower()
            if severity in counts:
                counts[severity] += 1

        return counts

    async def scan_dependencies(self, project_path: str, language: str) -> ValidationResult:
        """
        Escaneia dependências para vulnerabilidades

        Args:
            project_path: Caminho do projeto
            language: Linguagem (python, javascript, etc.)

        Returns:
            ValidationResult com vulnerabilidades encontradas
        """
        if not self.enabled:
            return ValidationResult(
                validation_type=ValidationType.SECURITY_SCAN,
                tool_name='Snyk',
                tool_version='latest',
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

        start_time = time.monotonic()
        logger.info('snyk_scan_started', language=language, path=project_path)

        try:
            snyk_output = self._run_snyk_cli(project_path, language)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            if 'error' in snyk_output and 'vulnerabilities' not in snyk_output:
                logger.error(
                    'snyk_scan_failed',
                    error=snyk_output.get('error'),
                    duration_ms=duration_ms
                )
                return ValidationResult(
                    validation_type=ValidationType.SECURITY_SCAN,
                    tool_name='Snyk',
                    tool_version='latest',
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

            counts = self._parse_vulnerabilities(snyk_output)
            total_issues = sum(counts.values())

            if counts['critical'] > 0:
                status = ValidationStatus.FAILED
                score = 0.3
            elif counts['high'] > 0:
                status = ValidationStatus.WARNING
                score = 0.6
            elif counts['medium'] > 0:
                status = ValidationStatus.WARNING
                score = 0.8
            elif counts['low'] > 0:
                status = ValidationStatus.PASSED
                score = 0.9
            else:
                status = ValidationStatus.PASSED
                score = 1.0

            # Observar métricas de duração e sucesso
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.snyk_scan_duration_seconds.observe(duration_seconds)

            logger.info(
                'snyk_scan_completed',
                issues=total_issues,
                critical=counts['critical'],
                high=counts['high'],
                medium=counts['medium'],
                low=counts['low'],
                duration_ms=duration_ms
            )

            return ValidationResult(
                validation_type=ValidationType.SECURITY_SCAN,
                tool_name='Snyk',
                tool_version='latest',
                status=status,
                score=score,
                issues_count=total_issues,
                critical_issues=counts['critical'],
                high_issues=counts['high'],
                medium_issues=counts['medium'],
                low_issues=counts['low'],
                executed_at=datetime.now(),
                duration_ms=duration_ms
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.snyk_scan_duration_seconds.observe(duration_seconds)
                self.metrics.external_tool_errors_total.labels(
                    tool='snyk', error_type='timeout'
                ).inc()
            logger.error('snyk_scan_timeout', timeout=self.timeout, duration_ms=duration_ms)
            return ValidationResult(
                validation_type=ValidationType.SECURITY_SCAN,
                tool_name='Snyk',
                tool_version='latest',
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

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            if self.metrics:
                self.metrics.snyk_scan_duration_seconds.observe(duration_seconds)
                self.metrics.external_tool_errors_total.labels(
                    tool='snyk', error_type='cli_error'
                ).inc()
            logger.error('snyk_scan_failed', error=str(e), duration_ms=duration_ms)
            return ValidationResult(
                validation_type=ValidationType.SECURITY_SCAN,
                tool_name='Snyk',
                tool_version='latest',
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
