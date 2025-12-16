import asyncio
import random
from typing import Any, Dict, Optional
from neural_hive_integration.clients.code_forge_client import CodeForgeClient
from neural_hive_observability import get_tracer
from .base_executor import BaseTaskExecutor


class BuildExecutor(BaseTaskExecutor):
    '''Executor para task_type=BUILD (stub MVP)'''

    def get_task_type(self) -> str:
        return 'BUILD'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client: Optional[CodeForgeClient] = None,
        metrics=None
    ):
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics)

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa de BUILD integrado com Code Forge ou fallback'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})
        artifact_id = parameters.get('artifact_id') or ticket_id
        branch = parameters.get('branch') or parameters.get('ref') or 'main'
        commit_sha = parameters.get('commit_sha') or parameters.get('commit') or None
        build_args = parameters.get('build_args') or {}
        env_vars = parameters.get('env') or parameters.get('env_vars') or {}
        pipeline_timeout = parameters.get('timeout_seconds') or getattr(self.config, 'code_forge_timeout_seconds', 14400)
        poll_interval = parameters.get('poll_interval_seconds') or 30

        tracer = get_tracer()
        with tracer.start_as_current_span("task_execution") as span:
            span.set_attribute("neural.hive.task_id", ticket_id)
            span.set_attribute("neural.hive.task_type", self.get_task_type())
            span.set_attribute("neural.hive.executor", self.__class__.__name__)

            self.log_execution(
                ticket_id,
                'build_started',
                parameters=parameters
            )

            use_simulation = not self.code_forge_client

            if self.code_forge_client:
                try:
                    # Retry leve para lidar com falhas transitórias
                    retries = 0
                    max_retries = getattr(self.config, 'code_forge_retry_attempts', 3)
                    backoff = getattr(self.config, 'retry_backoff_base_seconds', 2)
                    pipeline_id: Optional[str] = None

                    while retries < max_retries:
                        try:
                            pipeline_id = await self.code_forge_client.trigger_pipeline(
                                artifact_id
                            )
                            if self.metrics and hasattr(self.metrics, 'code_forge_api_calls_total'):
                                self.metrics.code_forge_api_calls_total.labels(method='trigger', status='success').inc()
                            break
                        except Exception as exc:
                            retries += 1
                            if self.metrics and hasattr(self.metrics, 'code_forge_api_calls_total'):
                                self.metrics.code_forge_api_calls_total.labels(method='trigger', status='error').inc()
                            if retries >= max_retries:
                                raise
                            await asyncio.sleep(min(backoff * (2 ** (retries - 1)), getattr(self.config, 'retry_backoff_max_seconds', 60)))

                    if not pipeline_id:
                        raise RuntimeError('Pipeline not triggered')

                    status = await self.code_forge_client.wait_for_pipeline_completion(
                        pipeline_id,
                        poll_interval=poll_interval,
                        timeout=pipeline_timeout
                    )

                    duration_seconds = status.duration_ms / 1000 if status.duration_ms else None
                    success = status.status in ('completed', 'succeeded')
                    failed_state = status.status in ('failed', 'cancelled', 'timeout', 'error')

                    stage = getattr(status, 'stage', None)
                    artifacts = getattr(status, 'artifacts', None)
                    sbom = getattr(status, 'sbom', None)
                    signature = getattr(status, 'signature', None)

                    result = {
                        'success': success,
                        'output': {
                            'pipeline_id': pipeline_id,
                            'artifact_id': artifact_id,
                            'branch': branch,
                            'commit_sha': commit_sha,
                            'artifacts': artifacts,
                            'sbom': sbom,
                            'signature': signature
                        },
                        'metadata': {
                            'executor': 'BuildExecutor',
                            'simulated': False,
                            'duration_seconds': duration_seconds
                        },
                        'logs': [
                            'Build started',
                            f'Triggered pipeline {pipeline_id} for artifact {artifact_id}',
                            f'Pipeline status: {status.status} at stage {stage}',
                            'Build completed successfully via Code Forge' if success else 'Build failed via Code Forge'
                        ]
                    }

                    log_level = 'info' if success else 'warning'
                    event = 'build_completed' if success else 'build_failed'
                    self.log_execution(
                        ticket_id,
                        event,
                        level=log_level,
                        pipeline_id=pipeline_id,
                        status=status.status,
                        stage=stage,
                        artifacts=len(artifacts or [])
                    )

                    if self.metrics:
                        if hasattr(self.metrics, 'build_tasks_executed_total'):
                            self.metrics.build_tasks_executed_total.labels(status='success' if success else 'failed').inc()
                        if hasattr(self.metrics, 'build_duration_seconds') and duration_seconds is not None:
                            self.metrics.build_duration_seconds.labels(stage=stage or 'completed').observe(duration_seconds)
                        if hasattr(self.metrics, 'build_artifacts_generated_total') and artifacts:
                            for artifact in artifacts:
                                artifact_type = artifact.get('type') if isinstance(artifact, dict) else 'unknown'
                                self.metrics.build_artifacts_generated_total.labels(type=artifact_type).inc()
                        if hasattr(self.metrics, 'code_forge_api_calls_total'):
                            self.metrics.code_forge_api_calls_total.labels(method='status', status='success').inc()

                    if failed_state and not success:
                        span.set_attribute("neural.hive.execution_status", 'failed')
                        return {
                            **result,
                            'logs': result['logs'] + [f'Pipeline ended with status {status.status}']
                        }

                    span.set_attribute("neural.hive.execution_status", 'success' if success else 'failed')
                    return result

                except Exception as exc:
                    self.log_execution(
                        ticket_id,
                        'build_code_forge_error',
                        level='error',
                        error=str(exc)
                    )
                    if self.metrics and hasattr(self.metrics, 'build_tasks_executed_total'):
                        self.metrics.build_tasks_executed_total.labels(status='failed').inc()
                    use_simulation = True

            if use_simulation and self.code_forge_client:
                self.log_execution(ticket_id, 'build_fallback_simulation', level='warning')

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

            if self.metrics and hasattr(self.metrics, 'build_tasks_executed_total'):
                self.metrics.build_tasks_executed_total.labels(status='success').inc()
            if self.metrics and hasattr(self.metrics, 'build_duration_seconds'):
                self.metrics.build_duration_seconds.labels(stage='simulated').observe(delay)

            span.set_attribute("neural.hive.execution_status", 'success')
            return result
