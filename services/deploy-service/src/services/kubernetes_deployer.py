"""
Kubernetes Deployer Service.

Gerencia deployments em Kubernetes usando kubectl.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from src.config.settings import settings
from src.models.deployment import (
    DeploymentRequest,
    DeploymentResponse,
    DeploymentStatus,
    HealthCheckResult,
    HealthCheckStatus,
    KubernetesInfo,
    ServiceInfo,
)

logger = structlog.get_logger(__name__)


class KubernetesDeployer:
    """
    Serviço para gerenciar deployments em Kubernetes.
    """

    def __init__(self):
        self.namespace = settings.default_namespace
        self.kubeconfig = settings.kubeconfig_path

    def _kubectl_auth_args(self) -> list[str]:
        """Args de auth do kubectl. Vazio → kubectl usa a config in-cluster (SA do pod);
        evita falhar com `--kubeconfig=/root/.kube/config` inexistente dentro do cluster."""
        return [f"--kubeconfig={self.kubeconfig}"] if self.kubeconfig else []

    async def deploy(self, request: DeploymentRequest) -> DeploymentResponse:
        """
        Cria um deployment no Kubernetes.

        Args:
            request: Deployment request

        Returns:
            Deployment response
        """
        deployment_id = f"{request.service_name}-{request.version}-{int(datetime.now(timezone.utc).timestamp())}"

        logger.info(
            "kubernetes_deploy_start",
            deployment_id=deployment_id,
            service_name=request.service_name,
            namespace=request.namespace,
        )

        try:
            # 1. Criar namespace se não existir
            await self._ensure_namespace(request.namespace)

            # 2. Criar Deployment
            deployment_name = await self._create_deployment(request)

            # 3. Criar Service
            service_url = await self._create_service(request)

            # 4. Criar Ingress se habilitado
            ingress_url = ""
            if request.ingress and request.ingress.enabled:
                ingress_url = await self._create_ingress(request)

            # 5. Aguardar rollout
            await self._wait_for_rollout(deployment_name, request.namespace)

            # 6. Verificar health checks
            health_checks = await self._verify_health_checks(
                deployment_name, request.namespace, request.health_checks
            )

            # 7. Obter status final
            k8s_info = await self._get_deployment_info(deployment_name, request.namespace)

            logger.info(
                "kubernetes_deploy_complete",
                deployment_id=deployment_id,
                deployment_name=deployment_name,
                status="deployed",
            )

            return DeploymentResponse(
                deployment_id=deployment_id,
                plan_id=request.plan_id,
                service_name=request.service_name,
                version=request.version,
                status=DeploymentStatus.DEPLOYED,
                kubernetes=k8s_info,
                service=ServiceInfo(
                    name=request.service_name,
                    namespace=request.namespace,
                    url=service_url,
                    ingress_url=ingress_url,
                ),
                health_checks=health_checks,
                rollback_enabled=settings.rollback_enabled,
            )

        except Exception as e:
            logger.exception(
                "kubernetes_deploy_failed",
                deployment_id=deployment_id,
                error=str(e),
            )
            return DeploymentResponse(
                deployment_id=deployment_id,
                plan_id=request.plan_id,
                service_name=request.service_name,
                version=request.version,
                status=DeploymentStatus.FAILED,
                error=str(e),
            )

    async def rollback(self, deployment_name: str, namespace: str) -> dict[str, Any]:
        """
        Executa rollback de um deployment.

        Args:
            deployment_name: Nome do deployment
            namespace: Namespace Kubernetes

        Returns:
            Resultado do rollback
        """
        logger.warning(
            "kubernetes_rollback_start",
            deployment_name=deployment_name,
            namespace=namespace,
        )

        cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "rollout",
            "undo",
            f"deployment/{deployment_name}",
            f"-n={namespace}",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error = stderr.decode()
            logger.error(
                "kubernetes_rollback_failed",
                deployment_name=deployment_name,
                error=error,
            )
            raise RuntimeError(f"Rollback failed: {error}")

        # Aguardar rollback completar
        await self._wait_for_rollout(deployment_name, namespace)

        logger.info(
            "kubernetes_rollback_complete",
            deployment_name=deployment_name,
        )

        return {
            "deployment_name": deployment_name,
            "rollback_status": "completed",
        }

    async def _ensure_namespace(self, namespace: str):
        """Garante que o namespace existe."""
        cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "create",
            "namespace",
            namespace,
            "--dry-run=client",
            "-o=yaml",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()

        # Aplicar manifest
        apply_cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "apply",
            "-f=-",
        ]

        process = await asyncio.create_subprocess_exec(
            *apply_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await process.communicate(input=stdout)

    async def _create_deployment(self, request: DeploymentRequest) -> str:
        """Cria o Deployment no Kubernetes."""
        deployment_name = f"{request.service_name}-{request.version}"

        resources = request.resources or {}
        cpu = resources.cpu or settings.default_cpu
        memory = resources.memory or settings.default_memory
        cpu_limit = (resources.limits or {}).get("cpu", settings.default_cpu_limit)
        memory_limit = (resources.limits or {}).get("memory", settings.default_memory_limit)

        health_checks = request.health_checks or {}
        liveness_path = health_checks.liveness_path or settings.liveness_path
        readiness_path = health_checks.readiness_path or settings.readiness_path
        initial_delay = health_checks.initial_delay or settings.health_check_delay
        period = health_checks.period or settings.health_check_period

        deployment_manifest = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "namespace": request.namespace,
                "labels": {
                    "app": request.service_name,
                    # Gatekeeper must-have-app-label-all exige app.kubernetes.io/name
                    "app.kubernetes.io/name": request.service_name,
                    "version": request.version,
                    "plan_id": request.plan_id,
                },
            },
            "spec": {
                "replicas": request.replicas,
                "selector": {"matchLabels": {"app": request.service_name}},
                "template": {
                    "metadata": {
                        "labels": {
                            "app": request.service_name,
                            # Gatekeeper must-have-app-label-all exige app.kubernetes.io/name
                            "app.kubernetes.io/name": request.service_name,
                            "version": request.version,
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": request.service_name,
                                "image": request.container_image,
                                "ports": [{"containerPort": 8080}],
                                "resources": {
                                    "requests": {
                                        "cpu": cpu,
                                        "memory": memory,
                                    },
                                    "limits": {
                                        "cpu": cpu_limit,
                                        "memory": memory_limit,
                                    },
                                },
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": liveness_path,
                                        "port": 8080,
                                    },
                                    "initialDelaySeconds": initial_delay,
                                    "periodSeconds": period,
                                },
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": readiness_path,
                                        "port": 8080,
                                    },
                                    "initialDelaySeconds": initial_delay,
                                    "periodSeconds": period,
                                },
                            }
                        ]
                    },
                },
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": 1,
                        "maxUnavailable": 0,
                    },
                },
                "revisionHistoryLimit": settings.rollback_history_limit,
            },
        }

        # Aplicar deployment
        await self._kubectl_apply(deployment_manifest)

        return deployment_name

    async def _create_service(self, request: DeploymentRequest) -> str:
        """Cria o Service no Kubernetes."""
        service_name = request.service_name

        service_manifest = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": service_name,
                "namespace": request.namespace,
                "labels": {
                    "app": request.service_name,
                    "app.kubernetes.io/name": request.service_name,
                },
            },
            "spec": {
                "type": "ClusterIP",
                "selector": {"app": request.service_name},
                "ports": [
                    {
                        "name": "http",
                        "port": 80,
                        "targetPort": 8080,
                        "protocol": "TCP",
                    }
                ],
            },
        }

        await self._kubectl_apply(service_manifest)

        return f"http://{service_name}.{request.namespace}.svc.cluster.local:80"

    async def _create_ingress(self, request: DeploymentRequest) -> str:
        """Cria o Ingress no Kubernetes."""
        ingress = request.ingress

        ingress_manifest = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{request.service_name}-ingress",
                "namespace": request.namespace,
                "annotations": ingress.annotations or {},
            },
            "spec": {
                "ingressClassName": "nginx",
                "rules": [
                    {
                        "host": ingress.host,
                        "http": {
                            "paths": [
                                {
                                    "path": ingress.path,
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": request.service_name,
                                            "port": {"number": 80},
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        }

        if ingress.tls_enabled:
            ingress_manifest["spec"]["tls"] = [
                {"hosts": [ingress.host], "secretName": f"{request.service_name}-tls"}
            ]

        await self._kubectl_apply(ingress_manifest)

        scheme = "https" if ingress.tls_enabled else "http"
        return f"{scheme}://{ingress.host}{ingress.path}"

    async def _wait_for_rollout(self, deployment_name: str, namespace: str, timeout: int = 600):
        """Aguarda o rollout completar."""
        cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "rollout",
            "status",
            f"deployment/{deployment_name}",
            f"-n={namespace}",
            "--timeout={timeout}s",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error = stderr.decode()
            raise RuntimeError(f"Rollout failed: {error}")

    async def _verify_health_checks(
        self,
        deployment_name: str,
        namespace: str,
        health_checks_spec: Any,
    ) -> HealthCheckResult:
        """Verifica os health checks."""
        # Obter pods
        cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "get",
            "pods",
            f"-l=app={deployment_name}",
            f"-n={namespace}",
            "-o=json",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()
        pods_data = json.loads(stdout.decode())

        ready_pods = 0
        total_pods = len(pods_data.get("items", []))

        for pod in pods_data.get("items", []):
            for condition in pod.get("status", {}).get("conditions", []):
                if condition.get("type") == "Ready" and condition.get("status") == "True":
                    ready_pods += 1

        # Determinar status dos health checks
        liveness = (
            HealthCheckStatus.HEALTHY if ready_pods == total_pods else HealthCheckStatus.PENDING
        )
        readiness = (
            HealthCheckStatus.HEALTHY if ready_pods == total_pods else HealthCheckStatus.PENDING
        )

        return HealthCheckResult(
            liveness=liveness,
            readiness=readiness,
            custom={"ready_pods": ready_pods, "total_pods": total_pods},
        )

    async def _get_deployment_info(self, deployment_name: str, namespace: str) -> KubernetesInfo:
        """Obtém informações do deployment."""
        cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "get",
            f"deployment/{deployment_name}",
            f"-n={namespace}",
            "-o=json",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()
        deployment_data = json.loads(stdout.decode())

        spec = deployment_data.get("spec", {})
        status = deployment_data.get("status", {})

        return KubernetesInfo(
            deployment_name=deployment_name,
            namespace=namespace,
            replicas=spec.get("replicas", 0),
            available_replicas=status.get("availableReplicas", 0),
            updated_replicas=status.get("updatedReplicas", 0),
            ready_replicas=status.get("readyReplicas", 0),
        )

    async def _kubectl_apply(self, manifest: dict[str, Any]):
        """Aplica um manifest no Kubernetes."""
        manifest_yaml = json.dumps(manifest)
        cmd = [
            "kubectl",
            *self._kubectl_auth_args(),
            "apply",
            "-f=-",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate(input=manifest_yaml.encode())

        if process.returncode != 0:
            error = stderr.decode()
            raise RuntimeError(f"kubectl apply failed: {error}")
