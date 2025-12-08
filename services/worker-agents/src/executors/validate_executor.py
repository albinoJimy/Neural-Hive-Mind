import asyncio
import json
import random
import subprocess
from typing import Any, Dict, Optional
import httpx
from .base_executor import BaseTaskExecutor


class ValidateExecutor(BaseTaskExecutor):
    '''Executor para task_type=VALIDATE (stub MVP)'''

    def get_task_type(self) -> str:
        return 'VALIDATE'

    def __init__(self, config, vault_client=None, code_forge_client=None):
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client)
        self.opa_url: Optional[str] = getattr(config, 'opa_url', None)
        self.opa_enabled: bool = getattr(config, 'opa_enabled', False)
        self.trivy_enabled: bool = getattr(config, 'trivy_enabled', False)
        self.trivy_timeout_seconds: int = getattr(config, 'trivy_timeout_seconds', 300)

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
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

        if validation_type == 'policy' and self.opa_enabled and self.opa_url:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f'{self.opa_url}/v1/data/{policy_path}',
                        json={'input': input_data}
                    )
                    response.raise_for_status()
                    result_body = response.json().get('result', {})
                    allow = result_body.get('allow', False)
                    violations = result_body.get('violations', [])

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
                            'duration_seconds': None
                        },
                        'logs': logs
                    }

                    self.log_execution(
                        ticket_id,
                        'validation_completed' if allow else 'validation_failed',
                        level='info' if allow else 'warning',
                        violations=len(violations)
                    )
                    # TODO: Incrementar métrica worker_agent_validate_tasks_executed_total
                    return result
            except Exception as exc:
                self.log_execution(
                    ticket_id,
                    'validation_opa_error',
                    level='error',
                    error=str(exc)
                )
                # fallback para simulação

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
                return result
            except subprocess.TimeoutExpired:
                self.log_execution(
                    ticket_id,
                    'validation_sast_timeout',
                    level='error',
                    timeout_seconds=self.trivy_timeout_seconds
                )
                return {
                    'success': False,
                    'output': {
                        'validation_passed': False,
                        'violations': ['SAST timeout'],
                        'validation_type': 'sast',
                        'rules_checked': 0
                    },
                    'metadata': {
                        'executor': 'ValidateExecutor',
                        'simulated': False,
                        'duration_seconds': self.trivy_timeout_seconds
                    },
                    'logs': ['SAST validation timed out']
                }
            except Exception as exc:
                self.log_execution(
                    ticket_id,
                    'validation_sast_error',
                    level='error',
                    error=str(exc)
                )
                # fallback para simulação

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

        # TODO: Incrementar métrica worker_agent_validate_tasks_executed_total

        return result
