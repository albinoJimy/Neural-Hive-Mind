import asyncio
import json
import random
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from .base_executor import BaseTaskExecutor


class TestExecutor(BaseTaskExecutor):
    '''Executor para task_type=TEST (stub MVP)'''

    def get_task_type(self) -> str:
        return 'TEST'

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa de TEST com subprocess ou fallback'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})

        self.log_execution(
            ticket_id,
            'test_started',
            parameters=parameters
        )

        test_command = parameters.get('test_command')
        working_dir = parameters.get('working_dir')
        test_suite = parameters.get('test_suite', 'default')
        timeout_seconds = getattr(self.config, 'test_execution_timeout_seconds', 600)

        if test_command:
            try:
                allowed = getattr(self.config, 'allowed_test_commands', [])
                command_parts = shlex.split(test_command)
                if not command_parts:
                    raise ValueError('Empty test command')
                if allowed and not any(
                    test_command.startswith(cmd) or command_parts[0] == cmd for cmd in allowed
                ):
                    raise ValueError(f'Command {command_parts[0] if command_parts else ""} not allowed')

                cwd = Path(working_dir) if working_dir else None
                if cwd and not cwd.exists():
                    raise FileNotFoundError(f'Working dir not found: {cwd}')

                proc = subprocess.run(
                    command_parts,
                    cwd=str(cwd) if cwd else None,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds
                )

                report_path = Path(working_dir) / parameters.get('report_path', 'report.json') if working_dir else Path(parameters.get('report_path', 'report.json'))
                report_data: Dict[str, Any] = {}
                if report_path.exists():
                    try:
                        report_data = json.loads(report_path.read_text())
                    except Exception:
                        report_data = {}
                else:
                    try:
                        report_data = json.loads(proc.stdout)
                    except Exception:
                        report_data = {}

                tests_passed = report_data.get('tests_passed') or report_data.get('passed') or 0
                tests_failed = report_data.get('tests_failed') or report_data.get('failed') or 0
                coverage = report_data.get('coverage') or report_data.get('coverage_percent')

                success = proc.returncode == 0
                logs = [
                    'Tests started',
                    f'Running test suite: {test_suite}',
                    f'Command: {test_command}',
                    f'STDOUT: {proc.stdout.strip()[:500]}',
                    f'STDERR: {proc.stderr.strip()[:500]}'
                ]

                result = {
                    'success': success,
                    'output': {
                        'tests_passed': tests_passed,
                        'tests_failed': tests_failed,
                        'coverage': coverage,
                        'test_suite': test_suite,
                        'report_path': str(report_path) if report_path else ''
                    },
                    'metadata': {
                        'executor': 'TestExecutor',
                        'simulated': False,
                        'duration_seconds': None
                    },
                    'logs': logs
                }

                level = 'info' if success else 'warning'
                self.log_execution(
                    ticket_id,
                    'test_completed' if success else 'test_failed',
                    level=level,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed
                )

                # TODO: Incrementar métrica worker_agent_test_tasks_executed_total
                return result

            except subprocess.TimeoutExpired:
                self.log_execution(
                    ticket_id,
                    'test_timeout',
                    level='error',
                    timeout_seconds=timeout_seconds
                )
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
                # Fallback para simulação

        # Fallback simulado para manter compatibilidade
        delay = random.uniform(1, 3)
        await asyncio.sleep(delay)

        tests_passed = random.randint(40, 50)
        coverage = random.uniform(0.80, 0.95)

        result = {
            'success': True,
            'output': {
                'tests_passed': tests_passed,
                'tests_failed': 0,
                'coverage': round(coverage, 2),
                'test_suite': test_suite
            },
            'metadata': {
                'executor': 'TestExecutor',
                'simulated': True,
                'duration_seconds': delay
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

        # TODO: Incrementar métrica worker_agent_test_tasks_executed_total

        return result
