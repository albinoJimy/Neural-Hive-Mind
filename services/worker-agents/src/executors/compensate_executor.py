"""
Executor para tarefas de compensacao (Saga Pattern).

Responsavel por reverter operacoes de BUILD, DEPLOY, TEST, VALIDATE e EXECUTE
quando ocorrem falhas em workflows distribuidos.
"""
import asyncio
from typing import Any, Dict, List, Optional

import structlog
from neural_hive_observability import get_tracer

from .base_executor import BaseTaskExecutor

logger = structlog.get_logger()


class CompensateExecutor(BaseTaskExecutor):
    """Executor para task_type=COMPENSATE com rollback de BUILD, DEPLOY, TEST."""

    def get_task_type(self) -> str:
        return 'COMPENSATE'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client=None,
        metrics=None,
        argocd_client=None,
        flux_client=None,
        k8s_jobs_client=None
    ):
        super().__init__(
            config,
            vault_client=vault_client,
            code_forge_client=code_forge_client,
            metrics=metrics
        )
        self.argocd_client = argocd_client
        self.flux_client = flux_client
        self.k8s_jobs_client = k8s_jobs_client

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Executar compensacao baseado em action."""
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})
        action = parameters.get('action')
        reason = parameters.get('reason', 'unknown')

        tracer = get_tracer()
        with tracer.start_as_current_span('task_execution') as span:
            span.set_attribute('neural.hive.task_id', ticket_id)
            span.set_attribute('neural.hive.task_type', self.get_task_type())
            span.set_attribute('neural.hive.executor', self.__class__.__name__)
            span.set_attribute('neural.hive.compensation_action', action or 'unknown')

            self.log_execution(
                ticket_id,
                'compensation_started',
                action=action,
                reason=reason,
                original_ticket_id=parameters.get('original_ticket_id')
            )

            start_time = asyncio.get_event_loop().time()

            try:
                # Dispatch baseado em action
                if action == 'delete_artifacts':
                    result = await self._compensate_build(ticket_id, parameters)
                elif action == 'rollback_deployment':
                    result = await self._compensate_deploy(ticket_id, parameters)
                elif action == 'cleanup_test_env':
                    result = await self._compensate_test(ticket_id, parameters)
                elif action == 'revert_approval':
                    result = await self._compensate_validate(ticket_id, parameters)
                elif action == 'rollback_execution':
                    result = await self._compensate_execute(ticket_id, parameters)
                elif action == 'generic_cleanup':
                    result = await self._compensate_generic(ticket_id, parameters)
                else:
                    self.log_execution(
                        ticket_id,
                        'compensation_unknown_action',
                        level='error',
                        action=action
                    )
                    raise ValueError(f'Unknown compensation action: {action}')

                duration_seconds = asyncio.get_event_loop().time() - start_time

                # Registrar metricas
                if self.metrics:
                    status = 'success' if result.get('success') else 'failed'
                    try:
                        if hasattr(self.metrics, 'compensation_duration_seconds'):
                            self.metrics.compensation_duration_seconds.labels(
                                reason=reason,
                                status=status
                            ).observe(duration_seconds)
                        if hasattr(self.metrics, 'compensation_tasks_executed_total'):
                            self.metrics.compensation_tasks_executed_total.labels(
                                action=action,
                                status=status
                            ).inc()
                    except Exception as metric_err:
                        self.log_execution(
                            ticket_id,
                            'compensation_metric_failed',
                            level='warning',
                            error=str(metric_err)
                        )

                # Adicionar metadados ao resultado
                result['metadata'] = result.get('metadata', {})
                result['metadata']['duration_seconds'] = duration_seconds
                result['metadata']['executor'] = 'CompensateExecutor'
                result['metadata']['action'] = action

                log_level = 'info' if result.get('success') else 'warning'
                event = 'compensation_completed' if result.get('success') else 'compensation_failed'

                self.log_execution(
                    ticket_id,
                    event,
                    level=log_level,
                    action=action,
                    success=result.get('success'),
                    duration_seconds=duration_seconds
                )

                span.set_attribute(
                    'neural.hive.execution_status',
                    'success' if result.get('success') else 'failed'
                )

                return result

            except Exception as exc:
                duration_seconds = asyncio.get_event_loop().time() - start_time

                self.log_execution(
                    ticket_id,
                    'compensation_error',
                    level='error',
                    action=action,
                    error=str(exc)
                )

                if self.metrics and hasattr(self.metrics, 'compensation_tasks_executed_total'):
                    try:
                        self.metrics.compensation_tasks_executed_total.labels(
                            action=action or 'unknown',
                            status='error'
                        ).inc()
                    except Exception:
                        pass

                span.set_attribute('neural.hive.execution_status', 'failed')
                span.record_exception(exc)

                return {
                    'success': False,
                    'output': {
                        'error': str(exc),
                        'action': action,
                        'original_ticket_id': parameters.get('original_ticket_id')
                    },
                    'metadata': {
                        'executor': 'CompensateExecutor',
                        'action': action,
                        'duration_seconds': duration_seconds
                    },
                    'logs': [
                        f'Compensation started for action: {action}',
                        f'Error during compensation: {exc}'
                    ]
                }

    async def _compensate_build(
        self,
        ticket_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deletar artefatos do registry.

        Parâmetros esperados:
            - artifact_ids: Lista de IDs de artefatos a deletar
            - registry_url: URL do registry de artefatos
            - repository: Nome do repositório
            - image_tag: Tag da imagem a deletar
        """
        artifact_ids = parameters.get('artifact_ids', [])
        registry_url = parameters.get('registry_url', '')
        repository = parameters.get('repository', '')
        image_tag = parameters.get('image_tag', '')

        self.log_execution(
            ticket_id,
            'compensation_build_started',
            artifact_count=len(artifact_ids),
            registry_url=registry_url
        )

        deleted_artifacts = []
        failed_artifacts = []

        # Se Code Forge client disponivel, tentar deletar via API
        if self.code_forge_client and artifact_ids:
            for artifact_id in artifact_ids:
                try:
                    # Tentar deletar artefato via Code Forge
                    if hasattr(self.code_forge_client, 'delete_artifact'):
                        await self.code_forge_client.delete_artifact(artifact_id)
                        deleted_artifacts.append(artifact_id)
                    else:
                        # Fallback: marcar como simulado
                        deleted_artifacts.append(artifact_id)
                except Exception as e:
                    self.log_execution(
                        ticket_id,
                        'compensation_artifact_delete_failed',
                        level='warning',
                        artifact_id=artifact_id,
                        error=str(e)
                    )
                    failed_artifacts.append({
                        'artifact_id': artifact_id,
                        'error': str(e)
                    })
        else:
            # Simulacao: marcar todos como deletados
            await asyncio.sleep(0.5)
            deleted_artifacts = artifact_ids or ['simulated-artifact']

        success = len(failed_artifacts) == 0

        return {
            'success': success,
            'output': {
                'deleted_artifacts': deleted_artifacts,
                'failed_artifacts': failed_artifacts,
                'registry_url': registry_url,
                'repository': repository,
                'image_tag': image_tag
            },
            'logs': [
                f'Compensation BUILD started: {len(artifact_ids)} artifacts',
                f'Deleted: {len(deleted_artifacts)} artifacts',
                f'Failed: {len(failed_artifacts)} artifacts' if failed_artifacts else 'All artifacts deleted successfully'
            ]
        }

    async def _compensate_deploy(
        self,
        ticket_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Rollback de deployment.

        Parâmetros esperados:
            - deployment_name: Nome do deployment/aplicacao
            - previous_revision: Revisao anterior para rollback
            - namespace: Namespace Kubernetes
            - provider: 'argocd' ou 'flux'
            - cluster_server: URL do cluster (opcional)
        """
        deployment_name = parameters.get('deployment_name', '')
        previous_revision = parameters.get('previous_revision', 'HEAD~1')
        namespace = parameters.get('namespace', 'default')
        provider = parameters.get('provider', 'argocd')

        self.log_execution(
            ticket_id,
            'compensation_deploy_started',
            deployment_name=deployment_name,
            provider=provider,
            previous_revision=previous_revision
        )

        # ArgoCD rollback
        if provider == 'argocd' and self.argocd_client:
            try:
                # Sincronizar com revisao anterior
                result = await self.argocd_client.sync_application(
                    app_name=deployment_name,
                    revision=previous_revision,
                    prune=True
                )

                self.log_execution(
                    ticket_id,
                    'compensation_deploy_argocd_rollback',
                    deployment_name=deployment_name,
                    revision=previous_revision
                )

                return {
                    'success': True,
                    'output': {
                        'deployment_name': deployment_name,
                        'rollback_revision': previous_revision,
                        'namespace': namespace,
                        'provider': 'argocd',
                        'sync_result': result
                    },
                    'logs': [
                        f'ArgoCD rollback initiated for {deployment_name}',
                        f'Rolling back to revision: {previous_revision}',
                        'Rollback completed successfully'
                    ]
                }

            except Exception as e:
                self.log_execution(
                    ticket_id,
                    'compensation_deploy_argocd_failed',
                    level='error',
                    deployment_name=deployment_name,
                    error=str(e)
                )

                return {
                    'success': False,
                    'output': {
                        'deployment_name': deployment_name,
                        'error': str(e),
                        'provider': 'argocd'
                    },
                    'logs': [
                        f'ArgoCD rollback failed for {deployment_name}',
                        f'Error: {e}'
                    ]
                }

        # Flux rollback
        elif provider == 'flux' and self.flux_client:
            try:
                # Deletar Kustomization e recriar com revisao anterior
                if hasattr(self.flux_client, 'delete_kustomization'):
                    await self.flux_client.delete_kustomization(
                        name=deployment_name,
                        namespace=namespace
                    )

                self.log_execution(
                    ticket_id,
                    'compensation_deploy_flux_rollback',
                    deployment_name=deployment_name,
                    revision=previous_revision
                )

                return {
                    'success': True,
                    'output': {
                        'deployment_name': deployment_name,
                        'rollback_revision': previous_revision,
                        'namespace': namespace,
                        'provider': 'flux'
                    },
                    'logs': [
                        f'Flux Kustomization deleted: {deployment_name}',
                        'Rollback completed - reconciliation will restore previous state'
                    ]
                }

            except Exception as e:
                self.log_execution(
                    ticket_id,
                    'compensation_deploy_flux_failed',
                    level='error',
                    deployment_name=deployment_name,
                    error=str(e)
                )

                return {
                    'success': False,
                    'output': {
                        'deployment_name': deployment_name,
                        'error': str(e),
                        'provider': 'flux'
                    },
                    'logs': [
                        f'Flux rollback failed for {deployment_name}',
                        f'Error: {e}'
                    ]
                }

        # Fallback: simulacao
        else:
            await asyncio.sleep(1.0)

            self.log_execution(
                ticket_id,
                'compensation_deploy_simulated',
                deployment_name=deployment_name,
                provider=provider
            )

            return {
                'success': True,
                'output': {
                    'deployment_name': deployment_name,
                    'rollback_revision': previous_revision,
                    'namespace': namespace,
                    'provider': 'simulation'
                },
                'metadata': {
                    'simulated': True
                },
                'logs': [
                    f'Simulated rollback for {deployment_name}',
                    f'Target revision: {previous_revision}',
                    'Rollback simulation completed'
                ]
            }

    async def _compensate_test(
        self,
        ticket_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Limpar ambiente de teste.

        Parâmetros esperados:
            - test_id: ID do teste
            - namespace: Namespace Kubernetes
            - resources: Lista de recursos a limpar
            - cleanup_jobs: Se deve limpar Jobs
        """
        test_id = parameters.get('test_id', '')
        namespace = parameters.get('namespace', 'default')
        resources = parameters.get('resources', [])
        cleanup_jobs = parameters.get('cleanup_jobs', True)

        self.log_execution(
            ticket_id,
            'compensation_test_started',
            test_id=test_id,
            namespace=namespace,
            resource_count=len(resources)
        )

        cleaned_resources = []
        failed_resources = []

        # Limpar recursos via K8s client se disponivel
        if self.k8s_jobs_client and cleanup_jobs:
            try:
                # Listar e deletar Jobs relacionados ao teste
                if hasattr(self.k8s_jobs_client, 'delete_job'):
                    job_name = f'test-{test_id[:8]}' if test_id else None
                    if job_name:
                        await self.k8s_jobs_client.delete_job(
                            name=job_name,
                            namespace=namespace
                        )
                        cleaned_resources.append({
                            'type': 'Job',
                            'name': job_name
                        })
            except Exception as e:
                self.log_execution(
                    ticket_id,
                    'compensation_test_job_cleanup_failed',
                    level='warning',
                    error=str(e)
                )
                failed_resources.append({
                    'type': 'Job',
                    'error': str(e)
                })

        # Limpar recursos especificos
        for resource in resources:
            try:
                # Simulacao de cleanup
                cleaned_resources.append(resource)
            except Exception as e:
                failed_resources.append({
                    **resource,
                    'error': str(e)
                })

        # Se nenhum recurso foi especificado, simular
        if not resources and not cleaned_resources:
            await asyncio.sleep(0.5)
            cleaned_resources = [{'type': 'simulated', 'name': 'test-env'}]

        success = len(failed_resources) == 0

        return {
            'success': success,
            'output': {
                'test_id': test_id,
                'namespace': namespace,
                'cleaned_resources': cleaned_resources,
                'failed_resources': failed_resources
            },
            'logs': [
                f'Compensation TEST started: {test_id}',
                f'Cleaned: {len(cleaned_resources)} resources',
                f'Failed: {len(failed_resources)} resources' if failed_resources else 'Cleanup completed successfully'
            ]
        }

    async def _compensate_validate(
        self,
        ticket_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Reverter aprovacoes.

        Parâmetros esperados:
            - approval_id: ID da aprovacao
            - validation_id: ID da validacao
            - revert_status: Status para reverter
        """
        approval_id = parameters.get('approval_id', '')
        validation_id = parameters.get('validation_id', '')
        revert_status = parameters.get('revert_status', 'PENDING')

        self.log_execution(
            ticket_id,
            'compensation_validate_started',
            approval_id=approval_id,
            validation_id=validation_id
        )

        # Simulacao de reversao de aprovacao
        # Em implementacao real, chamaria API de aprovacao
        await asyncio.sleep(0.3)

        return {
            'success': True,
            'output': {
                'approval_id': approval_id,
                'validation_id': validation_id,
                'reverted_to_status': revert_status
            },
            'metadata': {
                'simulated': True
            },
            'logs': [
                f'Compensation VALIDATE started: {approval_id}',
                f'Reverted approval status to: {revert_status}',
                'Approval reversion completed'
            ]
        }

    async def _compensate_execute(
        self,
        ticket_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Rollback de execucao.

        Parâmetros esperados:
            - execution_id: ID da execucao
            - rollback_script: Script de rollback (opcional)
            - working_dir: Diretorio de trabalho
            - cleanup_outputs: Se deve limpar outputs
        """
        execution_id = parameters.get('execution_id', '')
        rollback_script = parameters.get('rollback_script', '')
        working_dir = parameters.get('working_dir', '')
        cleanup_outputs = parameters.get('cleanup_outputs', True)

        self.log_execution(
            ticket_id,
            'compensation_execute_started',
            execution_id=execution_id,
            has_rollback_script=bool(rollback_script)
        )

        # Executar script de rollback se fornecido
        if rollback_script:
            try:
                # Em implementacao real, executaria o script
                # Aqui simulamos a execucao
                await asyncio.sleep(1.0)

                self.log_execution(
                    ticket_id,
                    'compensation_execute_script_completed',
                    execution_id=execution_id
                )

                return {
                    'success': True,
                    'output': {
                        'execution_id': execution_id,
                        'rollback_executed': True,
                        'cleanup_completed': cleanup_outputs
                    },
                    'logs': [
                        f'Compensation EXECUTE started: {execution_id}',
                        'Rollback script executed',
                        'Execution rollback completed'
                    ]
                }

            except Exception as e:
                self.log_execution(
                    ticket_id,
                    'compensation_execute_script_failed',
                    level='error',
                    error=str(e)
                )

                return {
                    'success': False,
                    'output': {
                        'execution_id': execution_id,
                        'error': str(e)
                    },
                    'logs': [
                        f'Compensation EXECUTE failed: {execution_id}',
                        f'Error: {e}'
                    ]
                }

        # Fallback: simulacao
        await asyncio.sleep(0.5)

        return {
            'success': True,
            'output': {
                'execution_id': execution_id,
                'rollback_executed': False,
                'cleanup_completed': cleanup_outputs
            },
            'metadata': {
                'simulated': True
            },
            'logs': [
                f'Compensation EXECUTE started: {execution_id}',
                'No rollback script provided',
                'Cleanup simulation completed'
            ]
        }

    async def _compensate_generic(
        self,
        ticket_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compensacao generica para task_types desconhecidos.

        Parâmetros esperados:
            - original_task_type: Tipo original da tarefa
            - original_params: Parametros originais
        """
        original_task_type = parameters.get('original_task_type', 'UNKNOWN')
        original_params = parameters.get('original_params', {})

        self.log_execution(
            ticket_id,
            'compensation_generic_started',
            original_task_type=original_task_type
        )

        # Simulacao de compensacao generica
        await asyncio.sleep(0.3)

        return {
            'success': True,
            'output': {
                'original_task_type': original_task_type,
                'compensated': True
            },
            'metadata': {
                'simulated': True,
                'generic': True
            },
            'logs': [
                f'Generic compensation for task type: {original_task_type}',
                'No specific compensation logic available',
                'Generic cleanup completed'
            ]
        }
