"""Kubernetes client for Guard Agents"""
from typing import Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger()


class KubernetesClient:
    """Cliente Kubernetes para Guard Agents"""

    def __init__(self, in_cluster: bool = True, namespace: str = "neural-hive-resilience"):
        self.in_cluster = in_cluster
        self.namespace = namespace
        self.core_v1: Optional[client.CoreV1Api] = None
        self.apps_v1: Optional[client.AppsV1Api] = None

    async def connect(self):
        """Conecta ao cluster Kubernetes"""
        try:
            if self.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()

            # Testa conexão listando namespaces
            self.core_v1.list_namespace()
            logger.info("kubernetes.connected", in_cluster=self.in_cluster, namespace=self.namespace)
        except Exception as e:
            logger.error("kubernetes.connection_failed", error=str(e))
            raise

    def is_healthy(self) -> bool:
        """Verifica se cliente está saudável"""
        return self.core_v1 is not None and self.apps_v1 is not None

    async def get_pod(self, pod_name: str) -> Optional[dict]:
        """Obtém informações de um pod"""
        try:
            pod = self.core_v1.read_namespaced_pod(pod_name, self.namespace)
            return pod.to_dict()
        except ApiException as e:
            logger.error("kubernetes.get_pod_failed", pod=pod_name, error=str(e))
            return None

    async def delete_pod(self, pod_name: str) -> bool:
        """Deleta um pod (restart forçado)"""
        try:
            self.core_v1.delete_namespaced_pod(pod_name, self.namespace)
            logger.info("kubernetes.pod_deleted", pod=pod_name)
            return True
        except ApiException as e:
            logger.error("kubernetes.delete_pod_failed", pod=pod_name, error=str(e))
            return False

    async def scale_deployment(self, deployment_name: str, replicas: int) -> bool:
        """Escala um deployment"""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(deployment_name, self.namespace)
            deployment.spec.replicas = replicas
            self.apps_v1.patch_namespaced_deployment_scale(deployment_name, self.namespace, deployment)
            logger.info("kubernetes.deployment_scaled", deployment=deployment_name, replicas=replicas)
            return True
        except ApiException as e:
            logger.error("kubernetes.scale_deployment_failed", deployment=deployment_name, error=str(e))
            return False
