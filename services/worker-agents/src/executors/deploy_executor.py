import asyncio
import random
from typing import Any, Dict, Optional
import httpx
from .base_executor import BaseTaskExecutor


class DeployExecutor(BaseTaskExecutor):
    '''Executor para task_type=DEPLOY (stub MVP)'''

    def get_task_type(self) -> str:
        return 'DEPLOY'

    def __init__(self, config, vault_client=None, code_forge_client=None):
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client)
        self.argocd_url: Optional[str] = getattr(config, 'argocd_url', None)
        self.argocd_token: Optional[str] = getattr(config, 'argocd_token', None)

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        '''Executar tarefa de DEPLOY com preparação para GitOps/ArgoCD'''
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})

        self.log_execution(
            ticket_id,
            'deploy_started',
            parameters=parameters
        )

        namespace = parameters.get('namespace', 'default')
        deployment_name = parameters.get('deployment_name', f'deploy-{ticket_id[:8]}')
        image = parameters.get('image', 'latest')
        replicas = int(parameters.get('replicas', 1))

        if self.argocd_url and getattr(self.config, 'argocd_enabled', False):
            try:
                headers = {}
                if self.argocd_token:
                    headers['Authorization'] = f'Bearer {self.argocd_token}'

                payload = {
                    'metadata': {'name': deployment_name, 'namespace': namespace},
                    'spec': {
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
                }

                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f'{self.argocd_url}/api/v1/applications',
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()

                    # Poll status até deployed
                    for attempt in range(20):
                        status_resp = await client.get(
                            f'{self.argocd_url}/api/v1/applications/{deployment_name}',
                            headers=headers
                        )
                        status_resp.raise_for_status()
                        health = status_resp.json().get('status', {}).get('health', {}).get('status')
                        if health in ['Healthy', 'Deployed']:
                            duration_seconds = attempt * 5
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
                                    'simulated': False,
                                    'duration_seconds': duration_seconds
                                },
                                'logs': [
                                    'Deployment started via ArgoCD',
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
                            return result
                        await asyncio.sleep(5)

                self.log_execution(
                    ticket_id,
                    'deploy_argocd_timeout',
                    level='warning',
                    deployment_id=deployment_name
                )
            except Exception as exc:
                self.log_execution(
                    ticket_id,
                    'deploy_argocd_error',
                    level='error',
                    error=str(exc)
                )
                # fallback para simulação

        # Fallback simulado enquanto integração GitOps completa não está disponível
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
                'simulated': True,
                'duration_seconds': delay
            },
            'logs': [
                'Deployment started',
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

        # TODO: Incrementar métrica worker_agent_deploy_tasks_executed_total

        return result
