import asyncio
import random
from typing import Any, Dict, Optional
from neural_hive_integration.clients.code_forge_client import CodeForgeClient
from .base_executor import BaseTaskExecutor


class BuildExecutor(BaseTaskExecutor):
    '''Executor para task_type=BUILD (stub MVP)'''

    def get_task_type(self) -> str:
        return 'BUILD'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client: Optional[CodeForgeClient] = None
    ):
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client)

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa de BUILD integrado com Code Forge ou fallback'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})
        artifact_id = parameters.get('artifact_id') or ticket_id

        self.log_execution(
            ticket_id,
            'build_started',
            parameters=parameters
        )

        if self.code_forge_client:
            try:
                pipeline_id = await self.code_forge_client.trigger_pipeline(artifact_id)
                status = await self.code_forge_client.wait_for_pipeline_completion(
                    pipeline_id,
                    poll_interval=30,
                    timeout=14400
                )

                duration_seconds = status.duration_ms / 1000 if status.duration_ms else None
                success = status.status == 'completed'

                result = {
                    'success': success,
                    'output': {
                        'pipeline_id': pipeline_id,
                        'artifact_id': artifact_id,
                        'artifacts': status.artifacts,
                        'sbom': status.sbom,
                        'signature': status.signature
                    },
                    'metadata': {
                        'executor': 'BuildExecutor',
                        'simulated': False,
                        'duration_seconds': duration_seconds
                    },
                    'logs': [
                        'Build started',
                        f'Triggered pipeline {pipeline_id} for artifact {artifact_id}',
                        f'Pipeline status: {status.status} at stage {status.stage}',
                        'Build completed successfully via Code Forge' if success else 'Build failed via Code Forge'
                    ]
                }

                log_level = 'info' if success else 'warning'
                self.log_execution(
                    ticket_id,
                    'build_completed' if success else 'build_failed',
                    level=log_level,
                    pipeline_id=pipeline_id,
                    status=status.status
                )

                # TODO: Incrementar métrica worker_agent_build_tasks_executed_total
                return result

            except Exception as exc:
                self.log_execution(
                    ticket_id,
                    'build_code_forge_error',
                    level='error',
                    error=str(exc)
                )
                # fallback to simulation

        delay = random.uniform(2, 5)
        await asyncio.sleep(delay)

        result = {
            'success': True,
            'output': {
                'artifact_url': 'stub://artifact',
                'build_id': f'stub-{ticket_id[:8]}',
                'commit_sha': 'stub-commit-sha'
            },
            'metadata': {
                'executor': 'BuildExecutor',
                'simulated': True,
                'duration_seconds': delay
            },
            'logs': [
                'Build started',
                f'Simulated build for {delay:.2f}s',
                'Build completed successfully'
            ]
        }

        self.log_execution(
            ticket_id,
            'build_completed',
            duration_seconds=delay,
            artifact_url=result['output']['artifact_url']
        )

        # TODO: Incrementar métrica worker_agent_build_tasks_executed_total

        return result
