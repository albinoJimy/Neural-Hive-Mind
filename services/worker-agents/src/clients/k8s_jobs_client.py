"""
Cliente Kubernetes Jobs para execução de comandos como Jobs K8s.

Este cliente implementa execução isolada de comandos via Kubernetes Jobs API,
com resource limits, security context e cleanup automático.
"""

import asyncio
import structlog
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field
from enum import Enum
import uuid


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class K8sJobError(Exception):
    """Erro de execução de Job Kubernetes."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class K8sJobTimeoutError(Exception):
    """Timeout aguardando Job Kubernetes."""
    pass


class RestartPolicy(str, Enum):
    """Políticas de restart para containers."""
    NEVER = 'Never'
    ON_FAILURE = 'OnFailure'


class K8sResourceRequirements(BaseModel):
    """Requisitos de recursos para container K8s."""
    cpu_request: str = Field(default='100m', description='CPU request (ex: 100m, 1)')
    cpu_limit: str = Field(default='1000m', description='CPU limit (ex: 1000m, 2)')
    memory_request: str = Field(default='128Mi', description='Memory request (ex: 128Mi, 1Gi)')
    memory_limit: str = Field(default='512Mi', description='Memory limit (ex: 512Mi, 2Gi)')


class K8sSecurityContext(BaseModel):
    """Security context para Pod/Container."""
    run_as_non_root: bool = Field(default=True, description='Executar como non-root')
    run_as_user: Optional[int] = Field(default=1000, description='UID para execução')
    run_as_group: Optional[int] = Field(default=1000, description='GID para execução')
    read_only_root_filesystem: bool = Field(default=True, description='Filesystem read-only')
    allow_privilege_escalation: bool = Field(default=False, description='Permitir escalação de privilégios')


class K8sEnvVar(BaseModel):
    """Variável de ambiente para container."""
    name: str
    value: Optional[str] = None
    value_from: Optional[Dict[str, Any]] = None


class K8sJobRequest(BaseModel):
    """Request para criação de Job Kubernetes."""
    name: Optional[str] = Field(default=None, description='Nome do Job (gerado se não fornecido)')
    namespace: str = Field(default='neural-hive-execution', description='Namespace do Job')
    image: str = Field(..., description='Imagem do container')
    command: List[str] = Field(..., description='Comando a executar')
    args: Optional[List[str]] = Field(default=None, description='Argumentos do comando')
    env_vars: Optional[Dict[str, str]] = Field(default=None, description='Variáveis de ambiente')
    resource_limits: K8sResourceRequirements = Field(default_factory=K8sResourceRequirements)
    timeout_seconds: int = Field(default=600, description='Timeout em segundos')
    restart_policy: RestartPolicy = Field(default=RestartPolicy.NEVER)
    backoff_limit: int = Field(default=0, description='Número de retries do Job')
    service_account: Optional[str] = Field(default=None, description='ServiceAccount a usar')
    security_context: K8sSecurityContext = Field(default_factory=K8sSecurityContext)
    labels: Optional[Dict[str, str]] = Field(default=None, description='Labels do Job')
    annotations: Optional[Dict[str, str]] = Field(default=None, description='Annotations do Job')
    ttl_seconds_after_finished: int = Field(default=300, description='TTL para cleanup automático')
    active_deadline_seconds: Optional[int] = Field(default=None, description='Deadline do Job')


class K8sJobStatus(str, Enum):
    """Status do Job Kubernetes."""
    PENDING = 'Pending'
    RUNNING = 'Running'
    SUCCEEDED = 'Succeeded'
    FAILED = 'Failed'
    UNKNOWN = 'Unknown'


class K8sJobResult(BaseModel):
    """Resultado da execução de Job Kubernetes."""
    job_name: str
    pod_name: Optional[str] = None
    namespace: str
    status: K8sJobStatus
    exit_code: Optional[int] = None
    logs: str = ''
    duration_ms: int
    resource_usage: Optional[Dict[str, Any]] = None
    start_time: Optional[str] = None
    completion_time: Optional[str] = None
    conditions: Optional[List[Dict[str, Any]]] = None


class KubernetesJobsClient:
    """Cliente para execução de comandos como Kubernetes Jobs."""

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        namespace: str = 'neural-hive-execution',
        timeout: int = 600,
        poll_interval: int = 5,
        cleanup_jobs: bool = True,
        service_account: str = 'worker-agent-executor',
    ):
        """
        Inicializa cliente Kubernetes Jobs.

        Args:
            kubeconfig_path: Caminho para kubeconfig (None para in-cluster)
            namespace: Namespace padrão para Jobs
            timeout: Timeout padrão em segundos
            poll_interval: Intervalo de polling em segundos
            cleanup_jobs: Deletar Jobs após execução
            service_account: ServiceAccount padrão
        """
        self.kubeconfig_path = kubeconfig_path
        self.namespace = namespace
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.cleanup_jobs = cleanup_jobs
        self.service_account = service_account
        self._batch_api = None
        self._core_api = None
        self._initialized = False
        self.logger = logger.bind(service='k8s_jobs_client')

    async def initialize(self) -> None:
        """Inicializa conexão com Kubernetes API."""
        try:
            from kubernetes_asyncio import client, config

            if self.kubeconfig_path:
                await config.load_kube_config(config_file=self.kubeconfig_path)
                self.logger.info('k8s_config_loaded_from_file', path=self.kubeconfig_path)
            else:
                config.load_incluster_config()
                self.logger.info('k8s_config_loaded_incluster')

            self._batch_api = client.BatchV1Api()
            self._core_api = client.CoreV1Api()
            self._initialized = True
            self.logger.info('k8s_jobs_client_initialized', namespace=self.namespace)

        except ImportError:
            self.logger.error('kubernetes_asyncio_not_installed')
            raise K8sJobError('kubernetes-asyncio não está instalado')
        except Exception as e:
            self.logger.error('k8s_jobs_init_failed', error=str(e))
            raise K8sJobError(f'Falha ao inicializar cliente K8s: {e}')

    async def close(self) -> None:
        """Fecha conexão com Kubernetes API."""
        from kubernetes_asyncio import client
        await client.ApiClient().close()
        self._initialized = False
        self.logger.info('k8s_jobs_client_closed')

    def _generate_job_name(self, prefix: str = 'exec') -> str:
        """Gera nome único para Job."""
        short_uuid = str(uuid.uuid4())[:8]
        return f'{prefix}-{short_uuid}'

    def _build_job_manifest(self, request: K8sJobRequest) -> Dict[str, Any]:
        """Constrói manifest do Job Kubernetes."""
        job_name = request.name or self._generate_job_name()

        # Labels padrão
        labels = {
            'app.kubernetes.io/name': 'neural-hive-executor',
            'app.kubernetes.io/component': 'job',
            'app.kubernetes.io/managed-by': 'worker-agents',
            'neural-hive.io/job-id': job_name,
        }
        if request.labels:
            labels.update(request.labels)

        # Annotations padrão
        annotations = {
            'neural-hive.io/created-by': 'execute-executor',
        }
        if request.annotations:
            annotations.update(request.annotations)

        # Construir env vars
        env = []
        if request.env_vars:
            for name, value in request.env_vars.items():
                env.append({'name': name, 'value': value})

        # Construir container spec
        container = {
            'name': 'executor',
            'image': request.image,
            'command': request.command,
            'resources': {
                'requests': {
                    'cpu': request.resource_limits.cpu_request,
                    'memory': request.resource_limits.memory_request,
                },
                'limits': {
                    'cpu': request.resource_limits.cpu_limit,
                    'memory': request.resource_limits.memory_limit,
                }
            },
            'securityContext': {
                'runAsNonRoot': request.security_context.run_as_non_root,
                'readOnlyRootFilesystem': request.security_context.read_only_root_filesystem,
                'allowPrivilegeEscalation': request.security_context.allow_privilege_escalation,
            }
        }

        if request.args:
            container['args'] = request.args

        if env:
            container['env'] = env

        if request.security_context.run_as_user:
            container['securityContext']['runAsUser'] = request.security_context.run_as_user

        if request.security_context.run_as_group:
            container['securityContext']['runAsGroup'] = request.security_context.run_as_group

        # Construir Job manifest
        job_manifest = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'name': job_name,
                'namespace': request.namespace,
                'labels': labels,
                'annotations': annotations,
            },
            'spec': {
                'backoffLimit': request.backoff_limit,
                'ttlSecondsAfterFinished': request.ttl_seconds_after_finished,
                'template': {
                    'metadata': {
                        'labels': labels,
                    },
                    'spec': {
                        'restartPolicy': request.restart_policy.value,
                        'containers': [container],
                    }
                }
            }
        }

        # ServiceAccount
        sa = request.service_account or self.service_account
        if sa:
            job_manifest['spec']['template']['spec']['serviceAccountName'] = sa

        # Active deadline
        if request.active_deadline_seconds:
            job_manifest['spec']['activeDeadlineSeconds'] = request.active_deadline_seconds

        return job_manifest

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _create_job(self, manifest: Dict[str, Any], namespace: str) -> str:
        """Cria Job no Kubernetes."""
        from kubernetes_asyncio import client

        with tracer.start_as_current_span('k8s.create_job') as span:
            job_name = manifest['metadata']['name']
            span.set_attribute('k8s.job_name', job_name)
            span.set_attribute('k8s.namespace', namespace)

            try:
                body = client.V1Job(**manifest)
                await self._batch_api.create_namespaced_job(
                    namespace=namespace,
                    body=body
                )
                self.logger.info('k8s_job_created', job_name=job_name, namespace=namespace)
                return job_name

            except Exception as e:
                self.logger.error('k8s_job_create_failed', job_name=job_name, error=str(e))
                raise K8sJobError(f'Falha ao criar Job {job_name}: {e}')

    async def _get_job_status(self, job_name: str, namespace: str) -> Dict[str, Any]:
        """Obtém status do Job."""
        try:
            job = await self._batch_api.read_namespaced_job_status(
                name=job_name,
                namespace=namespace
            )
            return {
                'active': job.status.active or 0,
                'succeeded': job.status.succeeded or 0,
                'failed': job.status.failed or 0,
                'start_time': str(job.status.start_time) if job.status.start_time else None,
                'completion_time': str(job.status.completion_time) if job.status.completion_time else None,
                'conditions': [
                    {'type': c.type, 'status': c.status, 'reason': c.reason, 'message': c.message}
                    for c in (job.status.conditions or [])
                ]
            }
        except Exception as e:
            self.logger.warning('k8s_job_status_failed', job_name=job_name, error=str(e))
            return {'active': 0, 'succeeded': 0, 'failed': 0}

    async def _get_pod_for_job(self, job_name: str, namespace: str) -> Optional[str]:
        """Obtém nome do Pod criado pelo Job."""
        try:
            pods = await self._core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f'job-name={job_name}'
            )
            if pods.items:
                return pods.items[0].metadata.name
            return None
        except Exception as e:
            self.logger.warning('k8s_pod_lookup_failed', job_name=job_name, error=str(e))
            return None

    async def _get_pod_logs(self, pod_name: str, namespace: str) -> str:
        """Obtém logs do Pod."""
        try:
            logs = await self._core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace
            )
            return logs or ''
        except Exception as e:
            self.logger.warning('k8s_pod_logs_failed', pod_name=pod_name, error=str(e))
            return f'[Erro ao obter logs: {e}]'

    async def _get_pod_exit_code(self, pod_name: str, namespace: str) -> Optional[int]:
        """Obtém exit code do container no Pod."""
        try:
            pod = await self._core_api.read_namespaced_pod_status(
                name=pod_name,
                namespace=namespace
            )
            for container_status in (pod.status.container_statuses or []):
                if container_status.name == 'executor':
                    if container_status.state.terminated:
                        return container_status.state.terminated.exit_code
            return None
        except Exception as e:
            self.logger.warning('k8s_exit_code_failed', pod_name=pod_name, error=str(e))
            return None

    async def _wait_for_job(
        self,
        job_name: str,
        namespace: str,
        timeout_seconds: int
    ) -> K8sJobStatus:
        """Aguarda conclusão do Job via polling."""
        with tracer.start_as_current_span('k8s.wait_for_job') as span:
            span.set_attribute('k8s.job_name', job_name)
            span.set_attribute('k8s.timeout', timeout_seconds)

            start_time = asyncio.get_event_loop().time()

            while True:
                status = await self._get_job_status(job_name, namespace)

                if status['succeeded'] > 0:
                    self.logger.info('k8s_job_succeeded', job_name=job_name)
                    return K8sJobStatus.SUCCEEDED

                if status['failed'] > 0:
                    self.logger.info('k8s_job_failed', job_name=job_name)
                    return K8sJobStatus.FAILED

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    self.logger.warning(
                        'k8s_job_timeout',
                        job_name=job_name,
                        elapsed=elapsed,
                        timeout=timeout_seconds
                    )
                    raise K8sJobTimeoutError(
                        f'Timeout após {timeout_seconds}s aguardando Job {job_name}'
                    )

                self.logger.debug(
                    'k8s_job_polling',
                    job_name=job_name,
                    active=status['active'],
                    elapsed=int(elapsed)
                )

                await asyncio.sleep(self.poll_interval)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _delete_job(self, job_name: str, namespace: str) -> None:
        """Deleta Job e Pods associados."""
        from kubernetes_asyncio import client

        try:
            await self._batch_api.delete_namespaced_job(
                name=job_name,
                namespace=namespace,
                body=client.V1DeleteOptions(propagation_policy='Foreground')
            )
            self.logger.info('k8s_job_deleted', job_name=job_name)
        except Exception as e:
            self.logger.warning('k8s_job_delete_failed', job_name=job_name, error=str(e))

    async def execute_job(
        self,
        request: K8sJobRequest,
        metrics=None
    ) -> K8sJobResult:
        """
        Cria e executa Job Kubernetes.

        Args:
            request: Parâmetros do Job
            metrics: Objeto de métricas Prometheus (opcional)

        Returns:
            K8sJobResult com resultado da execução

        Raises:
            K8sJobError: Erro na execução
            K8sJobTimeoutError: Timeout aguardando Job
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('k8s.execute_job') as span:
            span.set_attribute('k8s.image', request.image)
            span.set_attribute('k8s.namespace', request.namespace)

            start_time = asyncio.get_event_loop().time()
            job_name = None

            try:
                # Construir e criar Job
                manifest = self._build_job_manifest(request)
                job_name = await self._create_job(manifest, request.namespace)
                span.set_attribute('k8s.job_name', job_name)

                # Aguardar conclusão
                timeout = request.timeout_seconds or self.timeout
                job_status = await self._wait_for_job(job_name, request.namespace, timeout)

                # Obter Pod e logs
                pod_name = await self._get_pod_for_job(job_name, request.namespace)
                logs = ''
                exit_code = None

                if pod_name:
                    logs = await self._get_pod_logs(pod_name, request.namespace)
                    exit_code = await self._get_pod_exit_code(pod_name, request.namespace)

                # Obter status final do Job
                final_status = await self._get_job_status(job_name, request.namespace)

                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                self.logger.info(
                    'k8s_job_completed',
                    job_name=job_name,
                    status=job_status.value,
                    exit_code=exit_code,
                    duration_ms=duration_ms
                )

                # Registrar métricas
                if metrics:
                    status_label = 'succeeded' if job_status == K8sJobStatus.SUCCEEDED else 'failed'
                    if hasattr(metrics, 'k8s_jobs_executed_total'):
                        metrics.k8s_jobs_executed_total.labels(status=status_label).inc()
                    if hasattr(metrics, 'k8s_job_duration_seconds'):
                        metrics.k8s_job_duration_seconds.labels(
                            stage='total'
                        ).observe(duration_ms / 1000)

                return K8sJobResult(
                    job_name=job_name,
                    pod_name=pod_name,
                    namespace=request.namespace,
                    status=job_status,
                    exit_code=exit_code,
                    logs=logs,
                    duration_ms=duration_ms,
                    start_time=final_status.get('start_time'),
                    completion_time=final_status.get('completion_time'),
                    conditions=final_status.get('conditions')
                )

            except K8sJobTimeoutError:
                if metrics and hasattr(metrics, 'k8s_jobs_executed_total'):
                    metrics.k8s_jobs_executed_total.labels(status='timeout').inc()
                raise

            except Exception as e:
                self.logger.error(
                    'k8s_job_execution_failed',
                    job_name=job_name,
                    error=str(e)
                )
                if metrics and hasattr(metrics, 'k8s_jobs_executed_total'):
                    metrics.k8s_jobs_executed_total.labels(status='failed').inc()
                raise K8sJobError(f'Erro na execução do Job: {e}')

            finally:
                # Cleanup Job
                if job_name and self.cleanup_jobs:
                    try:
                        await self._delete_job(job_name, request.namespace)
                    except Exception as e:
                        self.logger.warning(
                            'k8s_job_cleanup_failed',
                            job_name=job_name,
                            error=str(e)
                        )

    async def health_check(self) -> bool:
        """Verifica se Kubernetes API está acessível."""
        try:
            if not self._batch_api:
                return False
            await self._batch_api.get_api_resources()
            return True
        except Exception:
            return False
