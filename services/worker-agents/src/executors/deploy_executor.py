import asyncio
import random
from typing import Any, Dict, Optional
from neural_hive_observability import get_tracer
from .base_executor import BaseTaskExecutor

from ..clients.argocd_client import (
    ArgoCDClient,
    ArgoCDAPIError,
    ArgoCDTimeoutError,
    ApplicationCreateRequest,
    ApplicationMetadata,
    ApplicationSpec,
    ApplicationSource,
    ApplicationDestination,
    SyncPolicy
)
from ..clients.flux_client import (
    FluxClient,
    FluxAPIError,
    FluxTimeoutError,
    KustomizationRequest,
    KustomizationMetadata,
    KustomizationSpec,
    SourceReference
)


class DeployExecutor(BaseTaskExecutor):
    '''Executor para task_type=DEPLOY com suporte a ArgoCD e Flux'''

    def get_task_type(self) -> str:
        return 'DEPLOY'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client=None,
        metrics=None,
        argocd_client: Optional[ArgoCDClient] = None,
        flux_client: Optional[FluxClient] = None
    ):
        super().__init__(
            config,
            vault_client=vault_client,
            code_forge_client=code_forge_client,
            metrics=metrics
        )
        self.argocd_client = argocd_client
        self.flux_client = flux_client
        self.argocd_url: Optional[str] = getattr(config, 'argocd_url', None)
        self.argocd_token: Optional[str] = getattr(config, 'argocd_token', None)

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa de DEPLOY com suporte a ArgoCD e Flux'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})

        tracer = get_tracer()
        with tracer.start_as_current_span('task_execution') as span:
            span.set_attribute('neural.hive.task_id', ticket_id)
            span.set_attribute('neural.hive.task_type', self.get_task_type())
            span.set_attribute('neural.hive.executor', self.__class__.__name__)

            self.log_execution(
                ticket_id,
                'deploy_started',
                parameters=parameters
            )

            namespace = parameters.get('namespace', 'default')
            deployment_name = parameters.get('deployment_name', f'deploy-{ticket_id[:8]}')
            image = parameters.get('image', 'latest')
            replicas = int(parameters.get('replicas', 1))
            sync_strategy = parameters.get('sync_strategy', 'auto')
            poll_timeout = parameters.get('timeout_seconds', 600)
            poll_interval = parameters.get('poll_interval', 5)
            provider = parameters.get('provider', 'argocd')

            # Fluxo ArgoCD com cliente dedicado
            if provider == 'argocd' and self.argocd_client:
                return await self._execute_argocd(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    sync_strategy=sync_strategy,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span
                )

            # Fluxo Flux com cliente dedicado
            if provider == 'flux' and self.flux_client:
                return await self._execute_flux(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span
                )

            # Fallback: ArgoCD legado via URL direta (backward compatibility)
            if self.argocd_url and getattr(self.config, 'argocd_enabled', False):
                return await self._execute_argocd_legacy(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    sync_strategy=sync_strategy,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span
                )

            # Fallback simulado
            return await self._execute_simulation(
                ticket_id=ticket_id,
                namespace=namespace,
                span=span
            )

    async def _execute_argocd(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        deployment_name: str,
        namespace: str,
        image: str,
        replicas: int,
        sync_strategy: str,
        poll_timeout: int,
        poll_interval: int,
        span
    ) -> Dict[str, Any]:
        '''Executa deploy via cliente ArgoCD dedicado'''
        self.log_execution(
            ticket_id,
            'deploy_argocd_started',
            deployment_name=deployment_name
        )

        start_time = asyncio.get_event_loop().time()

        try:
            helm_params = None
            if image or replicas:
                helm_params = {
                    'parameters': [
                        {'name': 'image.repository', 'value': image},
                        {'name': 'replicaCount', 'value': str(replicas)}
                    ]
                }

            sync_policy = None
            if sync_strategy == 'auto':
                sync_policy = SyncPolicy(
                    automated={'prune': True, 'selfHeal': True}
                )

            request = ApplicationCreateRequest(
                metadata=ApplicationMetadata(
                    name=deployment_name,
                    namespace=parameters.get('argocd_namespace', 'argocd'),
                    labels=parameters.get('labels'),
                    annotations=parameters.get('annotations')
                ),
                spec=ApplicationSpec(
                    project=parameters.get('project', 'default'),
                    source=ApplicationSource(
                        repoURL=parameters.get('repo_url', ''),
                        path=parameters.get('chart_path', '.'),
                        targetRevision=parameters.get('revision', 'HEAD'),
                        helm=helm_params
                    ),
                    destination=ApplicationDestination(
                        server=parameters.get('cluster_server', 'https://kubernetes.default.svc'),
                        namespace=namespace
                    ),
                    syncPolicy=sync_policy
                )
            )

            app_name = await self.argocd_client.create_application(request)

            if self.metrics and hasattr(self.metrics, 'argocd_api_calls_total'):
                self.metrics.argocd_api_calls_total.labels(method='create', status='success').inc()

            self.log_execution(
                ticket_id,
                'deploy_argocd_created',
                app_name=app_name
            )

            status = await self.argocd_client.wait_for_health(
                app_name=app_name,
                poll_interval=poll_interval,
                timeout=poll_timeout
            )

            if self.metrics and hasattr(self.metrics, 'argocd_api_calls_total'):
                self.metrics.argocd_api_calls_total.labels(method='get', status='success').inc()

            duration_seconds = asyncio.get_event_loop().time() - start_time

            result = {
                'success': True,
                'output': {
                    'deployment_id': app_name,
                    'status': status.health.status.lower(),
                    'sync_status': status.sync.status,
                    'replicas': replicas,
                    'namespace': namespace,
                    'revision': status.sync.revision
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'argocd',
                    'simulated': False,
                    'duration_seconds': duration_seconds
                },
                'logs': [
                    'Deployment started via ArgoCD client',
                    f'Application {app_name} created',
                    f'Health status: {status.health.status}',
                    f'Sync status: {status.sync.status}'
                ]
            }

            self.log_execution(
                ticket_id,
                'deploy_completed',
                deployment_id=app_name,
                status=status.health.status
            )

            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='success').inc()
            if self.metrics and hasattr(self.metrics, 'deploy_duration_seconds'):
                self.metrics.deploy_duration_seconds.labels(stage='argocd').observe(duration_seconds)

            span.set_attribute('neural.hive.execution_status', 'success')
            return result

        except ArgoCDTimeoutError as e:
            self.log_execution(
                ticket_id,
                'deploy_argocd_timeout',
                level='warning',
                deployment_id=deployment_name,
                error=str(e)
            )
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='timeout').inc()
            span.set_attribute('neural.hive.execution_status', 'timeout')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'timeout',
                    'replicas': replicas,
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'argocd',
                    'simulated': False,
                    'duration_seconds': poll_timeout
                },
                'logs': [
                    'Deployment started via ArgoCD client',
                    f'Timed out after {poll_timeout}s: {e}'
                ]
            }

        except ArgoCDAPIError as e:
            self.log_execution(
                ticket_id,
                'deploy_argocd_error',
                level='error',
                deployment_id=deployment_name,
                error=str(e),
                status_code=e.status_code
            )
            if self.metrics and hasattr(self.metrics, 'argocd_api_calls_total'):
                self.metrics.argocd_api_calls_total.labels(
                    method='unknown',
                    status='error'
                ).inc()
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='failed').inc()
            span.set_attribute('neural.hive.execution_status', 'failed')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'error',
                    'replicas': replicas,
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'argocd',
                    'simulated': False,
                    'error_code': e.status_code
                },
                'logs': [
                    'Deployment started via ArgoCD client',
                    f'Failed with error: {e}'
                ]
            }

        except Exception as exc:
            self.log_execution(
                ticket_id,
                'deploy_argocd_unexpected_error',
                level='error',
                deployment_id=deployment_name,
                error=str(exc)
            )
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='failed').inc()
            span.set_attribute('neural.hive.execution_status', 'failed')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'error',
                    'replicas': replicas,
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'argocd',
                    'simulated': False
                },
                'logs': [
                    'Deployment started via ArgoCD client',
                    f'Unexpected error: {exc}'
                ]
            }

    async def _execute_flux(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        deployment_name: str,
        namespace: str,
        poll_timeout: int,
        poll_interval: int,
        span
    ) -> Dict[str, Any]:
        '''Executa deploy via cliente Flux dedicado'''
        self.log_execution(
            ticket_id,
            'deploy_flux_started',
            deployment_name=deployment_name
        )

        start_time = asyncio.get_event_loop().time()

        try:
            request = KustomizationRequest(
                metadata=KustomizationMetadata(
                    name=deployment_name,
                    namespace=parameters.get('flux_namespace', 'flux-system'),
                    labels=parameters.get('labels'),
                    annotations=parameters.get('annotations')
                ),
                spec=KustomizationSpec(
                    interval=parameters.get('interval', '5m'),
                    path=parameters.get('path', './'),
                    prune=parameters.get('prune', True),
                    sourceRef=SourceReference(
                        kind=parameters.get('source_kind', 'GitRepository'),
                        name=parameters.get('source_name', ''),
                        namespace=parameters.get('source_namespace')
                    ),
                    targetNamespace=namespace,
                    timeout=parameters.get('apply_timeout'),
                    force=parameters.get('force', False),
                    wait=parameters.get('wait', True)
                )
            )

            kust_name = await self.flux_client.create_kustomization(request)

            if self.metrics and hasattr(self.metrics, 'flux_api_calls_total'):
                self.metrics.flux_api_calls_total.labels(method='create', status='success').inc()

            self.log_execution(
                ticket_id,
                'deploy_flux_created',
                kustomization_name=kust_name
            )

            status = await self.flux_client.wait_for_ready(
                name=kust_name,
                namespace=parameters.get('flux_namespace', 'flux-system'),
                poll_interval=poll_interval,
                timeout=poll_timeout
            )

            duration_seconds = asyncio.get_event_loop().time() - start_time

            result = {
                'success': True,
                'output': {
                    'deployment_id': kust_name,
                    'status': 'ready' if status.ready else 'not_ready',
                    'namespace': namespace,
                    'revision': status.lastAppliedRevision
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'flux',
                    'simulated': False,
                    'duration_seconds': duration_seconds
                },
                'logs': [
                    'Deployment started via Flux client',
                    f'Kustomization {kust_name} created',
                    f'Ready: {status.ready}',
                    f'Revision: {status.lastAppliedRevision}'
                ]
            }

            self.log_execution(
                ticket_id,
                'deploy_completed',
                deployment_id=kust_name,
                status='ready' if status.ready else 'not_ready'
            )

            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='success').inc()
            if self.metrics and hasattr(self.metrics, 'deploy_duration_seconds'):
                self.metrics.deploy_duration_seconds.labels(stage='flux').observe(duration_seconds)

            span.set_attribute('neural.hive.execution_status', 'success')
            return result

        except FluxTimeoutError as e:
            self.log_execution(
                ticket_id,
                'deploy_flux_timeout',
                level='warning',
                deployment_id=deployment_name,
                error=str(e)
            )
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='timeout').inc()
            span.set_attribute('neural.hive.execution_status', 'timeout')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'timeout',
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'flux',
                    'simulated': False,
                    'duration_seconds': poll_timeout
                },
                'logs': [
                    'Deployment started via Flux client',
                    f'Timed out after {poll_timeout}s: {e}'
                ]
            }

        except FluxAPIError as e:
            self.log_execution(
                ticket_id,
                'deploy_flux_error',
                level='error',
                deployment_id=deployment_name,
                error=str(e),
                status_code=e.status_code
            )
            if self.metrics and hasattr(self.metrics, 'flux_api_calls_total'):
                self.metrics.flux_api_calls_total.labels(
                    method='unknown',
                    status='error'
                ).inc()
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='failed').inc()
            span.set_attribute('neural.hive.execution_status', 'failed')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'error',
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'flux',
                    'simulated': False,
                    'error_code': e.status_code
                },
                'logs': [
                    'Deployment started via Flux client',
                    f'Failed with error: {e}'
                ]
            }

        except Exception as exc:
            self.log_execution(
                ticket_id,
                'deploy_flux_unexpected_error',
                level='error',
                deployment_id=deployment_name,
                error=str(exc)
            )
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='failed').inc()
            span.set_attribute('neural.hive.execution_status', 'failed')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'error',
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'flux',
                    'simulated': False
                },
                'logs': [
                    'Deployment started via Flux client',
                    f'Unexpected error: {exc}'
                ]
            }

    async def _execute_argocd_legacy(
        self,
        ticket_id: str,
        parameters: Dict[str, Any],
        deployment_name: str,
        namespace: str,
        image: str,
        replicas: int,
        sync_strategy: str,
        poll_timeout: int,
        poll_interval: int,
        span
    ) -> Dict[str, Any]:
        '''Fluxo legado de ArgoCD via httpx direto (backward compatibility)'''
        import httpx

        try:
            headers = {}
            if self.argocd_token:
                headers['Authorization'] = f'Bearer {self.argocd_token}'

            spec = {
                'project': 'default',
                'source': {
                    'repoURL': parameters.get('repo_url', ''),
                    'path': parameters.get('chart_path', '.'),
                    'targetRevision': parameters.get('revision', 'HEAD'),
                    'helm': {
                        'parameters': [
                            {'name': 'image.repository', 'value': image},
                            {'name': 'replicaCount', 'value': str(replicas)}
                        ]
                    }
                },
                'destination': {
                    'server': parameters.get('cluster_server', 'https://kubernetes.default.svc'),
                    'namespace': namespace
                }
            }

            if sync_strategy == 'auto':
                spec['syncPolicy'] = {
                    'automated': {'prune': True, 'selfHeal': True}
                }

            payload = {
                'metadata': {'name': deployment_name, 'namespace': namespace},
                'spec': spec
            }

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f'{self.argocd_url}/api/v1/applications',
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()

                if self.metrics and hasattr(self.metrics, 'argocd_api_calls_total'):
                    self.metrics.argocd_api_calls_total.labels(method='create', status='success').inc()

                attempts = int(poll_timeout / poll_interval)
                for attempt in range(attempts):
                    status_resp = await client.get(
                        f'{self.argocd_url}/api/v1/applications/{deployment_name}',
                        headers=headers
                    )
                    status_resp.raise_for_status()
                    if self.metrics and hasattr(self.metrics, 'argocd_api_calls_total'):
                        self.metrics.argocd_api_calls_total.labels(method='get', status='success').inc()
                    health = status_resp.json().get('status', {}).get('health', {}).get('status')
                    if health in ['Healthy', 'Deployed']:
                        duration_seconds = attempt * poll_interval
                        result = {
                            'success': True,
                            'output': {
                                'deployment_id': deployment_name,
                                'status': health.lower(),
                                'replicas': replicas,
                                'namespace': namespace
                            },
                            'metadata': {
                                'executor': 'DeployExecutor',
                                'provider': 'argocd_legacy',
                                'simulated': False,
                                'duration_seconds': duration_seconds
                            },
                            'logs': [
                                'Deployment started via ArgoCD (legacy)',
                                f'Application {deployment_name} created',
                                f'Health status: {health}'
                            ]
                        }
                        self.log_execution(
                            ticket_id,
                            'deploy_completed',
                            deployment_id=deployment_name,
                            status=health
                        )
                        if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                            self.metrics.deploy_tasks_executed_total.labels(status='success').inc()
                        if self.metrics and hasattr(self.metrics, 'deploy_duration_seconds'):
                            self.metrics.deploy_duration_seconds.labels(stage='health_check').observe(duration_seconds)
                        span.set_attribute('neural.hive.execution_status', 'success')
                        return result
                    await asyncio.sleep(poll_interval)

            self.log_execution(
                ticket_id,
                'deploy_argocd_timeout',
                level='warning',
                deployment_id=deployment_name
            )
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='timeout').inc()
            span.set_attribute('neural.hive.execution_status', 'timeout')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'timeout',
                    'replicas': replicas,
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'argocd_legacy',
                    'simulated': False,
                    'duration_seconds': poll_timeout
                },
                'logs': [
                    'Deployment started via ArgoCD (legacy)',
                    f'Timed out after {poll_timeout}s'
                ]
            }
        except Exception as exc:
            self.log_execution(
                ticket_id,
                'deploy_argocd_error',
                level='error',
                error=str(exc)
            )
            if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
                self.metrics.deploy_tasks_executed_total.labels(status='failed').inc()
            span.set_attribute('neural.hive.execution_status', 'failed')
            return {
                'success': False,
                'output': {
                    'deployment_id': deployment_name,
                    'status': 'error',
                    'replicas': replicas,
                    'namespace': namespace
                },
                'metadata': {
                    'executor': 'DeployExecutor',
                    'provider': 'argocd_legacy',
                    'simulated': False
                },
                'logs': [
                    'Deployment started via ArgoCD (legacy)',
                    f'Failed with error: {exc}'
                ]
            }

    async def _execute_simulation(
        self,
        ticket_id: str,
        namespace: str,
        span
    ) -> Dict[str, Any]:
        '''Fallback simulado quando nenhum provider esta disponivel'''
        self.log_execution(
            ticket_id,
            'deploy_fallback_simulation',
            reason='No GitOps provider available'
        )

        delay = random.uniform(3, 7)
        await asyncio.sleep(delay)

        result = {
            'success': True,
            'output': {
                'deployment_id': f'stub-deploy-{ticket_id[:8]}',
                'status': 'deployed',
                'replicas': 3,
                'namespace': namespace
            },
            'metadata': {
                'executor': 'DeployExecutor',
                'provider': 'simulation',
                'simulated': True,
                'duration_seconds': delay
            },
            'logs': [
                'Deployment started (simulation)',
                f'Simulated deployment for {delay:.2f}s',
                'Health checks passed',
                'Deployment completed successfully'
            ]
        }

        self.log_execution(
            ticket_id,
            'deploy_completed',
            duration_seconds=delay,
            deployment_id=result['output']['deployment_id']
        )

        if self.metrics and hasattr(self.metrics, 'deploy_tasks_executed_total'):
            self.metrics.deploy_tasks_executed_total.labels(status='success').inc()
        if self.metrics and hasattr(self.metrics, 'deploy_duration_seconds'):
            self.metrics.deploy_duration_seconds.labels(stage='simulated').observe(delay)

        span.set_attribute('neural.hive.execution_status', 'success')
        return result
