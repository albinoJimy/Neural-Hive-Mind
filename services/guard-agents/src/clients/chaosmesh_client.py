"""ChaosMesh client for chaos engineering experiments"""
from typing import Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Prometheus metrics
chaosmesh_operations_total = Counter(
    'guard_agents_chaosmesh_operations_total',
    'Total de operacoes ChaosMesh',
    ['operation', 'chaos_type', 'status']
)

chaosmesh_operation_duration = Histogram(
    'guard_agents_chaosmesh_operation_duration_seconds',
    'Duracao das operacoes ChaosMesh',
    ['operation'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)


class ChaosMeshClient:
    """
    Cliente para ChaosMesh - plataforma de chaos engineering para Kubernetes.

    Suporta criação de experimentos:
    - PodChaos: Kill, failure, container kill
    - NetworkChaos: Delay, loss, duplicate, corrupt
    - StressChaos: CPU/memory stress

    Requer ChaosMesh instalado no cluster.
    """

    # ChaosMesh API group and versions
    CHAOS_API_GROUP = "chaos-mesh.org"
    CHAOS_API_VERSION = "v1alpha1"

    def __init__(
        self,
        in_cluster: bool = True,
        namespace: str = "chaos-testing",
        enabled: bool = True
    ):
        self.in_cluster = in_cluster
        self.namespace = namespace
        self.enabled = enabled
        self.custom_api: Optional[client.CustomObjectsApi] = None
        self._connected = False

    async def connect(self):
        """Conecta ao cluster Kubernetes para operações ChaosMesh"""
        if not self.enabled:
            logger.info("chaosmesh_client.disabled")
            return

        try:
            if self.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.custom_api = client.CustomObjectsApi()
            self._connected = True

            logger.info(
                "chaosmesh_client.connected",
                namespace=self.namespace
            )

        except Exception as e:
            logger.error(
                "chaosmesh_client.connection_failed",
                error=str(e)
            )
            # Não raise - permite graceful degradation
            self._connected = False

    def is_healthy(self) -> bool:
        """Verifica se cliente está saudável"""
        return self.enabled and self._connected and self.custom_api is not None

    async def create_pod_chaos(
        self,
        name: str,
        namespace: Optional[str] = None,
        action: str = "pod-kill",
        selector: Optional[Dict[str, Any]] = None,
        duration: str = "30s"
    ) -> Dict[str, Any]:
        """
        Cria experimento PodChaos.

        Args:
            name: Nome do experimento
            namespace: Namespace alvo (default: self.namespace)
            action: Tipo de ação (pod-kill, pod-failure, container-kill)
            selector: Seletor de pods alvo
            duration: Duração do experimento

        Returns:
            Dict com resultado da criação
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "ChaosMesh client not available",
                "experiment_name": name
            }

        ns = namespace or self.namespace

        with chaosmesh_operation_duration.labels(operation="create_pod_chaos").time():
            try:
                experiment = {
                    "apiVersion": f"{self.CHAOS_API_GROUP}/{self.CHAOS_API_VERSION}",
                    "kind": "PodChaos",
                    "metadata": {
                        "name": name,
                        "namespace": ns,
                        "labels": {
                            "app.kubernetes.io/managed-by": "guard-agents"
                        }
                    },
                    "spec": {
                        "action": action,
                        "mode": "one",
                        "selector": selector or {"namespaces": [ns]},
                        "duration": duration
                    }
                }

                result = self.custom_api.create_namespaced_custom_object(
                    group=self.CHAOS_API_GROUP,
                    version=self.CHAOS_API_VERSION,
                    namespace=ns,
                    plural="podchaos",
                    body=experiment
                )

                chaosmesh_operations_total.labels(
                    operation="create_pod_chaos",
                    chaos_type="pod",
                    status="success"
                ).inc()

                logger.info(
                    "chaosmesh_client.pod_chaos_created",
                    name=name,
                    action=action,
                    namespace=ns,
                    duration=duration
                )

                return {
                    "success": True,
                    "experiment_name": name,
                    "experiment_type": "PodChaos",
                    "action": action,
                    "namespace": ns,
                    "duration": duration
                }

            except ApiException as e:
                chaosmesh_operations_total.labels(
                    operation="create_pod_chaos",
                    chaos_type="pod",
                    status="error"
                ).inc()

                logger.error(
                    "chaosmesh_client.create_pod_chaos_failed",
                    name=name,
                    error=str(e)
                )

                return {
                    "success": False,
                    "experiment_name": name,
                    "error": str(e)
                }

    async def create_network_chaos(
        self,
        name: str,
        namespace: Optional[str] = None,
        action: str = "delay",
        selector: Optional[Dict[str, Any]] = None,
        duration: str = "30s",
        delay_latency: str = "100ms",
        loss_percentage: int = 0
    ) -> Dict[str, Any]:
        """
        Cria experimento NetworkChaos.

        Args:
            name: Nome do experimento
            namespace: Namespace alvo
            action: Tipo de ação (delay, loss, duplicate, corrupt, partition)
            selector: Seletor de pods alvo
            duration: Duração do experimento
            delay_latency: Latência para ação delay
            loss_percentage: Percentual de perda para ação loss

        Returns:
            Dict com resultado da criação
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "ChaosMesh client not available",
                "experiment_name": name
            }

        ns = namespace or self.namespace

        with chaosmesh_operation_duration.labels(operation="create_network_chaos").time():
            try:
                spec = {
                    "action": action,
                    "mode": "one",
                    "selector": selector or {"namespaces": [ns]},
                    "duration": duration
                }

                # Adicionar configurações específicas por tipo de ação
                if action == "delay":
                    spec["delay"] = {"latency": delay_latency}
                elif action == "loss":
                    spec["loss"] = {"loss": str(loss_percentage)}

                experiment = {
                    "apiVersion": f"{self.CHAOS_API_GROUP}/{self.CHAOS_API_VERSION}",
                    "kind": "NetworkChaos",
                    "metadata": {
                        "name": name,
                        "namespace": ns,
                        "labels": {
                            "app.kubernetes.io/managed-by": "guard-agents"
                        }
                    },
                    "spec": spec
                }

                result = self.custom_api.create_namespaced_custom_object(
                    group=self.CHAOS_API_GROUP,
                    version=self.CHAOS_API_VERSION,
                    namespace=ns,
                    plural="networkchaos",
                    body=experiment
                )

                chaosmesh_operations_total.labels(
                    operation="create_network_chaos",
                    chaos_type="network",
                    status="success"
                ).inc()

                logger.info(
                    "chaosmesh_client.network_chaos_created",
                    name=name,
                    action=action,
                    namespace=ns
                )

                return {
                    "success": True,
                    "experiment_name": name,
                    "experiment_type": "NetworkChaos",
                    "action": action,
                    "namespace": ns,
                    "duration": duration
                }

            except ApiException as e:
                chaosmesh_operations_total.labels(
                    operation="create_network_chaos",
                    chaos_type="network",
                    status="error"
                ).inc()

                logger.error(
                    "chaosmesh_client.create_network_chaos_failed",
                    name=name,
                    error=str(e)
                )

                return {
                    "success": False,
                    "experiment_name": name,
                    "error": str(e)
                }

    async def delete_chaos_experiment(
        self,
        name: str,
        chaos_type: str = "podchaos",
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Remove um experimento de chaos.

        Args:
            name: Nome do experimento
            chaos_type: Tipo do experimento (podchaos, networkchaos, stresschaos)
            namespace: Namespace do experimento

        Returns:
            Dict com resultado da deleção
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "ChaosMesh client not available",
                "experiment_name": name
            }

        ns = namespace or self.namespace

        with chaosmesh_operation_duration.labels(operation="delete_chaos_experiment").time():
            try:
                self.custom_api.delete_namespaced_custom_object(
                    group=self.CHAOS_API_GROUP,
                    version=self.CHAOS_API_VERSION,
                    namespace=ns,
                    plural=chaos_type.lower(),
                    name=name
                )

                chaosmesh_operations_total.labels(
                    operation="delete_chaos_experiment",
                    chaos_type=chaos_type,
                    status="success"
                ).inc()

                logger.info(
                    "chaosmesh_client.experiment_deleted",
                    name=name,
                    chaos_type=chaos_type,
                    namespace=ns
                )

                return {
                    "success": True,
                    "experiment_name": name,
                    "chaos_type": chaos_type,
                    "namespace": ns
                }

            except ApiException as e:
                if e.status == 404:
                    # Experimento não existe - considerar sucesso
                    return {
                        "success": True,
                        "experiment_name": name,
                        "warning": "Experiment not found"
                    }

                chaosmesh_operations_total.labels(
                    operation="delete_chaos_experiment",
                    chaos_type=chaos_type,
                    status="error"
                ).inc()

                logger.error(
                    "chaosmesh_client.delete_experiment_failed",
                    name=name,
                    error=str(e)
                )

                return {
                    "success": False,
                    "experiment_name": name,
                    "error": str(e)
                }

    async def get_experiment_status(
        self,
        name: str,
        chaos_type: str = "podchaos",
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtém status de um experimento.

        Args:
            name: Nome do experimento
            chaos_type: Tipo do experimento
            namespace: Namespace do experimento

        Returns:
            Dict com status do experimento
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "ChaosMesh client not available",
                "experiment_name": name
            }

        ns = namespace or self.namespace

        try:
            result = self.custom_api.get_namespaced_custom_object(
                group=self.CHAOS_API_GROUP,
                version=self.CHAOS_API_VERSION,
                namespace=ns,
                plural=chaos_type.lower(),
                name=name
            )

            status = result.get("status", {})

            return {
                "success": True,
                "experiment_name": name,
                "chaos_type": chaos_type,
                "phase": status.get("experiment", {}).get("phase", "unknown"),
                "conditions": status.get("conditions", []),
                "namespace": ns
            }

        except ApiException as e:
            logger.error(
                "chaosmesh_client.get_status_failed",
                name=name,
                error=str(e)
            )

            return {
                "success": False,
                "experiment_name": name,
                "error": str(e)
            }
