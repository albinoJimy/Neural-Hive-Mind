"""
Cliente Kubernetes para monitoramento de HPA e recursos durante testes de carga.

Observa eventos de autoscaling e metricas de pods.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from kubernetes import client, config
    from kubernetes.client import (
        AutoscalingV2Api,
        CoreV1Api,
        AppsV1Api,
        CustomObjectsApi,
    )
    from kubernetes.client.rest import ApiException
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class HPAStatus:
    """Status do HorizontalPodAutoscaler."""
    name: str
    namespace: str
    current_replicas: int
    desired_replicas: int
    min_replicas: int
    max_replicas: int
    current_cpu_utilization: Optional[int] = None
    target_cpu_utilization: Optional[int] = None
    current_memory_utilization: Optional[int] = None
    target_memory_utilization: Optional[int] = None
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    last_scale_time: Optional[datetime] = None


@dataclass
class PodMetrics:
    """Metricas de um pod."""
    name: str
    namespace: str
    cpu_usage_millicores: int
    memory_usage_bytes: int
    timestamp: datetime


@dataclass
class ScalingEvent:
    """Evento de scaling observado."""
    timestamp: datetime
    event_type: str  # 'scale_up', 'scale_down', 'steady'
    from_replicas: int
    to_replicas: int
    reason: Optional[str] = None


@dataclass
class PodEvent:
    """Evento de pod (eviction, OOM, etc)."""
    timestamp: datetime
    pod_name: str
    event_type: str
    reason: str
    message: str


class KubernetesClient:
    """Cliente Kubernetes para monitoramento de carga."""

    def __init__(
        self,
        namespace: str = 'neural-hive-orchestration',
        in_cluster: bool = True,
    ):
        """
        Inicializa o cliente Kubernetes.

        Args:
            namespace: Namespace padrao para queries
            in_cluster: Se True, usa configuracao in-cluster
        """
        self.namespace = namespace
        self._initialized = False
        self._core_api: Optional[CoreV1Api] = None
        self._apps_api: Optional[AppsV1Api] = None
        self._autoscaling_api: Optional[AutoscalingV2Api] = None
        self._custom_api: Optional[CustomObjectsApi] = None

        if not KUBERNETES_AVAILABLE:
            logger.warning('kubernetes package not available')
            return

        try:
            if in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self._core_api = CoreV1Api()
            self._apps_api = AppsV1Api()
            self._autoscaling_api = AutoscalingV2Api()
            self._custom_api = CustomObjectsApi()
            self._initialized = True
            logger.info(f'Kubernetes client initialized for namespace {namespace}')
        except Exception as e:
            logger.warning(f'Failed to initialize Kubernetes client: {e}')

    async def close(self) -> None:
        """Fecha o cliente (no-op para kubernetes client)."""
        pass

    def is_available(self) -> bool:
        """Verifica se o cliente esta disponivel."""
        return self._initialized

    async def get_hpa_status(
        self,
        name: str = 'orchestrator-dynamic',
        namespace: Optional[str] = None,
    ) -> Optional[HPAStatus]:
        """
        Obtem status do HPA.

        Args:
            name: Nome do HPA
            namespace: Namespace (usa padrao se nao especificado)

        Returns:
            HPAStatus ou None se nao encontrado
        """
        if not self._initialized:
            return None

        ns = namespace or self.namespace

        try:
            hpa = await asyncio.to_thread(
                self._autoscaling_api.read_namespaced_horizontal_pod_autoscaler,
                name=name,
                namespace=ns,
            )

            status = HPAStatus(
                name=name,
                namespace=ns,
                current_replicas=hpa.status.current_replicas or 0,
                desired_replicas=hpa.status.desired_replicas or 0,
                min_replicas=hpa.spec.min_replicas or 1,
                max_replicas=hpa.spec.max_replicas or 10,
            )

            # Extrair metricas atuais
            if hpa.status.current_metrics:
                for metric in hpa.status.current_metrics:
                    if metric.type == 'Resource' and metric.resource:
                        if metric.resource.name == 'cpu':
                            status.current_cpu_utilization = (
                                metric.resource.current.average_utilization
                            )
                        elif metric.resource.name == 'memory':
                            status.current_memory_utilization = (
                                metric.resource.current.average_utilization
                            )

            # Extrair targets
            if hpa.spec.metrics:
                for metric in hpa.spec.metrics:
                    if metric.type == 'Resource' and metric.resource:
                        if metric.resource.name == 'cpu' and metric.resource.target:
                            status.target_cpu_utilization = (
                                metric.resource.target.average_utilization
                            )
                        elif metric.resource.name == 'memory' and metric.resource.target:
                            status.target_memory_utilization = (
                                metric.resource.target.average_utilization
                            )

            # Extrair conditions
            if hpa.status.conditions:
                for cond in hpa.status.conditions:
                    status.conditions.append({
                        'type': cond.type,
                        'status': cond.status,
                        'reason': cond.reason,
                        'message': cond.message,
                        'last_transition_time': cond.last_transition_time.isoformat() if cond.last_transition_time else None,
                    })

            # Last scale time
            if hpa.status.last_scale_time:
                status.last_scale_time = hpa.status.last_scale_time

            return status

        except ApiException as e:
            if e.status == 404:
                logger.warning(f'HPA {name} not found in namespace {ns}')
            else:
                logger.warning(f'Failed to get HPA status: {e}')
            return None
        except Exception as e:
            logger.warning(f'Error getting HPA status: {e}')
            return None

    async def get_pod_count(
        self,
        label_selector: str = 'app.kubernetes.io/name=orchestrator-dynamic',
        namespace: Optional[str] = None,
    ) -> int:
        """
        Conta pods por label selector.

        Args:
            label_selector: Seletor de labels
            namespace: Namespace

        Returns:
            Numero de pods running
        """
        if not self._initialized:
            return 0

        ns = namespace or self.namespace

        try:
            pods = await asyncio.to_thread(
                self._core_api.list_namespaced_pod,
                namespace=ns,
                label_selector=label_selector,
            )

            running_count = sum(
                1 for pod in pods.items
                if pod.status.phase == 'Running'
            )

            return running_count

        except Exception as e:
            logger.warning(f'Failed to count pods: {e}')
            return 0

    async def get_pod_metrics(
        self,
        label_selector: str = 'app.kubernetes.io/name=orchestrator-dynamic',
        namespace: Optional[str] = None,
    ) -> List[PodMetrics]:
        """
        Obtem metricas de pods via metrics-server.

        Args:
            label_selector: Seletor de labels
            namespace: Namespace

        Returns:
            Lista de PodMetrics
        """
        if not self._initialized:
            return []

        ns = namespace or self.namespace
        metrics_list = []

        try:
            # Usar API de metricas
            metrics = await asyncio.to_thread(
                self._custom_api.list_namespaced_custom_object,
                group='metrics.k8s.io',
                version='v1beta1',
                namespace=ns,
                plural='pods',
                label_selector=label_selector,
            )

            for item in metrics.get('items', []):
                name = item.get('metadata', {}).get('name', '')
                containers = item.get('containers', [])

                total_cpu = 0
                total_memory = 0

                for container in containers:
                    usage = container.get('usage', {})

                    # Parse CPU (pode ser "100m" ou "1")
                    cpu_str = usage.get('cpu', '0')
                    if cpu_str.endswith('n'):
                        total_cpu += int(cpu_str[:-1]) // 1000000
                    elif cpu_str.endswith('m'):
                        total_cpu += int(cpu_str[:-1])
                    else:
                        total_cpu += int(float(cpu_str) * 1000)

                    # Parse Memory (pode ser "100Mi", "1Gi", etc)
                    mem_str = usage.get('memory', '0')
                    if mem_str.endswith('Ki'):
                        total_memory += int(mem_str[:-2]) * 1024
                    elif mem_str.endswith('Mi'):
                        total_memory += int(mem_str[:-2]) * 1024 * 1024
                    elif mem_str.endswith('Gi'):
                        total_memory += int(mem_str[:-2]) * 1024 * 1024 * 1024
                    else:
                        total_memory += int(mem_str)

                metrics_list.append(PodMetrics(
                    name=name,
                    namespace=ns,
                    cpu_usage_millicores=total_cpu,
                    memory_usage_bytes=total_memory,
                    timestamp=datetime.utcnow(),
                ))

        except ApiException as e:
            if e.status == 404:
                logger.debug('Metrics API not available')
            else:
                logger.warning(f'Failed to get pod metrics: {e}')
        except Exception as e:
            logger.warning(f'Error getting pod metrics: {e}')

        return metrics_list

    async def get_pod_events(
        self,
        label_selector: str = 'app.kubernetes.io/name=orchestrator-dynamic',
        namespace: Optional[str] = None,
        event_types: Optional[List[str]] = None,
    ) -> List[PodEvent]:
        """
        Obtem eventos de pods (evictions, OOM, etc).

        Args:
            label_selector: Seletor de labels
            namespace: Namespace
            event_types: Tipos de eventos a filtrar

        Returns:
            Lista de PodEvent
        """
        if not self._initialized:
            return []

        ns = namespace or self.namespace
        events_list = []

        # Tipos de eventos relevantes para performance
        relevant_reasons = event_types or [
            'Evicted',
            'OOMKilled',
            'OOMKilling',
            'Killing',
            'Preempted',
            'FailedScheduling',
            'BackOff',
            'Unhealthy',
        ]

        try:
            # Primeiro, listar pods para obter nomes
            pods = await asyncio.to_thread(
                self._core_api.list_namespaced_pod,
                namespace=ns,
                label_selector=label_selector,
            )

            pod_names = {pod.metadata.name for pod in pods.items}

            # Listar eventos do namespace
            events = await asyncio.to_thread(
                self._core_api.list_namespaced_event,
                namespace=ns,
            )

            for event in events.items:
                # Filtrar eventos relacionados aos pods
                involved = event.involved_object
                if involved.kind != 'Pod' or involved.name not in pod_names:
                    continue

                # Filtrar por tipo de evento
                if event.reason not in relevant_reasons:
                    continue

                events_list.append(PodEvent(
                    timestamp=event.last_timestamp or datetime.utcnow(),
                    pod_name=involved.name,
                    event_type=event.type,
                    reason=event.reason,
                    message=event.message or '',
                ))

        except Exception as e:
            logger.warning(f'Failed to get pod events: {e}')

        return events_list

    async def watch_hpa_scaling(
        self,
        name: str = 'orchestrator-dynamic',
        namespace: Optional[str] = None,
        duration_seconds: int = 300,
        poll_interval: float = 5.0,
    ) -> List[ScalingEvent]:
        """
        Observa eventos de scaling do HPA.

        Args:
            name: Nome do HPA
            namespace: Namespace
            duration_seconds: Duracao do monitoramento
            poll_interval: Intervalo entre checks

        Returns:
            Lista de ScalingEvent observados
        """
        events = []
        last_replicas = None
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < duration_seconds:
            status = await self.get_hpa_status(name, namespace)

            if status:
                current = status.current_replicas

                if last_replicas is not None and current != last_replicas:
                    event_type = 'scale_up' if current > last_replicas else 'scale_down'
                    reason = None

                    # Tentar identificar razao
                    for cond in status.conditions:
                        if cond.get('type') == 'AbleToScale':
                            reason = cond.get('reason')
                            break

                    events.append(ScalingEvent(
                        timestamp=datetime.utcnow(),
                        event_type=event_type,
                        from_replicas=last_replicas,
                        to_replicas=current,
                        reason=reason,
                    ))

                    logger.info(
                        f'Scaling event: {event_type} from {last_replicas} to {current}'
                    )

                last_replicas = current

            await asyncio.sleep(poll_interval)

        return events

    async def wait_for_scale(
        self,
        target_replicas: int,
        name: str = 'orchestrator-dynamic',
        namespace: Optional[str] = None,
        timeout_seconds: int = 300,
    ) -> bool:
        """
        Aguarda HPA escalar para numero desejado de replicas.

        Args:
            target_replicas: Numero desejado de replicas
            name: Nome do HPA
            namespace: Namespace
            timeout_seconds: Timeout

        Returns:
            True se escalou, False se timeout
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            status = await self.get_hpa_status(name, namespace)

            if status and status.current_replicas >= target_replicas:
                logger.info(
                    f'HPA reached {status.current_replicas} replicas '
                    f'(target: {target_replicas})'
                )
                return True

            await asyncio.sleep(5.0)

        logger.warning(
            f'Timeout waiting for HPA to scale to {target_replicas} replicas'
        )
        return False

    async def check_for_evictions(
        self,
        label_selector: str = 'app.kubernetes.io/name=orchestrator-dynamic',
        namespace: Optional[str] = None,
    ) -> List[PodEvent]:
        """
        Verifica se houve evictions ou OOMs.

        Args:
            label_selector: Seletor de labels
            namespace: Namespace

        Returns:
            Lista de eventos de eviction/OOM
        """
        return await self.get_pod_events(
            label_selector=label_selector,
            namespace=namespace,
            event_types=['Evicted', 'OOMKilled', 'OOMKilling'],
        )

    async def get_resource_summary(
        self,
        label_selector: str = 'app.kubernetes.io/name=orchestrator-dynamic',
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Obtem resumo de recursos dos pods.

        Args:
            label_selector: Seletor de labels
            namespace: Namespace

        Returns:
            Dict com resumo de CPU, memoria, etc
        """
        ns = namespace or self.namespace

        summary = {
            'pod_count': 0,
            'total_cpu_millicores': 0,
            'total_memory_bytes': 0,
            'avg_cpu_millicores': 0,
            'avg_memory_bytes': 0,
        }

        metrics = await self.get_pod_metrics(label_selector, ns)

        if metrics:
            summary['pod_count'] = len(metrics)
            summary['total_cpu_millicores'] = sum(m.cpu_usage_millicores for m in metrics)
            summary['total_memory_bytes'] = sum(m.memory_usage_bytes for m in metrics)
            summary['avg_cpu_millicores'] = summary['total_cpu_millicores'] / len(metrics)
            summary['avg_memory_bytes'] = summary['total_memory_bytes'] / len(metrics)

        return summary
