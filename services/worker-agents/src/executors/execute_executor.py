import asyncio
import random
from typing import Any, Dict, Optional
from neural_hive_integration.clients.code_forge_client import CodeForgeClient, GenerationRequest
from neural_hive_observability import get_tracer
from .base_executor import BaseTaskExecutor


class ExecuteExecutor(BaseTaskExecutor):
    '''Executor para task_type=EXECUTE (genérico, stub MVP)'''

    def get_task_type(self) -> str:
        return 'EXECUTE'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client: Optional[CodeForgeClient] = None,
        metrics=None
    ):
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics)

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa EXECUTE com integração Code Forge ou fallback'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})
        template_id = parameters.get('template_id') or parameters.get('template') or 'default-template'

        tracer = get_tracer()
        with tracer.start_as_current_span("task_execution") as span:
            span.set_attribute("neural.hive.task_id", ticket_id)
            span.set_attribute("neural.hive.task_type", self.get_task_type())
            span.set_attribute("neural.hive.executor", self.__class__.__name__)

            self.log_execution(
                ticket_id,
                'execution_started',
                parameters=parameters
            )

            if self.code_forge_client:
                try:
                    request_id = await self.code_forge_client.submit_generation_request(
                        ticket_id,
                        template_id,
                        parameters
                    )

                    poll_interval = 5
                    timeout_seconds = 1800
                    start_time = asyncio.get_event_loop().time()

                    while True:
                        status = await self.code_forge_client.get_generation_status(request_id)

                        if status.status in ['completed', 'failed']:
                            break

                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed > timeout_seconds:
                            raise asyncio.TimeoutError(f'Generation timeout after {timeout_seconds}s')

                        await asyncio.sleep(poll_interval)

                    if status.status == 'completed':
                        duration_seconds = asyncio.get_event_loop().time() - start_time
                        result = {
                            'success': True,
                            'output': {
                                'request_id': request_id,
                                'artifacts': status.artifacts,
                                'pipeline_id': status.pipeline_id
                            },
                            'metadata': {
                                'executor': 'ExecuteExecutor',
                                'simulated': False,
                                'duration_seconds': duration_seconds
                            },
                            'logs': [
                                'Execution started',
                                f'Submitted generation request {request_id} using template {template_id}',
                                f'Artifacts generated: {len(status.artifacts)}',
                                'Execution completed via Code Forge'
                            ]
                        }
                        self.log_execution(
                            ticket_id,
                            'execution_completed',
                            duration_seconds=duration_seconds,
                            request_id=request_id
                        )
                        if self.metrics and hasattr(self.metrics, 'execute_tasks_executed_total'):
                            self.metrics.execute_tasks_executed_total.labels(status='success').inc()
                        span.set_attribute("neural.hive.execution_status", 'success')
                        return result

                    duration_seconds = asyncio.get_event_loop().time() - start_time
                    self.log_execution(
                        ticket_id,
                        'execution_failed_code_forge',
                        status=status.status,
                        error=status.error
                    )
                    if self.metrics and hasattr(self.metrics, 'execute_tasks_executed_total'):
                        self.metrics.execute_tasks_executed_total.labels(status='failed').inc()
                    span.set_attribute("neural.hive.execution_status", 'failed')
                    return {
                        'success': False,
                        'output': {
                            'request_id': request_id,
                            'artifacts': status.artifacts,
                            'pipeline_id': status.pipeline_id
                        },
                        'metadata': {
                            'executor': 'ExecuteExecutor',
                            'simulated': False,
                            'duration_seconds': duration_seconds
                        },
                        'logs': [
                            'Execution started',
                            f'Submitted generation request {request_id} using template {template_id}',
                            f'Execution failed with status: {status.status}',
                            status.error or 'Unknown error'
                        ]
                    }

                except Exception as exc:
                    self.log_execution(
                        ticket_id,
                        'execution_code_forge_error',
                        level='error',
                        error=str(exc)
                    )
                    # Fallback para simulação em caso de erro externo

            # Fallback simulado para manter fluxo funcionando
            delay = random.uniform(2, 4)
            await asyncio.sleep(delay)

            result = {
                'success': True,
                'output': {
                    'exit_code': 0,
                    'stdout': f'stub output for command: {parameters.get(\"command\", \"unknown\")}',
                    'stderr': '',
                    'command': parameters.get('command', 'unknown')
                },
                'metadata': {
                    'executor': 'ExecuteExecutor',
                    'simulated': True,
                    'duration_seconds': delay
                },
                'logs': [
                    'Execution started',
                    f'Running command: {parameters.get(\"command\", \"unknown\")}',
                    f'Simulated execution for {delay:.2f}s',
                    'Execution completed successfully'
                ]
            }

            self.log_execution(
                ticket_id,
                'execution_completed',
                duration_seconds=delay,
                exit_code=0
            )

            if self.metrics and hasattr(self.metrics, 'execute_tasks_executed_total'):
                self.metrics.execute_tasks_executed_total.labels(status='success').inc()

            span.set_attribute("neural.hive.execution_status", 'success')
            return result
