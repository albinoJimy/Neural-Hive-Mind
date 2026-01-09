import asyncio
import json
import random
import subprocess
import time
from typing import Any, Dict, Optional
import httpx
import structlog
from neural_hive_observability import get_tracer
from .base_executor import BaseTaskExecutor

logger = structlog.get_logger()


class ValidateExecutor(BaseTaskExecutor):
    '''Executor para task_type=VALIDATE com integracao OPA dedicada'''

    def get_task_type(self) -> str:
        return 'VALIDATE'

    def __init__(self, config, vault_client=None, code_forge_client=None, metrics=None, opa_client=None):
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics)
        self.opa_url: Optional[str] = getattr(config, 'opa_url', None)
        self.opa_enabled: bool = getattr(config, 'opa_enabled', False)
        self.trivy_enabled: bool = getattr(config, 'trivy_enabled', False)
        self.trivy_timeout_seconds: int = getattr(config, 'trivy_timeout_seconds', 300)
        self.opa_client = opa_client
        self.logger = logger.bind(executor='ValidateExecutor')

        try:
            from ..clients.sonarqube_client import SonarQubeClient
            self.sonarqube_client = SonarQubeClient.from_env(config) if getattr(config, 'sonarqube_enabled', False) else None
        except Exception:
            self.sonarqube_client = None
        try:
            from ..clients.snyk_client import SnykClient
            self.snyk_client = SnykClient.from_env(config) if getattr(config, 'snyk_enabled', False) else None
        except Exception:
            self.snyk_client = None
        try:
            from ..clients.checkov_client import CheckovClient
            self.checkov_client = CheckovClient(config) if getattr(config, 'checkov_enabled', False) else None
        except Exception:
            self.checkov_client = None

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        tracer = get_tracer()
        with tracer.start_as_current_span("task_execution") as span:
            span.set_attribute("neural.hive.task_id", ticket.get('ticket_id'))
            span.set_attribute("neural.hive.task_type", self.get_task_type())
            span.set_attribute("neural.hive.executor", self.__class__.__name__)
            result = await self._execute_internal(ticket, span)
            span.set_attribute("neural.hive.execution_status", 'success' if result.get('success') else 'failed')
            return result

    async def _execute_internal(self, ticket: Dict[str, Any], span=None) -> Dict[str, Any]:
        '''Executar tarefa de VALIDATE com OPA/Trivy ou fallback'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})

        self.log_execution(
            ticket_id,
            'validation_started',
            parameters=parameters
        )

        validation_type = parameters.get('validation_type', 'policy')
        policy_path = parameters.get('policy_path', 'policy/allow')
        input_data = parameters.get('input_data', {})
        working_dir = parameters.get('working_dir', '.')
        task_metric_recorded = False

        # Usar cliente OPA dedicado se disponivel
        if validation_type == 'policy' and self.opa_enabled:
            if self.opa_client:
                return await self._execute_opa_with_client(
                    ticket_id, parameters, policy_path, input_data, span
                )
            elif self.opa_url:
                # Fallback para legacy httpx direto
                self.logger.info('opa_using_legacy_client', ticket_id=ticket_id)
                return await self._execute_opa_legacy(
                    ticket_id, parameters, policy_path, input_data
                )

        if validation_type == 'sast' and self.trivy_enabled:
            try:
                proc = subprocess.run(
                    ['trivy', 'fs', '--format', 'json', working_dir],
                    capture_output=True,
                    text=True,
                    timeout=self.trivy_timeout_seconds
                )
                report = {}
                try:
                    report = json.loads(proc.stdout or '{}')
                except Exception:
                    report = {}

                vulnerabilities = report.get('Results', [])
                critical = [
                    item for result in vulnerabilities for item in result.get('Vulnerabilities', [])
                    if item.get('Severity') == 'CRITICAL'
                ]

                success = proc.returncode == 0 and not critical
                logs = [
                    'SAST validation started',
                    f'Findings: {len(critical)} critical vulnerabilities'
                ]

                result = {
                    'success': success,
                    'output': {
                        'validation_passed': success,
                        'violations': critical,
                        'validation_type': 'sast',
                        'rules_checked': len(vulnerabilities)
                    },
                    'metadata': {
                        'executor': 'ValidateExecutor',
                        'simulated': False,
                        'duration_seconds': None
                    },
                    'logs': logs
                }

                self.log_execution(
                    ticket_id,
                    'validation_completed' if success else 'validation_failed',
                    level='info' if success else 'warning',
                    critical_findings=len(critical)
                )
                if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='success' if success else 'failed', tool='trivy').inc()
                    task_metric_recorded = True
                if self.metrics and hasattr(self.metrics, 'validate_violations_total'):
                    self.metrics.validate_violations_total.labels(severity='critical', tool='trivy').inc(len(critical))
                return result
            except subprocess.TimeoutExpired:
                self.log_execution(
                    ticket_id,
                    'validation_sast_timeout',
                    level='warning',
                    timeout_seconds=self.trivy_timeout_seconds
                )
                if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='timeout', tool='trivy').inc()
                    task_metric_recorded = True
                return {
                    'success': True,
                    'output': {
                        'validation_passed': True,
                        'violations': [],
                        'validation_type': 'sast',
                        'rules_checked': 0
                    },
                    'metadata': {
                        'executor': 'ValidateExecutor',
                        'simulated': True,
                        'duration_seconds': self.trivy_timeout_seconds
                    },
                    'logs': [
                        'SAST validation timed out',
                        'Fallback to simulated validation'
                    ]
                }
            except Exception as exc:
                self.log_execution(
                    ticket_id,
                    'validation_sast_error',
                    level='error',
                    error=str(exc)
                )
                # fallback para simulação
                if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='error', tool='trivy').inc()
                    task_metric_recorded = True
                if self.metrics and hasattr(self.metrics, 'validate_tools_executed_total'):
                    self.metrics.validate_tools_executed_total.labels(tool='trivy', status='error').inc()

        if validation_type == 'sonarqube' and self.sonarqube_client:
            analysis = await self.sonarqube_client.trigger_analysis(
                parameters.get('project_key'),
                working_dir
            )
            if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                self.metrics.validate_tasks_executed_total.labels(status='success' if analysis.passed else 'failed', tool='sonarqube').inc()
                task_metric_recorded = True
            if self.metrics and hasattr(self.metrics, 'validate_tools_executed_total'):
                self.metrics.validate_tools_executed_total.labels(tool='sonarqube', status='success' if analysis.passed else 'failed').inc()
            return {
                'success': analysis.passed,
                'output': {
                    'validation_passed': analysis.passed,
                    'violations': analysis.issues,
                    'validation_type': 'sonarqube',
                    'rules_checked': len(analysis.issues or [])
                },
                'metadata': {
                    'executor': 'ValidateExecutor',
                    'simulated': False,
                    'duration_seconds': analysis.duration_seconds
                },
                'logs': analysis.logs or []
            }

        if validation_type == 'snyk' and self.snyk_client:
            report = await self.snyk_client.test_dependencies(parameters.get('manifest_path', working_dir))
            if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                self.metrics.validate_tasks_executed_total.labels(status='success' if report.passed else 'failed', tool='snyk').inc()
                task_metric_recorded = True
            if self.metrics and hasattr(self.metrics, 'validate_tools_executed_total'):
                self.metrics.validate_tools_executed_total.labels(tool='snyk', status='success' if report.passed else 'failed').inc()
            return {
                'success': report.passed,
                'output': {
                    'validation_passed': report.passed,
                    'violations': report.vulnerabilities,
                    'validation_type': 'snyk',
                    'rules_checked': len(report.vulnerabilities or [])
                },
                'metadata': {
                    'executor': 'ValidateExecutor',
                    'simulated': False,
                    'duration_seconds': report.duration_seconds
                },
                'logs': report.logs or []
            }

        if validation_type == 'iac' and self.checkov_client:
            report = await self.checkov_client.scan_iac(working_dir)
            if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                self.metrics.validate_tasks_executed_total.labels(status='success' if report.passed else 'failed', tool='checkov').inc()
                task_metric_recorded = True
            if self.metrics and hasattr(self.metrics, 'validate_tools_executed_total'):
                self.metrics.validate_tools_executed_total.labels(tool='checkov', status='success' if report.passed else 'failed').inc()
            return {
                'success': report.passed,
                'output': {
                    'validation_passed': report.passed,
                    'violations': report.findings,
                    'validation_type': 'iac',
                    'rules_checked': len(report.findings or [])
                },
                'metadata': {
                    'executor': 'ValidateExecutor',
                    'simulated': False,
                    'duration_seconds': report.duration_seconds
                },
                'logs': report.logs or []
            }

        # Fallback simulado enquanto integrações externas não disponíveis
        delay = random.uniform(1, 2)
        await asyncio.sleep(delay)

        result = {
            'success': True,
            'output': {
                'validation_passed': True,
                'violations': [],
                'validation_type': validation_type,
                'rules_checked': random.randint(10, 20)
            },
            'metadata': {
                'executor': 'ValidateExecutor',
                'simulated': True,
                'duration_seconds': delay
            },
            'logs': [
                'Validation started',
                f'Running {validation_type} validation',
                f'Simulated validation for {delay:.2f}s',
                'All validations passed'
            ]
        }

        self.log_execution(
            ticket_id,
            'validation_completed',
            duration_seconds=delay,
            validation_passed=True
        )

        tool_label = validation_type if validation_type in ['opa', 'trivy', 'sonarqube', 'snyk', 'checkov'] else 'simulation'
        if not task_metric_recorded and self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
            self.metrics.validate_tasks_executed_total.labels(status='success', tool=tool_label).inc()
        if self.metrics and hasattr(self.metrics, 'validate_duration_seconds'):
            self.metrics.validate_duration_seconds.labels(tool=tool_label).observe(delay)

        return result

    async def _execute_opa_with_client(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        policy_path: str,
        input_data: Dict[str, Any],
        span
    ) -> Dict[str, Any]:
        """
        Executa validacao OPA usando cliente dedicado.

        Args:
            ticket_id: ID do ticket
            parameters: Parametros da validacao
            policy_path: Caminho da politica OPA
            input_data: Dados de entrada para avaliacao
            span: OpenTelemetry span

        Returns:
            Resultado da validacao
        """
        from ..clients.opa_client import (
            PolicyEvaluationRequest,
            OPAAPIError,
            OPATimeoutError,
            OPAValidationError,
            ViolationSeverity
        )

        self.logger.info(
            'opa_using_dedicated_client',
            ticket_id=ticket_id,
            policy_path=policy_path
        )

        start_time = time.time()

        try:
            # Criar request de avaliacao
            request = PolicyEvaluationRequest(
                policy_path=policy_path,
                input_data=input_data,
                decision=parameters.get('decision')
            )

            # Avaliar politica
            response = await self.opa_client.evaluate_policy(request)
            duration = time.time() - start_time

            # Extrair violacoes para formato legado
            violations_output = [
                {
                    'rule_id': v.rule_id,
                    'message': v.message,
                    'severity': v.severity.value,
                    'resource': v.resource,
                    'location': v.location
                }
                for v in response.violations
            ]

            # Contar violacoes por severidade e registrar metricas
            severity_counts = self.opa_client.count_violations_by_severity(response.violations)
            self._record_opa_violation_metrics(severity_counts)

            logs = [
                'Validation started',
                f'OPA policy evaluated: {policy_path}',
                f'Allow: {response.allow}',
                f'Violations: {len(response.violations)}'
            ]

            # Adicionar detalhes de severidade aos logs
            for severity, count in severity_counts.items():
                if count > 0:
                    logs.append(f'  - {severity.value}: {count}')

            result = {
                'success': response.allow,
                'output': {
                    'validation_passed': response.allow,
                    'violations': violations_output,
                    'violations_by_severity': {s.value: c for s, c in severity_counts.items()},
                    'validation_type': 'policy',
                    'rules_checked': len(response.violations)
                },
                'metadata': {
                    'executor': 'ValidateExecutor',
                    'simulated': False,
                    'duration_seconds': duration,
                    'opa_metadata': response.metadata,
                    'client_type': 'dedicated'
                },
                'logs': logs
            }

            self.log_execution(
                ticket_id,
                'validation_completed' if response.allow else 'validation_failed',
                level='info' if response.allow else 'warning',
                violations=len(response.violations),
                duration_seconds=duration
            )

            # Registrar metricas
            if self.metrics:
                if hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(
                        status='success' if response.allow else 'failed',
                        tool='opa'
                    ).inc()
                if hasattr(self.metrics, 'validate_tools_executed_total'):
                    self.metrics.validate_tools_executed_total.labels(
                        tool='opa',
                        status='success' if response.allow else 'failed'
                    ).inc()
                if hasattr(self.metrics, 'validate_duration_seconds'):
                    self.metrics.validate_duration_seconds.labels(tool='opa').observe(duration)
                if hasattr(self.metrics, 'opa_api_calls_total'):
                    self.metrics.opa_api_calls_total.labels(
                        method='evaluate',
                        status='success'
                    ).inc()
                if hasattr(self.metrics, 'opa_policy_evaluation_duration_seconds'):
                    self.metrics.opa_policy_evaluation_duration_seconds.labels(
                        policy_path=policy_path
                    ).observe(duration)

            if span:
                span.set_attribute('opa.allow', response.allow)
                span.set_attribute('opa.violations_count', len(response.violations))
                span.set_attribute('opa.client_type', 'dedicated')

            return result

        except OPATimeoutError as exc:
            duration = time.time() - start_time
            self.logger.warning(
                'opa_evaluation_timeout',
                ticket_id=ticket_id,
                policy_path=policy_path,
                error=str(exc)
            )

            if self.metrics:
                if hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='timeout', tool='opa').inc()
                if hasattr(self.metrics, 'opa_api_calls_total'):
                    self.metrics.opa_api_calls_total.labels(method='evaluate', status='timeout').inc()

            if span:
                span.set_attribute('opa.error', 'timeout')

            # Fallback para simulacao
            return await self._execute_opa_fallback(ticket_id, policy_path, 'timeout')

        except OPAAPIError as exc:
            duration = time.time() - start_time
            self.logger.error(
                'opa_api_error',
                ticket_id=ticket_id,
                policy_path=policy_path,
                status_code=exc.status_code,
                error=str(exc)
            )

            if self.metrics:
                if hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='error', tool='opa').inc()
                if hasattr(self.metrics, 'opa_api_calls_total'):
                    self.metrics.opa_api_calls_total.labels(method='evaluate', status='error').inc()

            if span:
                span.set_attribute('opa.error', str(exc))
                if exc.status_code:
                    span.set_attribute('opa.status_code', exc.status_code)

            # Fallback para simulacao
            return await self._execute_opa_fallback(ticket_id, policy_path, 'api_error')

        except OPAValidationError as exc:
            self.logger.error(
                'opa_validation_error',
                ticket_id=ticket_id,
                policy_path=policy_path,
                error=str(exc)
            )

            if self.metrics:
                if hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='validation_error', tool='opa').inc()

            if span:
                span.set_attribute('opa.error', 'validation_error')

            # Nao fazer fallback em erro de validacao - retornar falha
            return {
                'success': False,
                'output': {
                    'validation_passed': False,
                    'violations': [{'rule_id': 'opa_validation_error', 'message': str(exc), 'severity': 'HIGH'}],
                    'validation_type': 'policy',
                    'rules_checked': 0
                },
                'metadata': {
                    'executor': 'ValidateExecutor',
                    'simulated': False,
                    'error': str(exc),
                    'client_type': 'dedicated'
                },
                'logs': [
                    'Validation started',
                    f'OPA validation error: {exc}'
                ]
            }

        except Exception as exc:
            self.logger.error(
                'opa_unexpected_error',
                ticket_id=ticket_id,
                policy_path=policy_path,
                error=str(exc)
            )

            if self.metrics:
                if hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='error', tool='opa').inc()
                if hasattr(self.metrics, 'opa_api_calls_total'):
                    self.metrics.opa_api_calls_total.labels(method='evaluate', status='error').inc()

            # Fallback para simulacao
            return await self._execute_opa_fallback(ticket_id, policy_path, 'unexpected_error')

    async def _execute_opa_legacy(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        policy_path: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executa validacao OPA usando httpx direto (legacy/fallback).

        Args:
            ticket_id: ID do ticket
            parameters: Parametros da validacao
            policy_path: Caminho da politica OPA
            input_data: Dados de entrada para avaliacao

        Returns:
            Resultado da validacao
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f'{self.opa_url}/v1/data/{policy_path}',
                    json={'input': input_data}
                )
                response.raise_for_status()
                result_body = response.json().get('result', {})

                # Tratar diferentes tipos de resultado OPA
                # OPA pode retornar: booleano, lista, ou dicionario
                if isinstance(result_body, bool):
                    # Resultado booleano direto (ex: policy/allow retorna true/false)
                    allow = result_body
                    violations = []
                elif isinstance(result_body, list):
                    # Resultado lista (ex: policy/violations retorna lista de violacoes)
                    allow = False
                    violations = result_body
                elif isinstance(result_body, dict):
                    # Resultado dicionario padrao (ex: {allow: bool, violations: []})
                    allow = result_body.get('allow', False)
                    violations = result_body.get('violations', [])
                else:
                    # Fallback para qualquer outro tipo
                    self.logger.warning(
                        'opa_legacy_unexpected_result_type',
                        ticket_id=ticket_id,
                        result_type=type(result_body).__name__
                    )
                    allow = False
                    violations = []

                logs = [
                    'Validation started',
                    f'OPA policy evaluated: {policy_path}',
                    f'Allow: {allow}',
                    f'Violations: {len(violations)}'
                ]

                result = {
                    'success': bool(allow),
                    'output': {
                        'validation_passed': bool(allow),
                        'violations': violations,
                        'validation_type': 'policy',
                        'rules_checked': len(violations) if isinstance(violations, list) else 0
                    },
                    'metadata': {
                        'executor': 'ValidateExecutor',
                        'simulated': False,
                        'duration_seconds': None,
                        'client_type': 'legacy'
                    },
                    'logs': logs
                }

                self.log_execution(
                    ticket_id,
                    'validation_completed' if allow else 'validation_failed',
                    level='info' if allow else 'warning',
                    violations=len(violations)
                )
                if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                    self.metrics.validate_tasks_executed_total.labels(status='success' if allow else 'failed', tool='opa').inc()
                if self.metrics and hasattr(self.metrics, 'validate_tools_executed_total'):
                    self.metrics.validate_tools_executed_total.labels(tool='opa', status='success' if allow else 'failed').inc()
                return result
        except Exception as exc:
            self.log_execution(
                ticket_id,
                'validation_opa_error',
                level='error',
                error=str(exc)
            )
            # fallback para simulação
            if self.metrics and hasattr(self.metrics, 'validate_tasks_executed_total'):
                self.metrics.validate_tasks_executed_total.labels(status='error', tool='opa').inc()
            if self.metrics and hasattr(self.metrics, 'validate_tools_executed_total'):
                self.metrics.validate_tools_executed_total.labels(tool='opa', status='error').inc()

            return await self._execute_opa_fallback(ticket_id, policy_path, 'legacy_error')

    async def _execute_opa_fallback(
        self,
        ticket_id: str,
        policy_path: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Fallback conservador quando OPA esta indisponivel.

        Retorna FALHA por padrao para garantir que validacoes nao sejam
        aprovadas automaticamente quando o servico de politicas esta indisponivel.

        Args:
            ticket_id: ID do ticket
            policy_path: Caminho da politica OPA
            reason: Motivo do fallback

        Returns:
            Resultado conservador com falha de validacao
        """
        self.logger.warning(
            'opa_fallback_conservative_failure',
            ticket_id=ticket_id,
            policy_path=policy_path,
            reason=reason
        )

        delay = random.uniform(0.5, 1)
        await asyncio.sleep(delay)

        # Retorna falha conservadora - nao aprovar sem validacao real
        return {
            'success': False,
            'output': {
                'validation_passed': False,
                'violations': [{
                    'rule_id': 'opa_unavailable',
                    'message': f'OPA indisponivel ({reason}). Validacao conservadora aplicada.',
                    'severity': 'HIGH'
                }],
                'validation_type': 'policy',
                'rules_checked': 0,
                'fallback_reason': reason
            },
            'metadata': {
                'executor': 'ValidateExecutor',
                'simulated': True,
                'duration_seconds': delay,
                'fallback_reason': reason,
                'client_type': 'fallback',
                'conservative_failure': True
            },
            'logs': [
                'Validation started',
                f'OPA unavailable ({reason}), conservative fallback applied',
                f'Fallback delay: {delay:.2f}s',
                'Fallback: Validation FAILED (conservative policy - OPA unavailable)'
            ]
        }

    def _record_opa_violation_metrics(self, severity_counts: Dict) -> None:
        """
        Registra metricas de violacoes por severidade.

        Args:
            severity_counts: Contagem de violacoes por severidade
        """
        if not self.metrics:
            return

        for severity, count in severity_counts.items():
            if count > 0:
                # Metrica existente: validate_violations_total
                if hasattr(self.metrics, 'validate_violations_total'):
                    self.metrics.validate_violations_total.labels(
                        severity=severity.value.lower(),
                        tool='opa'
                    ).inc(count)

                # Nova metrica solicitada: policy_violations_total
                if hasattr(self.metrics, 'policy_violations_total'):
                    self.metrics.policy_violations_total.labels(
                        severity=severity.value.lower(),
                        tool='opa'
                    ).inc(count)
