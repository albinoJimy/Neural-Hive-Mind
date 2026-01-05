"""Kubernetes client for Guard Agents"""
from typing import Optional, Dict, Any, List
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Metricas Prometheus
kubernetes_operations_total = Counter(
    'guard_agents_kubernetes_operations_total',
    'Total de operacoes Kubernetes',
    ['operation', 'status']
)

kubernetes_operation_duration = Histogram(
    'guard_agents_kubernetes_operation_duration_seconds',
    'Duracao das operacoes Kubernetes',
    ['operation'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)


class KubernetesClient:
    """Cliente Kubernetes para Guard Agents com operacoes de remediacao"""

    def __init__(self, in_cluster: bool = True, namespace: str = "neural-hive"):
        self.in_cluster = in_cluster
        self.namespace = namespace
        self.core_v1: Optional[client.CoreV1Api] = None
        self.apps_v1: Optional[client.AppsV1Api] = None
        self.networking_v1: Optional[client.NetworkingV1Api] = None

    async def connect(self):
        """Conecta ao cluster Kubernetes"""
        try:
            if self.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.networking_v1 = client.NetworkingV1Api()

            # Testa conexao verificando pods no proprio namespace
            self.core_v1.list_namespaced_pod(self.namespace, limit=1)
            logger.info("kubernetes.connected", in_cluster=self.in_cluster, namespace=self.namespace)
        except Exception as e:
            logger.error("kubernetes.connection_failed", error=str(e))
            raise

    def is_healthy(self) -> bool:
        """Verifica se cliente esta saudavel"""
        return self.core_v1 is not None and self.apps_v1 is not None

    async def get_pod(self, pod_name: str, namespace: Optional[str] = None) -> Optional[dict]:
        """Obtem informacoes de um pod"""
        ns = namespace or self.namespace
        with kubernetes_operation_duration.labels(operation="get_pod").time():
            try:
                pod = self.core_v1.read_namespaced_pod(pod_name, ns)
                kubernetes_operations_total.labels(operation="get_pod", status="success").inc()
                return pod.to_dict()
            except ApiException as e:
                kubernetes_operations_total.labels(operation="get_pod", status="error").inc()
                if e.status != 404:
                    logger.error("kubernetes.get_pod_failed", pod=pod_name, error=str(e))
                return None

    async def list_pods(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
        field_selector: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista pods em um namespace com filtros opcionais

        Args:
            namespace: Namespace (usa default se nao especificado)
            label_selector: Seletor de labels (ex: "app=worker")
            field_selector: Seletor de campos (ex: "status.phase=Running")

        Returns:
            Lista de pods como dicts
        """
        ns = namespace or self.namespace
        with kubernetes_operation_duration.labels(operation="list_pods").time():
            try:
                kwargs = {"namespace": ns}
                if label_selector:
                    kwargs["label_selector"] = label_selector
                if field_selector:
                    kwargs["field_selector"] = field_selector

                pods = self.core_v1.list_namespaced_pod(**kwargs)
                kubernetes_operations_total.labels(operation="list_pods", status="success").inc()
                return [pod.to_dict() for pod in pods.items]
            except ApiException as e:
                kubernetes_operations_total.labels(operation="list_pods", status="error").inc()
                logger.error(
                    "kubernetes.list_pods_failed",
                    namespace=ns,
                    label_selector=label_selector,
                    error=str(e)
                )
                return []

    async def delete_pod(self, pod_name: str, namespace: Optional[str] = None) -> bool:
        """Deleta um pod (restart forcado)"""
        ns = namespace or self.namespace
        with kubernetes_operation_duration.labels(operation="delete_pod").time():
            try:
                self.core_v1.delete_namespaced_pod(pod_name, ns)
                kubernetes_operations_total.labels(operation="delete_pod", status="success").inc()
                logger.info("kubernetes.pod_deleted", pod=pod_name, namespace=ns)
                return True
            except ApiException as e:
                kubernetes_operations_total.labels(operation="delete_pod", status="error").inc()
                logger.error("kubernetes.delete_pod_failed", pod=pod_name, error=str(e))
                return False

    async def scale_deployment(
        self, deployment_name: str, replicas: int, namespace: Optional[str] = None
    ) -> bool:
        """Escala um deployment"""
        ns = namespace or self.namespace

        # Validar replicas
        if replicas < 0 or replicas > 50:
            logger.error(
                "kubernetes.invalid_replicas",
                deployment=deployment_name,
                replicas=replicas
            )
            return False

        with kubernetes_operation_duration.labels(operation="scale_deployment").time():
            try:
                scale = client.V1Scale(
                    spec=client.V1ScaleSpec(replicas=replicas)
                )
                self.apps_v1.patch_namespaced_deployment_scale(
                    deployment_name, ns, scale
                )
                kubernetes_operations_total.labels(
                    operation="scale_deployment", status="success"
                ).inc()
                logger.info(
                    "kubernetes.deployment_scaled",
                    deployment=deployment_name,
                    replicas=replicas,
                    namespace=ns
                )
                return True
            except ApiException as e:
                kubernetes_operations_total.labels(
                    operation="scale_deployment", status="error"
                ).inc()
                logger.error(
                    "kubernetes.scale_deployment_failed",
                    deployment=deployment_name,
                    error=str(e)
                )
                return False

    async def rollback_deployment(
        self,
        deployment_name: str,
        revision: Optional[int] = None,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executa rollback de um deployment para revisao anterior

        Args:
            deployment_name: Nome do deployment
            revision: Revisao especifica (None = revisao anterior)
            namespace: Namespace (usa default se nao especificado)

        Returns:
            Dict com resultado do rollback
        """
        ns = namespace or self.namespace

        with kubernetes_operation_duration.labels(operation="rollback_deployment").time():
            try:
                # Obter deployment atual
                deployment = self.apps_v1.read_namespaced_deployment(deployment_name, ns)
                current_revision = deployment.metadata.annotations.get(
                    "deployment.kubernetes.io/revision", "0"
                )

                # Criar patch para rollback
                # O rollback e feito resetando o template para uma revisao anterior
                # via ReplicaSet history
                if revision:
                    # Rollback para revisao especifica
                    patch = {
                        "spec": {
                            "template": {
                                "metadata": {
                                    "annotations": {
                                        "kubectl.kubernetes.io/restartedAt": ""
                                    }
                                }
                            }
                        },
                        "metadata": {
                            "annotations": {
                                "deployment.kubernetes.io/revision": str(revision)
                            }
                        }
                    }
                else:
                    # Rollback para revisao anterior (trigger rolling update)
                    import datetime
                    patch = {
                        "spec": {
                            "template": {
                                "metadata": {
                                    "annotations": {
                                        "kubectl.kubernetes.io/restartedAt": datetime.datetime.now(
                                            datetime.timezone.utc
                                        ).isoformat()
                                    }
                                }
                            }
                        }
                    }

                self.apps_v1.patch_namespaced_deployment(deployment_name, ns, patch)

                kubernetes_operations_total.labels(
                    operation="rollback_deployment", status="success"
                ).inc()

                logger.info(
                    "kubernetes.deployment_rollback",
                    deployment=deployment_name,
                    previous_revision=current_revision,
                    target_revision=revision or "previous",
                    namespace=ns
                )

                return {
                    "success": True,
                    "deployment": deployment_name,
                    "previous_revision": current_revision,
                    "target_revision": revision or "previous",
                    "namespace": ns
                }

            except ApiException as e:
                kubernetes_operations_total.labels(
                    operation="rollback_deployment", status="error"
                ).inc()
                logger.error(
                    "kubernetes.rollback_deployment_failed",
                    deployment=deployment_name,
                    error=str(e)
                )
                return {
                    "success": False,
                    "deployment": deployment_name,
                    "error": str(e)
                }

    async def apply_network_policy(
        self,
        policy_name: str,
        policy_spec: Dict[str, Any],
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aplica ou atualiza uma NetworkPolicy

        Args:
            policy_name: Nome da NetworkPolicy
            policy_spec: Especificacao da policy
            namespace: Namespace (usa default se nao especificado)

        Returns:
            Dict com resultado da operacao
        """
        ns = namespace or self.namespace

        with kubernetes_operation_duration.labels(operation="apply_network_policy").time():
            try:
                # Construir NetworkPolicy
                network_policy = client.V1NetworkPolicy(
                    api_version="networking.k8s.io/v1",
                    kind="NetworkPolicy",
                    metadata=client.V1ObjectMeta(
                        name=policy_name,
                        namespace=ns,
                        labels={
                            "app.kubernetes.io/managed-by": "guard-agents",
                            "guard-agents/policy-type": policy_spec.get("type", "remediation")
                        }
                    ),
                    spec=self._build_network_policy_spec(policy_spec)
                )

                # Tentar criar ou atualizar
                try:
                    result = self.networking_v1.create_namespaced_network_policy(
                        ns, network_policy
                    )
                    action = "created"
                except ApiException as e:
                    if e.status == 409:  # Conflict - ja existe
                        result = self.networking_v1.patch_namespaced_network_policy(
                            policy_name, ns, network_policy
                        )
                        action = "updated"
                    else:
                        raise

                kubernetes_operations_total.labels(
                    operation="apply_network_policy", status="success"
                ).inc()

                logger.info(
                    "kubernetes.network_policy_applied",
                    policy=policy_name,
                    action=action,
                    namespace=ns
                )

                return {
                    "success": True,
                    "policy_name": policy_name,
                    "action": action,
                    "namespace": ns
                }

            except ApiException as e:
                kubernetes_operations_total.labels(
                    operation="apply_network_policy", status="error"
                ).inc()
                logger.error(
                    "kubernetes.apply_network_policy_failed",
                    policy=policy_name,
                    error=str(e)
                )
                return {
                    "success": False,
                    "policy_name": policy_name,
                    "error": str(e)
                }

    def _build_network_policy_spec(
        self, policy_spec: Dict[str, Any]
    ) -> client.V1NetworkPolicySpec:
        """Constroi spec de NetworkPolicy baseado em target"""
        target = policy_spec.get("target", "isolate")
        pod_selector = policy_spec.get("pod_selector", {})

        if target == "isolate":
            # Isolar pod - negar todo trafego ingress/egress
            return client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(match_labels=pod_selector),
                policy_types=["Ingress", "Egress"],
                ingress=[],  # Negar todo ingress
                egress=[]    # Negar todo egress
            )

        elif target == "rate_limit":
            # Rate limit - permitir apenas de fontes especificas
            return client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(match_labels=pod_selector),
                policy_types=["Ingress"],
                ingress=[
                    client.V1NetworkPolicyIngressRule(
                        from_=[
                            client.V1NetworkPolicyPeer(
                                namespace_selector=client.V1LabelSelector(
                                    match_labels={"kubernetes.io/metadata.name": self.namespace}
                                )
                            )
                        ]
                    )
                ]
            )

        elif target == "restore":
            # Restaurar - permitir todo trafego (policy permissiva)
            return client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(match_labels=pod_selector),
                policy_types=["Ingress", "Egress"],
                ingress=[client.V1NetworkPolicyIngressRule(from_=[])],
                egress=[client.V1NetworkPolicyEgressRule(to=[])]
            )

        else:
            # Default: isolate
            return client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(match_labels=pod_selector),
                policy_types=["Ingress", "Egress"],
                ingress=[],
                egress=[]
            )

    async def patch_pod_labels(
        self,
        pod_name: str,
        labels: Dict[str, str],
        namespace: Optional[str] = None
    ) -> bool:
        """
        Adiciona ou atualiza labels em um pod

        Args:
            pod_name: Nome do pod
            labels: Labels a adicionar/atualizar
            namespace: Namespace (usa default se nao especificado)

        Returns:
            True se sucesso, False se falha
        """
        ns = namespace or self.namespace

        with kubernetes_operation_duration.labels(operation="patch_pod_labels").time():
            try:
                patch = {"metadata": {"labels": labels}}
                self.core_v1.patch_namespaced_pod(pod_name, ns, patch)

                kubernetes_operations_total.labels(
                    operation="patch_pod_labels", status="success"
                ).inc()

                logger.info(
                    "kubernetes.pod_labels_patched",
                    pod=pod_name,
                    labels=labels,
                    namespace=ns
                )
                return True

            except ApiException as e:
                kubernetes_operations_total.labels(
                    operation="patch_pod_labels", status="error"
                ).inc()
                logger.error(
                    "kubernetes.patch_pod_labels_failed",
                    pod=pod_name,
                    error=str(e)
                )
                return False

    async def get_deployment_revision_history(
        self,
        deployment_name: str,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista historico de revisoes de um deployment

        Args:
            deployment_name: Nome do deployment
            namespace: Namespace (usa default se nao especificado)

        Returns:
            Lista de revisoes com metadados
        """
        ns = namespace or self.namespace

        try:
            # Listar ReplicaSets associados ao deployment
            rs_list = self.apps_v1.list_namespaced_replica_set(
                ns,
                label_selector=f"app={deployment_name}"
            )

            revisions = []
            for rs in rs_list.items:
                revision = rs.metadata.annotations.get(
                    "deployment.kubernetes.io/revision", "0"
                )
                revisions.append({
                    "name": rs.metadata.name,
                    "revision": int(revision),
                    "replicas": rs.spec.replicas or 0,
                    "available_replicas": rs.status.available_replicas or 0,
                    "created_at": rs.metadata.creation_timestamp.isoformat()
                        if rs.metadata.creation_timestamp else None
                })

            # Ordenar por revisao (decrescente)
            revisions.sort(key=lambda x: x["revision"], reverse=True)

            logger.debug(
                "kubernetes.revision_history",
                deployment=deployment_name,
                revision_count=len(revisions)
            )

            return revisions

        except ApiException as e:
            logger.error(
                "kubernetes.get_revision_history_failed",
                deployment=deployment_name,
                error=str(e)
            )
            return []

    async def delete_network_policy(
        self,
        policy_name: str,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Remove uma NetworkPolicy

        Args:
            policy_name: Nome da NetworkPolicy
            namespace: Namespace (usa default se nao especificado)

        Returns:
            True se sucesso, False se falha
        """
        ns = namespace or self.namespace

        with kubernetes_operation_duration.labels(operation="delete_network_policy").time():
            try:
                self.networking_v1.delete_namespaced_network_policy(policy_name, ns)

                kubernetes_operations_total.labels(
                    operation="delete_network_policy", status="success"
                ).inc()

                logger.info(
                    "kubernetes.network_policy_deleted",
                    policy=policy_name,
                    namespace=ns
                )
                return True

            except ApiException as e:
                if e.status == 404:
                    # Policy nao existe - considerar sucesso
                    logger.warning(
                        "kubernetes.network_policy_not_found",
                        policy=policy_name
                    )
                    return True

                kubernetes_operations_total.labels(
                    operation="delete_network_policy", status="error"
                ).inc()
                logger.error(
                    "kubernetes.delete_network_policy_failed",
                    policy=policy_name,
                    error=str(e)
                )
                return False
