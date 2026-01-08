"""Cliente Kubernetes para SLA Management System."""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Metricas Prometheus
sla_k8s_operations_total = Counter(
    'sla_k8s_operations_total',
    'Total de operacoes Kubernetes do SLA Management',
    ['operation', 'status']
)

sla_k8s_operation_duration = Histogram(
    'sla_k8s_operation_duration_seconds',
    'Duracao das operacoes Kubernetes do SLA Management',
    ['operation'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)

# Constantes do CRD
CRD_GROUP = "neural-hive.io"
CRD_VERSION = "v1"
CRD_PLURAL = "slodefinitions"


class KubernetesClient:
    """Cliente Kubernetes para operacoes com CRDs SLODefinition."""

    def __init__(self, in_cluster: bool = True, namespace: str = "neural-hive"):
        """
        Inicializa cliente Kubernetes.

        Args:
            in_cluster: Se True, usa config do cluster. Se False, usa kubeconfig local.
            namespace: Namespace padrao para operacoes.
        """
        self.in_cluster = in_cluster
        self.namespace = namespace
        self.custom_api: Optional[client.CustomObjectsApi] = None
        self._connected = False

    async def connect(self) -> None:
        """Conecta ao cluster Kubernetes."""
        try:
            if self.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.custom_api = client.CustomObjectsApi()
            self._connected = True

            logger.info(
                "kubernetes.connected",
                in_cluster=self.in_cluster,
                namespace=self.namespace
            )
        except Exception as e:
            logger.error("kubernetes.connection_failed", error=str(e))
            raise

    def is_healthy(self) -> bool:
        """Verifica se cliente esta saudavel."""
        return self._connected and self.custom_api is not None

    async def list_slo_definitions(
        self,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista CRDs SLODefinition no cluster.

        Args:
            namespace: Namespace especifico ou None para todos os namespaces.

        Returns:
            Lista de CRDs como dicts.
        """
        if not self.custom_api:
            logger.warning("kubernetes.not_connected")
            return []

        with sla_k8s_operation_duration.labels(operation="list_slo_definitions").time():
            try:
                if namespace:
                    result = self.custom_api.list_namespaced_custom_object(
                        group=CRD_GROUP,
                        version=CRD_VERSION,
                        namespace=namespace,
                        plural=CRD_PLURAL
                    )
                else:
                    result = self.custom_api.list_cluster_custom_object(
                        group=CRD_GROUP,
                        version=CRD_VERSION,
                        plural=CRD_PLURAL
                    )

                items = result.get("items", [])
                sla_k8s_operations_total.labels(
                    operation="list_slo_definitions",
                    status="success"
                ).inc()

                logger.info(
                    "kubernetes.slo_definitions_listed",
                    count=len(items),
                    namespace=namespace or "all"
                )

                return items

            except ApiException as e:
                sla_k8s_operations_total.labels(
                    operation="list_slo_definitions",
                    status="error"
                ).inc()
                logger.error(
                    "kubernetes.list_slo_definitions_failed",
                    namespace=namespace,
                    error=str(e),
                    status_code=e.status
                )
                raise

    async def get_slo_definition(
        self,
        name: str,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """
        Busca CRD SLODefinition especifico.

        Args:
            name: Nome do recurso.
            namespace: Namespace do recurso.

        Returns:
            CRD como dict ou None se nao encontrado.
        """
        if not self.custom_api:
            logger.warning("kubernetes.not_connected")
            return None

        with sla_k8s_operation_duration.labels(operation="get_slo_definition").time():
            try:
                result = self.custom_api.get_namespaced_custom_object(
                    group=CRD_GROUP,
                    version=CRD_VERSION,
                    namespace=namespace,
                    plural=CRD_PLURAL,
                    name=name
                )

                sla_k8s_operations_total.labels(
                    operation="get_slo_definition",
                    status="success"
                ).inc()

                return result

            except ApiException as e:
                if e.status == 404:
                    logger.debug(
                        "kubernetes.slo_definition_not_found",
                        name=name,
                        namespace=namespace
                    )
                    return None

                sla_k8s_operations_total.labels(
                    operation="get_slo_definition",
                    status="error"
                ).inc()
                logger.error(
                    "kubernetes.get_slo_definition_failed",
                    name=name,
                    namespace=namespace,
                    error=str(e)
                )
                return None

    async def update_slo_status(
        self,
        name: str,
        namespace: str,
        status: Dict[str, Any]
    ) -> bool:
        """
        Atualiza status do CRD SLODefinition.

        Args:
            name: Nome do recurso.
            namespace: Namespace do recurso.
            status: Novos campos de status.

        Returns:
            True se sucesso, False se falha.
        """
        if not self.custom_api:
            logger.warning("kubernetes.not_connected")
            return False

        with sla_k8s_operation_duration.labels(operation="update_slo_status").time():
            try:
                # Buscar recurso atual para obter resourceVersion
                current = await self.get_slo_definition(name, namespace)
                if not current:
                    logger.warning(
                        "kubernetes.slo_definition_not_found_for_status_update",
                        name=name,
                        namespace=namespace
                    )
                    return False

                # Preparar patch de status
                current_status = current.get("status", {})
                current_status.update(status)
                current_status["lastSyncTime"] = datetime.now(timezone.utc).isoformat()

                patch = {"status": current_status}

                self.custom_api.patch_namespaced_custom_object_status(
                    group=CRD_GROUP,
                    version=CRD_VERSION,
                    namespace=namespace,
                    plural=CRD_PLURAL,
                    name=name,
                    body=patch
                )

                sla_k8s_operations_total.labels(
                    operation="update_slo_status",
                    status="success"
                ).inc()

                logger.info(
                    "kubernetes.slo_status_updated",
                    name=name,
                    namespace=namespace,
                    synced=status.get("synced")
                )

                return True

            except ApiException as e:
                sla_k8s_operations_total.labels(
                    operation="update_slo_status",
                    status="error"
                ).inc()
                logger.error(
                    "kubernetes.update_slo_status_failed",
                    name=name,
                    namespace=namespace,
                    error=str(e)
                )
                return False
