"""
Cliente ArgoCD para gerenciamento de aplicacoes GitOps.

Este cliente implementa integracao com ArgoCD API para deploy de aplicacoes
seguindo o padrao estabelecido pelo CodeForgeClient.
"""

import asyncio
import httpx
import structlog
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class ArgoCDAPIError(Exception):
    """Erro de chamada a API do ArgoCD."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ArgoCDTimeoutError(Exception):
    """Timeout aguardando health check do ArgoCD."""
    pass


class ApplicationSource(BaseModel):
    """Fonte da aplicacao ArgoCD."""
    repoURL: str
    path: str = '.'
    targetRevision: str = 'HEAD'
    helm: Optional[Dict[str, Any]] = None
    kustomize: Optional[Dict[str, Any]] = None


class ApplicationDestination(BaseModel):
    """Destino da aplicacao ArgoCD."""
    server: str = 'https://kubernetes.default.svc'
    namespace: str = 'default'


class SyncPolicy(BaseModel):
    """Politica de sincronizacao ArgoCD."""
    automated: Optional[Dict[str, bool]] = None
    syncOptions: Optional[List[str]] = None


class ApplicationSpec(BaseModel):
    """Spec da aplicacao ArgoCD."""
    project: str = 'default'
    source: ApplicationSource
    destination: ApplicationDestination
    syncPolicy: Optional[SyncPolicy] = None


class ApplicationMetadata(BaseModel):
    """Metadata da aplicacao ArgoCD."""
    name: str
    namespace: str = 'argocd'
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None


class ApplicationCreateRequest(BaseModel):
    """Request para criacao de aplicacao ArgoCD."""
    metadata: ApplicationMetadata
    spec: ApplicationSpec


class HealthStatus(BaseModel):
    """Status de health da aplicacao."""
    status: str = 'Unknown'
    message: Optional[str] = None


class SyncStatus(BaseModel):
    """Status de sync da aplicacao."""
    status: str = 'Unknown'
    revision: Optional[str] = None


class OperationState(BaseModel):
    """Estado da operacao atual."""
    phase: str = 'Unknown'
    message: Optional[str] = None
    startedAt: Optional[str] = None
    finishedAt: Optional[str] = None


class ApplicationStatus(BaseModel):
    """Status da aplicacao ArgoCD."""
    name: str
    health: HealthStatus = Field(default_factory=HealthStatus)
    sync: SyncStatus = Field(default_factory=SyncStatus)
    operationState: Optional[OperationState] = None
    resources: Optional[List[Dict[str, Any]]] = None


class ApplicationResponse(BaseModel):
    """Resposta completa de aplicacao ArgoCD."""
    metadata: Dict[str, Any]
    spec: Dict[str, Any]
    status: Optional[Dict[str, Any]] = None


class ArgoCDClient:
    """Cliente para API do ArgoCD."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = 600,
        verify_ssl: bool = True,
    ):
        """
        Inicializa cliente ArgoCD.

        Args:
            base_url: URL base do ArgoCD (ex: https://argocd.example.com)
            token: Token de autenticacao Bearer
            timeout: Timeout padrao para requisicoes em segundos
            verify_ssl: Verificar certificado SSL
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            verify=verify_ssl
        )
        self.logger = logger.bind(service='argocd_client')

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers para requisicoes."""
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()
        self.logger.info('argocd_client_closed')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_application(self, request: ApplicationCreateRequest) -> str:
        """
        Cria aplicacao no ArgoCD.

        Args:
            request: Dados da aplicacao

        Returns:
            Nome da aplicacao criada

        Raises:
            ArgoCDAPIError: Erro na API
        """
        with tracer.start_as_current_span('argocd.create_application') as span:
            app_name = request.metadata.name
            span.set_attribute('argocd.app_name', app_name)
            span.set_attribute('argocd.namespace', request.metadata.namespace)

            self.logger.info(
                'argocd_create_application',
                app_name=app_name,
                namespace=request.spec.destination.namespace
            )

            try:
                response = await self.client.post(
                    f'{self.base_url}/api/v1/applications',
                    json=request.model_dump(exclude_none=True),
                    headers=self._get_headers()
                )
                response.raise_for_status()

                self.logger.info('argocd_application_created', app_name=app_name)
                return app_name

            except httpx.HTTPStatusError as e:
                self.logger.error(
                    'argocd_create_failed',
                    app_name=app_name,
                    status_code=e.response.status_code,
                    error=str(e)
                )
                raise ArgoCDAPIError(
                    f'Falha ao criar aplicacao {app_name}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException as e:
                self.logger.error('argocd_create_timeout', app_name=app_name)
                raise ArgoCDTimeoutError(f'Timeout ao criar aplicacao {app_name}')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_application_status(self, app_name: str) -> ApplicationStatus:
        """
        Obtem status da aplicacao.

        Args:
            app_name: Nome da aplicacao

        Returns:
            Status da aplicacao

        Raises:
            ArgoCDAPIError: Erro na API
        """
        with tracer.start_as_current_span('argocd.get_application_status') as span:
            span.set_attribute('argocd.app_name', app_name)

            try:
                response = await self.client.get(
                    f'{self.base_url}/api/v1/applications/{app_name}',
                    headers=self._get_headers()
                )
                response.raise_for_status()

                data = response.json()
                status_data = data.get('status', {})
                health_data = status_data.get('health', {})
                sync_data = status_data.get('sync', {})
                operation_data = status_data.get('operationState')

                return ApplicationStatus(
                    name=app_name,
                    health=HealthStatus(
                        status=health_data.get('status', 'Unknown'),
                        message=health_data.get('message')
                    ),
                    sync=SyncStatus(
                        status=sync_data.get('status', 'Unknown'),
                        revision=sync_data.get('revision')
                    ),
                    operationState=OperationState(**operation_data) if operation_data else None,
                    resources=status_data.get('resources')
                )

            except httpx.HTTPStatusError as e:
                self.logger.error(
                    'argocd_get_status_failed',
                    app_name=app_name,
                    status_code=e.response.status_code
                )
                raise ArgoCDAPIError(
                    f'Falha ao obter status de {app_name}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise ArgoCDTimeoutError(f'Timeout ao obter status de {app_name}')

    async def wait_for_health(
        self,
        app_name: str,
        poll_interval: int = 5,
        timeout: int = 600,
        healthy_statuses: Optional[List[str]] = None
    ) -> ApplicationStatus:
        """
        Aguarda aplicacao ficar healthy via polling.

        Args:
            app_name: Nome da aplicacao
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos
            healthy_statuses: Lista de status considerados healthy

        Returns:
            Status final da aplicacao

        Raises:
            ArgoCDTimeoutError: Timeout aguardando health
        """
        with tracer.start_as_current_span('argocd.wait_for_health') as span:
            span.set_attribute('argocd.app_name', app_name)
            span.set_attribute('argocd.timeout', timeout)

            if healthy_statuses is None:
                healthy_statuses = ['Healthy', 'Degraded']

            self.logger.info(
                'argocd_waiting_for_health',
                app_name=app_name,
                timeout=timeout
            )

            start_time = asyncio.get_event_loop().time()
            last_status = None

            while True:
                status = await self.get_application_status(app_name)
                last_status = status

                self.logger.debug(
                    'argocd_health_check',
                    app_name=app_name,
                    health=status.health.status,
                    sync=status.sync.status
                )

                if status.health.status in healthy_statuses:
                    self.logger.info(
                        'argocd_application_healthy',
                        app_name=app_name,
                        health=status.health.status
                    )
                    return status

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    self.logger.warning(
                        'argocd_health_timeout',
                        app_name=app_name,
                        last_health=status.health.status,
                        elapsed=elapsed
                    )
                    raise ArgoCDTimeoutError(
                        f'Timeout aguardando health de {app_name} '
                        f'(ultimo status: {status.health.status})'
                    )

                await asyncio.sleep(poll_interval)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def sync_application(
        self,
        app_name: str,
        prune: bool = False,
        dry_run: bool = False,
        revision: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trigger sync manual da aplicacao.

        Args:
            app_name: Nome da aplicacao
            prune: Remover recursos orfaos
            dry_run: Executar em modo dry-run
            revision: Revisao especifica para sync

        Returns:
            Resultado do sync

        Raises:
            ArgoCDAPIError: Erro na API
        """
        with tracer.start_as_current_span('argocd.sync_application') as span:
            span.set_attribute('argocd.app_name', app_name)
            span.set_attribute('argocd.prune', prune)
            span.set_attribute('argocd.dry_run', dry_run)

            self.logger.info(
                'argocd_sync_application',
                app_name=app_name,
                prune=prune,
                dry_run=dry_run
            )

            payload: Dict[str, Any] = {
                'prune': prune,
                'dryRun': dry_run
            }
            if revision:
                payload['revision'] = revision

            try:
                response = await self.client.post(
                    f'{self.base_url}/api/v1/applications/{app_name}/sync',
                    json=payload,
                    headers=self._get_headers()
                )
                response.raise_for_status()

                result = response.json()
                self.logger.info('argocd_sync_triggered', app_name=app_name)
                return result

            except httpx.HTTPStatusError as e:
                self.logger.error(
                    'argocd_sync_failed',
                    app_name=app_name,
                    status_code=e.response.status_code
                )
                raise ArgoCDAPIError(
                    f'Falha ao sync {app_name}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise ArgoCDTimeoutError(f'Timeout ao sync {app_name}')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def delete_application(
        self,
        app_name: str,
        cascade: bool = True
    ) -> bool:
        """
        Deleta aplicacao do ArgoCD.

        Args:
            app_name: Nome da aplicacao
            cascade: Deletar recursos gerenciados (cascade delete)

        Returns:
            True se deletado com sucesso

        Raises:
            ArgoCDAPIError: Erro na API
        """
        with tracer.start_as_current_span('argocd.delete_application') as span:
            span.set_attribute('argocd.app_name', app_name)
            span.set_attribute('argocd.cascade', cascade)

            self.logger.info(
                'argocd_delete_application',
                app_name=app_name,
                cascade=cascade
            )

            try:
                params = {'cascade': str(cascade).lower()}
                response = await self.client.delete(
                    f'{self.base_url}/api/v1/applications/{app_name}',
                    params=params,
                    headers=self._get_headers()
                )
                response.raise_for_status()

                self.logger.info('argocd_application_deleted', app_name=app_name)
                return True

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    self.logger.warning(
                        'argocd_application_not_found',
                        app_name=app_name
                    )
                    return True
                self.logger.error(
                    'argocd_delete_failed',
                    app_name=app_name,
                    status_code=e.response.status_code
                )
                raise ArgoCDAPIError(
                    f'Falha ao deletar {app_name}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise ArgoCDTimeoutError(f'Timeout ao deletar {app_name}')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_application(self, app_name: str) -> ApplicationResponse:
        """
        Obtem dados completos da aplicacao.

        Args:
            app_name: Nome da aplicacao

        Returns:
            Dados completos da aplicacao

        Raises:
            ArgoCDAPIError: Erro na API
        """
        with tracer.start_as_current_span('argocd.get_application') as span:
            span.set_attribute('argocd.app_name', app_name)

            try:
                response = await self.client.get(
                    f'{self.base_url}/api/v1/applications/{app_name}',
                    headers=self._get_headers()
                )
                response.raise_for_status()

                data = response.json()
                return ApplicationResponse(
                    metadata=data.get('metadata', {}),
                    spec=data.get('spec', {}),
                    status=data.get('status')
                )

            except httpx.HTTPStatusError as e:
                raise ArgoCDAPIError(
                    f'Falha ao obter {app_name}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise ArgoCDTimeoutError(f'Timeout ao obter {app_name}')

    async def list_applications(
        self,
        project: Optional[str] = None,
        selector: Optional[str] = None
    ) -> List[ApplicationResponse]:
        """
        Lista aplicacoes do ArgoCD.

        Args:
            project: Filtrar por projeto
            selector: Label selector

        Returns:
            Lista de aplicacoes

        Raises:
            ArgoCDAPIError: Erro na API
        """
        with tracer.start_as_current_span('argocd.list_applications') as span:
            params = {}
            if project:
                params['project'] = project
                span.set_attribute('argocd.project', project)
            if selector:
                params['selector'] = selector
                span.set_attribute('argocd.selector', selector)

            try:
                response = await self.client.get(
                    f'{self.base_url}/api/v1/applications',
                    params=params,
                    headers=self._get_headers()
                )
                response.raise_for_status()

                data = response.json()
                items = data.get('items', [])

                return [
                    ApplicationResponse(
                        metadata=item.get('metadata', {}),
                        spec=item.get('spec', {}),
                        status=item.get('status')
                    )
                    for item in items
                ]

            except httpx.HTTPStatusError as e:
                raise ArgoCDAPIError(
                    f'Falha ao listar aplicacoes: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise ArgoCDTimeoutError('Timeout ao listar aplicacoes')
