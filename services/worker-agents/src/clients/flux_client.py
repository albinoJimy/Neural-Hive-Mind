"""
Cliente Flux CD para gerenciamento de Kustomizations GitOps.

Este cliente implementa integracao com Flux via Kubernetes API
para deploy de aplicacoes usando Kustomization CRDs.
"""

import asyncio
import structlog
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class FluxAPIError(Exception):
    """Erro de chamada a API do Flux/Kubernetes."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class FluxTimeoutError(Exception):
    """Timeout aguardando Kustomization ficar ready."""
    pass


class SourceReference(BaseModel):
    """Referencia a fonte GitRepository ou OCIRepository."""
    kind: str = 'GitRepository'
    name: str
    namespace: Optional[str] = None


class KustomizationSpec(BaseModel):
    """Spec do Kustomization CRD."""
    interval: str = '5m'
    path: str = './'
    prune: bool = True
    sourceRef: SourceReference
    targetNamespace: Optional[str] = None
    timeout: Optional[str] = None
    force: bool = False
    wait: bool = True
    healthChecks: Optional[List[Dict[str, Any]]] = None


class KustomizationMetadata(BaseModel):
    """Metadata do Kustomization."""
    name: str
    namespace: str = 'flux-system'
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None


class KustomizationRequest(BaseModel):
    """Request para criacao de Kustomization."""
    metadata: KustomizationMetadata
    spec: KustomizationSpec


class Condition(BaseModel):
    """Condition do status."""
    type: str
    status: str
    reason: Optional[str] = None
    message: Optional[str] = None
    lastTransitionTime: Optional[str] = None


class KustomizationStatus(BaseModel):
    """Status do Kustomization."""
    name: str
    namespace: str = 'flux-system'
    ready: bool = False
    conditions: List[Condition] = Field(default_factory=list)
    lastAppliedRevision: Optional[str] = None
    lastAttemptedRevision: Optional[str] = None


class FluxClient:
    """Cliente para Flux CD via Kubernetes API."""

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        namespace: str = 'flux-system',
        timeout: int = 600,
    ):
        """
        Inicializa cliente Flux.

        Args:
            kubeconfig_path: Caminho para kubeconfig (None para in-cluster)
            namespace: Namespace padrao para Kustomizations
            timeout: Timeout padrao para operacoes em segundos
        """
        self.kubeconfig_path = kubeconfig_path
        self.default_namespace = namespace
        self.timeout = timeout
        self._client = None
        self._api = None
        self.logger = logger.bind(service='flux_client')
        self._initialized = False

    async def initialize(self):
        """Inicializa cliente Kubernetes."""
        if self._initialized:
            return

        try:
            from kubernetes_asyncio import client, config
            from kubernetes_asyncio.client import ApiClient

            if self.kubeconfig_path:
                await config.load_kube_config(config_file=self.kubeconfig_path)
            else:
                config.load_incluster_config()

            self._client = ApiClient()
            self._api = client.CustomObjectsApi(self._client)
            self._initialized = True
            self.logger.info('flux_client_initialized')

        except ImportError:
            self.logger.error('kubernetes_asyncio_not_installed')
            raise FluxAPIError(
                'kubernetes-asyncio nao instalado. '
                'Execute: pip install kubernetes-asyncio'
            )
        except Exception as e:
            self.logger.error('flux_client_init_failed', error=str(e))
            raise FluxAPIError(f'Falha ao inicializar cliente Flux: {e}')

    async def close(self):
        """Fecha cliente Kubernetes."""
        if self._client:
            await self._client.close()
            self._client = None
            self._api = None
            self._initialized = False
        self.logger.info('flux_client_closed')

    def _ensure_initialized(self):
        """Verifica se cliente foi inicializado."""
        if not self._initialized:
            raise FluxAPIError('Cliente Flux nao inicializado. Chame initialize() primeiro.')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_kustomization(self, request: KustomizationRequest) -> str:
        """
        Cria Kustomization no cluster.

        Args:
            request: Dados do Kustomization

        Returns:
            Nome do Kustomization criado

        Raises:
            FluxAPIError: Erro na API
        """
        with tracer.start_as_current_span('flux.create_kustomization') as span:
            self._ensure_initialized()

            name = request.metadata.name
            namespace = request.metadata.namespace
            span.set_attribute('flux.kustomization_name', name)
            span.set_attribute('flux.namespace', namespace)

            self.logger.info(
                'flux_create_kustomization',
                name=name,
                namespace=namespace
            )

            body = {
                'apiVersion': 'kustomize.toolkit.fluxcd.io/v1',
                'kind': 'Kustomization',
                'metadata': request.metadata.model_dump(exclude_none=True),
                'spec': request.spec.model_dump(exclude_none=True)
            }

            try:
                await self._api.create_namespaced_custom_object(
                    group='kustomize.toolkit.fluxcd.io',
                    version='v1',
                    namespace=namespace,
                    plural='kustomizations',
                    body=body
                )

                self.logger.info('flux_kustomization_created', name=name)
                return name

            except Exception as e:
                error_msg = str(e)
                status_code = getattr(e, 'status', None)

                self.logger.error(
                    'flux_create_failed',
                    name=name,
                    error=error_msg,
                    status_code=status_code
                )
                raise FluxAPIError(
                    f'Falha ao criar Kustomization {name}: {error_msg}',
                    status_code=status_code
                )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_kustomization_status(
        self,
        name: str,
        namespace: Optional[str] = None
    ) -> KustomizationStatus:
        """
        Obtem status do Kustomization.

        Args:
            name: Nome do Kustomization
            namespace: Namespace (usa default se nao especificado)

        Returns:
            Status do Kustomization

        Raises:
            FluxAPIError: Erro na API
        """
        with tracer.start_as_current_span('flux.get_kustomization_status') as span:
            self._ensure_initialized()

            ns = namespace or self.default_namespace
            span.set_attribute('flux.kustomization_name', name)
            span.set_attribute('flux.namespace', ns)

            try:
                result = await self._api.get_namespaced_custom_object(
                    group='kustomize.toolkit.fluxcd.io',
                    version='v1',
                    namespace=ns,
                    plural='kustomizations',
                    name=name
                )

                status_data = result.get('status', {})
                conditions_data = status_data.get('conditions', [])

                conditions = [
                    Condition(
                        type=c.get('type', 'Unknown'),
                        status=c.get('status', 'Unknown'),
                        reason=c.get('reason'),
                        message=c.get('message'),
                        lastTransitionTime=c.get('lastTransitionTime')
                    )
                    for c in conditions_data
                ]

                ready = any(
                    c.type == 'Ready' and c.status == 'True'
                    for c in conditions
                )

                return KustomizationStatus(
                    name=name,
                    namespace=ns,
                    ready=ready,
                    conditions=conditions,
                    lastAppliedRevision=status_data.get('lastAppliedRevision'),
                    lastAttemptedRevision=status_data.get('lastAttemptedRevision')
                )

            except Exception as e:
                error_msg = str(e)
                status_code = getattr(e, 'status', None)

                self.logger.error(
                    'flux_get_status_failed',
                    name=name,
                    error=error_msg
                )
                raise FluxAPIError(
                    f'Falha ao obter status de {name}: {error_msg}',
                    status_code=status_code
                )

    async def wait_for_ready(
        self,
        name: str,
        namespace: Optional[str] = None,
        poll_interval: int = 5,
        timeout: int = 600
    ) -> KustomizationStatus:
        """
        Aguarda Kustomization ficar ready via polling.

        Args:
            name: Nome do Kustomization
            namespace: Namespace
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos

        Returns:
            Status final do Kustomization

        Raises:
            FluxTimeoutError: Timeout aguardando ready
        """
        with tracer.start_as_current_span('flux.wait_for_ready') as span:
            ns = namespace or self.default_namespace
            span.set_attribute('flux.kustomization_name', name)
            span.set_attribute('flux.namespace', ns)
            span.set_attribute('flux.timeout', timeout)

            self.logger.info(
                'flux_waiting_for_ready',
                name=name,
                namespace=ns,
                timeout=timeout
            )

            start_time = asyncio.get_event_loop().time()

            while True:
                status = await self.get_kustomization_status(name, ns)

                self.logger.debug(
                    'flux_ready_check',
                    name=name,
                    ready=status.ready,
                    conditions_count=len(status.conditions)
                )

                if status.ready:
                    self.logger.info(
                        'flux_kustomization_ready',
                        name=name,
                        revision=status.lastAppliedRevision
                    )
                    return status

                failed_condition = next(
                    (c for c in status.conditions
                     if c.type == 'Ready' and c.status == 'False'),
                    None
                )
                if failed_condition and 'failed' in (failed_condition.reason or '').lower():
                    raise FluxAPIError(
                        f'Kustomization {name} falhou: {failed_condition.message}'
                    )

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    self.logger.warning(
                        'flux_ready_timeout',
                        name=name,
                        ready=status.ready,
                        elapsed=elapsed
                    )
                    raise FluxTimeoutError(
                        f'Timeout aguardando {name} ficar ready '
                        f'(ultimo status: ready={status.ready})'
                    )

                await asyncio.sleep(poll_interval)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def reconcile_kustomization(
        self,
        name: str,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Forca reconciliacao do Kustomization.

        Args:
            name: Nome do Kustomization
            namespace: Namespace

        Returns:
            Resultado da reconciliacao

        Raises:
            FluxAPIError: Erro na API
        """
        with tracer.start_as_current_span('flux.reconcile_kustomization') as span:
            self._ensure_initialized()

            ns = namespace or self.default_namespace
            span.set_attribute('flux.kustomization_name', name)
            span.set_attribute('flux.namespace', ns)

            self.logger.info(
                'flux_reconcile_kustomization',
                name=name,
                namespace=ns
            )

            try:
                import datetime
                annotation_value = datetime.datetime.utcnow().isoformat() + 'Z'

                patch_body = {
                    'metadata': {
                        'annotations': {
                            'reconcile.fluxcd.io/requestedAt': annotation_value
                        }
                    }
                }

                result = await self._api.patch_namespaced_custom_object(
                    group='kustomize.toolkit.fluxcd.io',
                    version='v1',
                    namespace=ns,
                    plural='kustomizations',
                    name=name,
                    body=patch_body
                )

                self.logger.info('flux_reconcile_triggered', name=name)
                return {'name': name, 'reconcileRequestedAt': annotation_value}

            except Exception as e:
                error_msg = str(e)
                status_code = getattr(e, 'status', None)

                self.logger.error(
                    'flux_reconcile_failed',
                    name=name,
                    error=error_msg
                )
                raise FluxAPIError(
                    f'Falha ao reconciliar {name}: {error_msg}',
                    status_code=status_code
                )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def delete_kustomization(
        self,
        name: str,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Deleta Kustomization do cluster.

        Args:
            name: Nome do Kustomization
            namespace: Namespace

        Returns:
            True se deletado com sucesso

        Raises:
            FluxAPIError: Erro na API
        """
        with tracer.start_as_current_span('flux.delete_kustomization') as span:
            self._ensure_initialized()

            ns = namespace or self.default_namespace
            span.set_attribute('flux.kustomization_name', name)
            span.set_attribute('flux.namespace', ns)

            self.logger.info(
                'flux_delete_kustomization',
                name=name,
                namespace=ns
            )

            try:
                await self._api.delete_namespaced_custom_object(
                    group='kustomize.toolkit.fluxcd.io',
                    version='v1',
                    namespace=ns,
                    plural='kustomizations',
                    name=name
                )

                self.logger.info('flux_kustomization_deleted', name=name)
                return True

            except Exception as e:
                error_msg = str(e)
                status_code = getattr(e, 'status', None)

                if status_code == 404:
                    self.logger.warning('flux_kustomization_not_found', name=name)
                    return True

                self.logger.error(
                    'flux_delete_failed',
                    name=name,
                    error=error_msg
                )
                raise FluxAPIError(
                    f'Falha ao deletar {name}: {error_msg}',
                    status_code=status_code
                )

    async def list_kustomizations(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None
    ) -> List[KustomizationStatus]:
        """
        Lista Kustomizations no cluster.

        Args:
            namespace: Namespace (None para todos)
            label_selector: Label selector

        Returns:
            Lista de status dos Kustomizations

        Raises:
            FluxAPIError: Erro na API
        """
        with tracer.start_as_current_span('flux.list_kustomizations') as span:
            self._ensure_initialized()

            if namespace:
                span.set_attribute('flux.namespace', namespace)
            if label_selector:
                span.set_attribute('flux.label_selector', label_selector)

            try:
                kwargs = {
                    'group': 'kustomize.toolkit.fluxcd.io',
                    'version': 'v1',
                    'plural': 'kustomizations'
                }
                if label_selector:
                    kwargs['label_selector'] = label_selector

                if namespace:
                    result = await self._api.list_namespaced_custom_object(
                        namespace=namespace,
                        **kwargs
                    )
                else:
                    result = await self._api.list_cluster_custom_object(**kwargs)

                items = result.get('items', [])
                kustomizations = []

                for item in items:
                    metadata = item.get('metadata', {})
                    status_data = item.get('status', {})
                    conditions_data = status_data.get('conditions', [])

                    conditions = [
                        Condition(
                            type=c.get('type', 'Unknown'),
                            status=c.get('status', 'Unknown'),
                            reason=c.get('reason'),
                            message=c.get('message'),
                            lastTransitionTime=c.get('lastTransitionTime')
                        )
                        for c in conditions_data
                    ]

                    ready = any(
                        c.type == 'Ready' and c.status == 'True'
                        for c in conditions
                    )

                    kustomizations.append(KustomizationStatus(
                        name=metadata.get('name', ''),
                        namespace=metadata.get('namespace', 'flux-system'),
                        ready=ready,
                        conditions=conditions,
                        lastAppliedRevision=status_data.get('lastAppliedRevision'),
                        lastAttemptedRevision=status_data.get('lastAttemptedRevision')
                    ))

                return kustomizations

            except Exception as e:
                error_msg = str(e)
                status_code = getattr(e, 'status', None)

                self.logger.error(
                    'flux_list_failed',
                    error=error_msg
                )
                raise FluxAPIError(
                    f'Falha ao listar Kustomizations: {error_msg}',
                    status_code=status_code
                )
