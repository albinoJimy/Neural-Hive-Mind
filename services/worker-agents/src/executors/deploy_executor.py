import asyncio
import contextlib
import datetime as _dt
from typing import Any

# Python 3.11+ expõe datetime.UTC; em 3.10 cai para timezone.utc (mesmo objeto).
_UTC = getattr(_dt, "UTC", _dt.timezone.utc)  # noqa: UP017

from src.clients.argocd_client import (
    ApplicationCreateRequest,
    ApplicationDestination,
    ApplicationMetadata,
    ApplicationSource,
    ApplicationSpec,
    ArgoCDAPIError,
    ArgoCDClient,
    ArgoCDTimeoutError,
    SyncPolicy,
)
from src.clients.flux_client import (
    FluxAPIError,
    FluxClient,
    FluxTimeoutError,
    KustomizationMetadata,
    KustomizationRequest,
    KustomizationSpec,
    SourceReference,
)

from neural_hive_observability import get_tracer

from .base_executor import BaseTaskExecutor


class _NoopSpan:
    """Span no-op para quando o tracer não está inicializado (ex.: testes)."""

    def set_attribute(self, *args, **kwargs):
        _ = (args, kwargs)  # no-op: span desativado


class DeployExecutor(BaseTaskExecutor):
    """Executor para task_type=DEPLOY com suporte a ArgoCD, Flux e caminho
    imperativo (kubernetes_asyncio) com namespace efémero + reconciliação."""

    def get_task_type(self) -> str:
        return "DEPLOY"

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client=None,
        metrics=None,
        argocd_client: ArgoCDClient | None = None,
        flux_client: FluxClient | None = None,
    ):
        super().__init__(
            config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics
        )
        self.argocd_client = argocd_client
        self.flux_client = flux_client
        self.argocd_url: str | None = getattr(config, "argocd_url", None)
        self.argocd_token: str | None = getattr(config, "argocd_token", None)
        # Clientes Kubernetes do caminho imperativo (lazy init).
        self._core_api = None
        self._apps_api = None
        self._k8s_client = None

    async def execute(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """Executar tarefa de DEPLOY com suporte a ArgoCD e Flux"""
        self.validate_ticket(ticket)

        ticket_id = ticket.get("ticket_id")
        parameters = ticket.get("parameters", {})

        tracer = get_tracer()
        span_cm = (
            tracer.start_as_current_span("task_execution")
            if tracer is not None
            else contextlib.nullcontext(_NoopSpan())
        )
        with span_cm as span:
            span.set_attribute("neural.hive.task_id", ticket_id)
            span.set_attribute("neural.hive.task_type", self.get_task_type())
            span.set_attribute("neural.hive.executor", self.__class__.__name__)

            self.log_execution(ticket_id, "deploy_started", parameters=parameters)

            namespace = parameters.get("namespace", "default")
            deployment_name = parameters.get("deployment_name", f"deploy-{ticket_id[:8]}")
            image = parameters.get("image", "latest")
            replicas = int(parameters.get("replicas", 1))
            sync_strategy = parameters.get("sync_strategy", "auto")
            poll_timeout = parameters.get("timeout_seconds", 600)
            poll_interval = parameters.get("poll_interval", 5)
            provider = parameters.get("provider", "argocd")

            # Fluxo ArgoCD com cliente dedicado
            if provider == "argocd" and self.argocd_client:
                return await self._execute_argocd(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    sync_strategy=sync_strategy,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span,
                )

            # Fluxo Flux com cliente dedicado
            if provider == "flux" and self.flux_client:
                return await self._execute_flux(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span,
                )

            # Caminho imperativo real: namespace efémero + Deployment + reconciliação.
            # (provider explícito "imperative"/"helm", ou default quando não há
            # argocd/flux client mas kubernetes_asyncio está disponível.)
            if provider in ("imperative", "helm"):
                return await self._execute_imperative(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span,
                )

            # Fallback: ArgoCD legado via URL direta (backward compatibility)
            if self.argocd_url and getattr(self.config, "argocd_enabled", False):
                return await self._execute_argocd_legacy(
                    ticket_id=ticket_id,
                    parameters=parameters,
                    deployment_name=deployment_name,
                    namespace=namespace,
                    image=image,
                    replicas=replicas,
                    sync_strategy=sync_strategy,
                    poll_timeout=poll_timeout,
                    poll_interval=poll_interval,
                    span=span,
                )

            # Provider GitOps pedido mas client não configurado: fallback EXPLÍCITO
            # (marcado) para o caminho imperativo — nunca silencioso (§5.4).
            if provider in ("argocd", "flux"):
                self.log_execution(
                    ticket_id,
                    "deploy_provider_unavailable_fallback_imperative",
                    level="warning",
                    degraded=True,
                    requested_provider=provider,
                    reason="gitops_client_not_configured",
                )

            # Nenhum provider GitOps configurado: tenta caminho imperativo real.
            # (Caminho Real First-Class §5.4: marcar+medir+falhar — NUNCA simular.)
            return await self._execute_imperative(
                ticket_id=ticket_id,
                parameters=parameters,
                deployment_name=deployment_name,
                namespace=namespace,
                image=image,
                replicas=replicas,
                poll_timeout=poll_timeout,
                poll_interval=poll_interval,
                span=span,
            )

    async def _execute_argocd(
        self,
        ticket_id: str,
        parameters: dict[str, Any],
        deployment_name: str,
        namespace: str,
        image: str,
        replicas: int,
        sync_strategy: str,
        poll_timeout: int,
        poll_interval: int,
        span,
    ) -> dict[str, Any]:
        """Executa deploy via cliente ArgoCD dedicado"""
        self.log_execution(ticket_id, "deploy_argocd_started", deployment_name=deployment_name)

        start_time = asyncio.get_event_loop().time()

        try:
            helm_params = None
            if image or replicas:
                helm_params = {
                    "parameters": [
                        {"name": "image.repository", "value": image},
                        {"name": "replicaCount", "value": str(replicas)},
                    ]
                }

            sync_policy = None
            if sync_strategy == "auto":
                sync_policy = SyncPolicy(automated={"prune": True, "selfHeal": True})

            request = ApplicationCreateRequest(
                metadata=ApplicationMetadata(
                    name=deployment_name,
                    namespace=parameters.get("argocd_namespace", "argocd"),
                    labels=parameters.get("labels"),
                    annotations=parameters.get("annotations"),
                ),
                spec=ApplicationSpec(
                    project=parameters.get("project", "default"),
                    source=ApplicationSource(
                        repoURL=parameters.get("repo_url", ""),
                        path=parameters.get("chart_path", "."),
                        targetRevision=parameters.get("revision", "HEAD"),
                        helm=helm_params,
                    ),
                    destination=ApplicationDestination(
                        server=parameters.get("cluster_server", "https://kubernetes.default.svc"),
                        namespace=namespace,
                    ),
                    syncPolicy=sync_policy,
                ),
            )

            app_name = await self.argocd_client.create_application(request)

            if self.metrics and hasattr(self.metrics, "argocd_api_calls_total"):
                self.metrics.argocd_api_calls_total.labels(method="create", status="success").inc()

            self.log_execution(ticket_id, "deploy_argocd_created", app_name=app_name)

            status = await self.argocd_client.wait_for_health(
                app_name=app_name, poll_interval=poll_interval, timeout=poll_timeout
            )

            if self.metrics and hasattr(self.metrics, "argocd_api_calls_total"):
                self.metrics.argocd_api_calls_total.labels(method="get", status="success").inc()

            duration_seconds = asyncio.get_event_loop().time() - start_time

            result = {
                "success": True,
                "output": {
                    "deployment_id": app_name,
                    "status": status.health.status.lower(),
                    "sync_status": status.sync.status,
                    "replicas": replicas,
                    "namespace": namespace,
                    "revision": status.sync.revision,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "argocd",
                    "simulated": False,
                    "duration_seconds": duration_seconds,
                },
                "logs": [
                    "Deployment started via ArgoCD client",
                    f"Application {app_name} created",
                    f"Health status: {status.health.status}",
                    f"Sync status: {status.sync.status}",
                ],
            }

            self.log_execution(
                ticket_id, "deploy_completed", deployment_id=app_name, status=status.health.status
            )

            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="success").inc()
            if self.metrics and hasattr(self.metrics, "deploy_duration_seconds"):
                self.metrics.deploy_duration_seconds.labels(stage="argocd").observe(
                    duration_seconds
                )

            span.set_attribute("neural.hive.execution_status", "success")
            return result

        except ArgoCDTimeoutError as e:
            self.log_execution(
                ticket_id,
                "deploy_argocd_timeout",
                level="warning",
                deployment_id=deployment_name,
                error=str(e),
            )
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="timeout").inc()
            span.set_attribute("neural.hive.execution_status", "timeout")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "timeout",
                    "replicas": replicas,
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "argocd",
                    "simulated": False,
                    "duration_seconds": poll_timeout,
                },
                "logs": [
                    "Deployment started via ArgoCD client",
                    f"Timed out after {poll_timeout}s: {e}",
                ],
            }

        except ArgoCDAPIError as e:
            self.log_execution(
                ticket_id,
                "deploy_argocd_error",
                level="error",
                deployment_id=deployment_name,
                error=str(e),
                status_code=e.status_code,
            )
            if self.metrics and hasattr(self.metrics, "argocd_api_calls_total"):
                self.metrics.argocd_api_calls_total.labels(method="unknown", status="error").inc()
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="failed").inc()
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "error",
                    "replicas": replicas,
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "argocd",
                    "simulated": False,
                    "error_code": e.status_code,
                },
                "logs": ["Deployment started via ArgoCD client", f"Failed with error: {e}"],
            }

        except Exception as exc:
            self.log_execution(
                ticket_id,
                "deploy_argocd_unexpected_error",
                level="error",
                deployment_id=deployment_name,
                error=str(exc),
            )
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="failed").inc()
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "error",
                    "replicas": replicas,
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "argocd",
                    "simulated": False,
                },
                "logs": ["Deployment started via ArgoCD client", f"Unexpected error: {exc}"],
            }

    async def _execute_flux(
        self,
        ticket_id: str,
        parameters: dict[str, Any],
        deployment_name: str,
        namespace: str,
        poll_timeout: int,
        poll_interval: int,
        span,
    ) -> dict[str, Any]:
        """Executa deploy via cliente Flux dedicado"""
        self.log_execution(ticket_id, "deploy_flux_started", deployment_name=deployment_name)

        start_time = asyncio.get_event_loop().time()

        try:
            request = KustomizationRequest(
                metadata=KustomizationMetadata(
                    name=deployment_name,
                    namespace=parameters.get("flux_namespace", "flux-system"),
                    labels=parameters.get("labels"),
                    annotations=parameters.get("annotations"),
                ),
                spec=KustomizationSpec(
                    interval=parameters.get("interval", "5m"),
                    path=parameters.get("path", "./"),
                    prune=parameters.get("prune", True),
                    sourceRef=SourceReference(
                        kind=parameters.get("source_kind", "GitRepository"),
                        name=parameters.get("source_name", ""),
                        namespace=parameters.get("source_namespace"),
                    ),
                    targetNamespace=namespace,
                    timeout=parameters.get("apply_timeout"),
                    force=parameters.get("force", False),
                    wait=parameters.get("wait", True),
                ),
            )

            kust_name = await self.flux_client.create_kustomization(request)

            if self.metrics and hasattr(self.metrics, "flux_api_calls_total"):
                self.metrics.flux_api_calls_total.labels(method="create", status="success").inc()

            self.log_execution(ticket_id, "deploy_flux_created", kustomization_name=kust_name)

            status = await self.flux_client.wait_for_ready(
                name=kust_name,
                namespace=parameters.get("flux_namespace", "flux-system"),
                poll_interval=poll_interval,
                timeout=poll_timeout,
            )

            duration_seconds = asyncio.get_event_loop().time() - start_time

            result = {
                "success": True,
                "output": {
                    "deployment_id": kust_name,
                    "status": "ready" if status.ready else "not_ready",
                    "namespace": namespace,
                    "revision": status.lastAppliedRevision,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "flux",
                    "simulated": False,
                    "duration_seconds": duration_seconds,
                },
                "logs": [
                    "Deployment started via Flux client",
                    f"Kustomization {kust_name} created",
                    f"Ready: {status.ready}",
                    f"Revision: {status.lastAppliedRevision}",
                ],
            }

            self.log_execution(
                ticket_id,
                "deploy_completed",
                deployment_id=kust_name,
                status="ready" if status.ready else "not_ready",
            )

            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="success").inc()
            if self.metrics and hasattr(self.metrics, "deploy_duration_seconds"):
                self.metrics.deploy_duration_seconds.labels(stage="flux").observe(duration_seconds)

            span.set_attribute("neural.hive.execution_status", "success")
            return result

        except FluxTimeoutError as e:
            self.log_execution(
                ticket_id,
                "deploy_flux_timeout",
                level="warning",
                deployment_id=deployment_name,
                error=str(e),
            )
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="timeout").inc()
            span.set_attribute("neural.hive.execution_status", "timeout")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "timeout",
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "flux",
                    "simulated": False,
                    "duration_seconds": poll_timeout,
                },
                "logs": [
                    "Deployment started via Flux client",
                    f"Timed out after {poll_timeout}s: {e}",
                ],
            }

        except FluxAPIError as e:
            self.log_execution(
                ticket_id,
                "deploy_flux_error",
                level="error",
                deployment_id=deployment_name,
                error=str(e),
                status_code=e.status_code,
            )
            if self.metrics and hasattr(self.metrics, "flux_api_calls_total"):
                self.metrics.flux_api_calls_total.labels(method="unknown", status="error").inc()
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="failed").inc()
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "error",
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "flux",
                    "simulated": False,
                    "error_code": e.status_code,
                },
                "logs": ["Deployment started via Flux client", f"Failed with error: {e}"],
            }

        except Exception as exc:
            self.log_execution(
                ticket_id,
                "deploy_flux_unexpected_error",
                level="error",
                deployment_id=deployment_name,
                error=str(exc),
            )
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="failed").inc()
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "error",
                    "namespace": namespace,
                },
                "metadata": {"executor": "DeployExecutor", "provider": "flux", "simulated": False},
                "logs": ["Deployment started via Flux client", f"Unexpected error: {exc}"],
            }

    async def _execute_argocd_legacy(
        self,
        ticket_id: str,
        parameters: dict[str, Any],
        deployment_name: str,
        namespace: str,
        image: str,
        replicas: int,
        sync_strategy: str,
        poll_timeout: int,
        poll_interval: int,
        span,
    ) -> dict[str, Any]:
        """Fluxo legado de ArgoCD via httpx direto (backward compatibility)"""
        import httpx

        try:
            headers = {}
            if self.argocd_token:
                headers["Authorization"] = f"Bearer {self.argocd_token}"

            spec = {
                "project": "default",
                "source": {
                    "repoURL": parameters.get("repo_url", ""),
                    "path": parameters.get("chart_path", "."),
                    "targetRevision": parameters.get("revision", "HEAD"),
                    "helm": {
                        "parameters": [
                            {"name": "image.repository", "value": image},
                            {"name": "replicaCount", "value": str(replicas)},
                        ]
                    },
                },
                "destination": {
                    "server": parameters.get("cluster_server", "https://kubernetes.default.svc"),
                    "namespace": namespace,
                },
            }

            if sync_strategy == "auto":
                spec["syncPolicy"] = {"automated": {"prune": True, "selfHeal": True}}

            payload = {"metadata": {"name": deployment_name, "namespace": namespace}, "spec": spec}

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.argocd_url}/api/v1/applications", json=payload, headers=headers
                )
                response.raise_for_status()

                if self.metrics and hasattr(self.metrics, "argocd_api_calls_total"):
                    self.metrics.argocd_api_calls_total.labels(
                        method="create", status="success"
                    ).inc()

                attempts = int(poll_timeout / poll_interval)
                for attempt in range(attempts):
                    status_resp = await client.get(
                        f"{self.argocd_url}/api/v1/applications/{deployment_name}", headers=headers
                    )
                    status_resp.raise_for_status()
                    if self.metrics and hasattr(self.metrics, "argocd_api_calls_total"):
                        self.metrics.argocd_api_calls_total.labels(
                            method="get", status="success"
                        ).inc()
                    health = status_resp.json().get("status", {}).get("health", {}).get("status")
                    if health in ["Healthy", "Deployed"]:
                        duration_seconds = attempt * poll_interval
                        result = {
                            "success": True,
                            "output": {
                                "deployment_id": deployment_name,
                                "status": health.lower(),
                                "replicas": replicas,
                                "namespace": namespace,
                            },
                            "metadata": {
                                "executor": "DeployExecutor",
                                "provider": "argocd_legacy",
                                "simulated": False,
                                "duration_seconds": duration_seconds,
                            },
                            "logs": [
                                "Deployment started via ArgoCD (legacy)",
                                f"Application {deployment_name} created",
                                f"Health status: {health}",
                            ],
                        }
                        self.log_execution(
                            ticket_id,
                            "deploy_completed",
                            deployment_id=deployment_name,
                            status=health,
                        )
                        if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                            self.metrics.deploy_tasks_executed_total.labels(status="success").inc()
                        if self.metrics and hasattr(self.metrics, "deploy_duration_seconds"):
                            self.metrics.deploy_duration_seconds.labels(
                                stage="health_check"
                            ).observe(duration_seconds)
                        span.set_attribute("neural.hive.execution_status", "success")
                        return result
                    await asyncio.sleep(poll_interval)

            self.log_execution(
                ticket_id, "deploy_argocd_timeout", level="warning", deployment_id=deployment_name
            )
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="timeout").inc()
            span.set_attribute("neural.hive.execution_status", "timeout")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "timeout",
                    "replicas": replicas,
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "argocd_legacy",
                    "simulated": False,
                    "duration_seconds": poll_timeout,
                },
                "logs": [
                    "Deployment started via ArgoCD (legacy)",
                    f"Timed out after {poll_timeout}s",
                ],
            }
        except Exception as exc:
            self.log_execution(ticket_id, "deploy_argocd_error", level="error", error=str(exc))
            if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
                self.metrics.deploy_tasks_executed_total.labels(status="failed").inc()
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "error",
                    "replicas": replicas,
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "argocd_legacy",
                    "simulated": False,
                },
                "logs": ["Deployment started via ArgoCD (legacy)", f"Failed with error: {exc}"],
            }

    def _metric_deploy_status(self, status: str) -> None:
        """Incrementa deploy_tasks_executed_total{status} se métricas existirem."""
        if self.metrics and hasattr(self.metrics, "deploy_tasks_executed_total"):
            self.metrics.deploy_tasks_executed_total.labels(status=status).inc()

    def _metric_real_path_unavailable(self) -> None:
        """Incrementa real_path_unavailable_total para o caminho imperativo."""
        if self.metrics and hasattr(self.metrics, "real_path_unavailable_total"):
            self.metrics.real_path_unavailable_total.labels(
                executor="DeployExecutor", task_type=self.get_task_type()
            ).inc()

    async def _init_k8s_clients(self) -> None:
        """Inicializa clientes Kubernetes para o caminho imperativo (lazy).

        Segue o padrão de ``flux_client``: in-cluster por omissão, fallback para
        kubeconfig local. Levanta ImportError se ``kubernetes_asyncio`` ausente,
        para que o chamador marque ``real_path_unavailable`` (§5.4).
        """
        if self._core_api is not None and self._apps_api is not None:
            return

        from kubernetes_asyncio import client, config
        from kubernetes_asyncio.client import ApiClient

        try:
            config.load_incluster_config()
        except Exception:  # fallback explícito p/ dev local
            await config.load_kube_config()

        self._k8s_client = ApiClient()
        self._core_api = client.CoreV1Api(self._k8s_client)
        self._apps_api = client.AppsV1Api(self._k8s_client)

    async def close(self) -> None:
        """Fecha o ApiClient kubernetes_asyncio (chamar no shutdown do worker).

        O ApiClient é um singleton reutilizado entre deploys (não há leak
        por-execução); este método liberta a ClientSession subjacente no
        encerramento gracioso, à semelhança de ``flux_client.close()``.
        """
        if self._k8s_client is not None:
            with contextlib.suppress(Exception):
                await self._k8s_client.close()
            self._k8s_client = None
            self._core_api = None
            self._apps_api = None

    def _build_namespace_manifest(
        self, namespace: str, app: str, ttl_seconds: int
    ) -> dict[str, Any]:
        """Manifesto de namespace efémero com labels Gatekeeper + TTL.

        Os labels TTL (`neural-hive.io/ttl-seconds`, `neural-hive.io/created-at`)
        permitem que um reaper externo faça o GC do namespace após expirar — a
        evidência de reconciliação persiste até lá para verificação.
        """
        return {
            "metadata": {
                "name": namespace,
                "labels": {
                    # Gatekeeper exige app/app.kubernetes.io/name.
                    "app": app,
                    "app.kubernetes.io/name": app,
                    "app.kubernetes.io/managed-by": "neural-hive-worker",
                    # TTL para GC externo (reaper). created-at em epoch seconds —
                    # ISO (':'/'+') é VALOR DE LABEL INVÁLIDO no K8s (422); o reaper
                    # calcula a expiração de created-at-epoch + ttl-seconds.
                    "neural-hive.io/ephemeral": "true",
                    "neural-hive.io/ttl-seconds": str(ttl_seconds),
                    "neural-hive.io/created-at": str(int(_dt.datetime.now(_UTC).timestamp())),
                },
            }
        }

    def _build_resource_quota_manifest(self, app: str) -> dict[str, Any]:
        """ResourceQuota modesta — cluster sobre-comprometido (ver MEMORY)."""
        return {
            "metadata": {
                "name": "cr-ephemeral-quota",
                "labels": {"app": app, "app.kubernetes.io/name": app},
            },
            "spec": {
                "hard": {
                    "limits.cpu": "2",
                    "limits.memory": "2Gi",
                    "requests.cpu": "1",
                    "requests.memory": "1Gi",
                }
            },
        }

    def _build_deployment_manifest(
        self, deployment_name: str, namespace: str, image: str, replicas: int
    ) -> dict[str, Any]:
        """Deployment Gatekeeper-compliant: labels no pod template + resources."""
        labels = {"app": deployment_name, "app.kubernetes.io/name": deployment_name}
        return {
            "metadata": {"name": deployment_name, "namespace": namespace, "labels": labels},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": deployment_name}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "containers": [
                            {
                                "name": deployment_name,
                                "image": image,
                                "resources": {
                                    "requests": {"cpu": "50m", "memory": "64Mi"},
                                    "limits": {"cpu": "200m", "memory": "128Mi"},
                                },
                            }
                        ]
                    },
                },
            },
        }

    @staticmethod
    def _build_reconciled_result(
        deployment_name: str,
        namespace: str,
        image: str,
        available: int,
        replicas: int,
        ephemeral: bool,
        ttl_seconds: int,
        duration_seconds: float,
    ) -> dict[str, Any]:
        """Constrói o resultado de sucesso com evidência de reconciliação real."""
        return {
            "success": True,
            "output": {
                "resource": f"{namespace}/{deployment_name}",
                "deployment_id": deployment_name,
                "status": "reconciled",
                "healthy": True,
                "available_replicas": available,
                "replicas": replicas,
                "namespace": namespace,
                "image": image,
            },
            "metadata": {
                "executor": "DeployExecutor",
                "provider": "imperative",
                "simulated": False,
                "ephemeral": ephemeral,
                "ttl_seconds": ttl_seconds,
                "duration_seconds": duration_seconds,
            },
            "logs": [
                "Deployment imperativo iniciado",
                f"Namespace efémero {namespace} (TTL={ttl_seconds}s)",
                f"Deployment {deployment_name} reconciliado "
                f"({available}/{replicas} disponíveis)",
            ],
        }

    async def _provision_resources(
        self,
        ticket_id: str,
        deployment_name: str,
        namespace: str,
        image: str,
        replicas: int,
        ephemeral: bool,
        ttl_seconds: int,
    ) -> None:
        """Cria namespace efémero + ResourceQuota (se ephemeral) e o Deployment.

        Idempotente: 409 AlreadyExists (re-execução do mesmo ticket / retry Temporal)
        é tolerado — o recurso já existe e a reconciliação prossegue.
        """
        if ephemeral:
            ns_manifest = self._build_namespace_manifest(namespace, deployment_name, ttl_seconds)
            await self._create_idempotent(
                self._core_api.create_namespace(body=ns_manifest), ticket_id, "namespace"
            )
            quota_manifest = self._build_resource_quota_manifest(deployment_name)
            await self._create_idempotent(
                self._core_api.create_namespaced_resource_quota(
                    namespace=namespace, body=quota_manifest
                ),
                ticket_id,
                "resourcequota",
            )
            self.log_execution(
                ticket_id,
                "deploy_namespace_created",
                namespace=namespace,
                ttl_seconds=ttl_seconds,
            )

        dep_manifest = self._build_deployment_manifest(deployment_name, namespace, image, replicas)
        await self._create_idempotent(
            self._apps_api.create_namespaced_deployment(namespace=namespace, body=dep_manifest),
            ticket_id,
            "deployment",
        )
        self.log_execution(ticket_id, "deploy_deployment_created", deployment_name=deployment_name)

    async def _create_idempotent(self, create_coro, ticket_id: str, resource: str) -> None:
        """Aguarda um create K8s, tolerando 409 AlreadyExists (idempotência)."""
        try:
            await create_coro
        except Exception as exc:  # 409 vs erro real distinguido por status
            if getattr(exc, "status", None) == 409:
                self.log_execution(
                    ticket_id, "deploy_resource_already_exists", resource=resource, level="info"
                )
                return
            raise

    async def _wait_for_reconciliation(
        self,
        deployment_name: str,
        namespace: str,
        replicas: int,
        deadline: float,
        poll_interval: int,
    ) -> tuple[bool, int]:
        """Poll do Deployment até available/ready_replicas >= replicas (ou deadline).

        Devolve ``(reconciled, available_replicas)``. Não reconciliar até ao
        deadline NÃO é sucesso — o chamador devolve FAILED (nunca verde).
        """
        available = 0
        while asyncio.get_event_loop().time() < deadline:
            status_obj = await self._apps_api.read_namespaced_deployment_status(
                name=deployment_name, namespace=namespace
            )
            status = getattr(status_obj, "status", None)
            available = getattr(status, "available_replicas", None) or 0
            ready = getattr(status, "ready_replicas", None) or 0
            if available >= replicas or ready >= replicas:
                return True, max(available, ready)
            await asyncio.sleep(poll_interval)
        return False, available

    async def _execute_imperative(
        self,
        ticket_id: str,
        parameters: dict[str, Any],
        deployment_name: str,
        namespace: str,
        image: str,
        replicas: int,
        poll_timeout: int,
        poll_interval: int,
        span,
    ) -> dict[str, Any]:
        """Deploy imperativo real via kubernetes_asyncio.

        Cria namespace efémero (dev) com ResourceQuota, aplica um Deployment
        Gatekeeper-compliant e faz poll do status até available_replicas atingir
        o número pedido. Devolve evidência de reconciliação que satisfaz o gate
        ``ExecutionEngine._evidence_deploy`` (Task 1). Sem reconciliação no
        timeout, ou sem kubernetes_asyncio/RBAC → FAILED (nunca verde simulado).
        """
        self.log_execution(ticket_id, "deploy_imperative_started", deployment_name=deployment_name)
        start_time = asyncio.get_event_loop().time()

        # 1) Inicialização do caminho real — ausência marca real_path_unavailable.
        try:
            await self._init_k8s_clients()
        except Exception as exc:  # ImportError ou init falhado
            self.log_execution(
                ticket_id,
                "deploy_real_path_unavailable",
                level="error",
                degraded=True,
                reason="kubernetes_asyncio_unavailable",
                error=str(exc),
            )
            self._metric_real_path_unavailable()
            self._metric_deploy_status("failed")
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "error": "kubernetes_asyncio_unavailable",
                    "namespace": namespace,
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "imperative",
                    "simulated": False,
                    "real_path_unavailable": True,
                },
                "logs": [
                    "Deployment imperativo iniciado",
                    f"Caminho real indisponível: {exc}",
                    "Ticket marcado como FAILED (sem fallback simulado)",
                ],
            }

        # Namespace efémero por omissão (dev). Pode ser explícito ou derivado.
        ephemeral = parameters.get("ephemeral", True)
        if not parameters.get("namespace"):
            namespace = f"cr-deploy-{ticket_id[:8]}"
        ttl_seconds = int(parameters.get("ttl_seconds", 3600))
        cleanup_after = parameters.get("cleanup_after", False)

        try:
            # 2-3) Namespace efémero + ResourceQuota + Deployment Gatekeeper-compliant.
            await self._provision_resources(
                ticket_id=ticket_id,
                deployment_name=deployment_name,
                namespace=namespace,
                image=image,
                replicas=replicas,
                ephemeral=ephemeral,
                ttl_seconds=ttl_seconds,
            )

            # 4) Reconciliação: poll até available_replicas == replicas.
            reconciled, available = await self._wait_for_reconciliation(
                deployment_name=deployment_name,
                namespace=namespace,
                replicas=replicas,
                deadline=start_time + poll_timeout,
                poll_interval=poll_interval,
            )
            duration_seconds = asyncio.get_event_loop().time() - start_time

            if not reconciled:
                self.log_execution(
                    ticket_id,
                    "deploy_imperative_timeout",
                    level="warning",
                    deployment_name=deployment_name,
                    available_replicas=available,
                    expected=replicas,
                )
                self._metric_deploy_status("timeout")
                span.set_attribute("neural.hive.execution_status", "timeout")
                return {
                    "success": False,
                    "output": {
                        "deployment_id": deployment_name,
                        "status": "not_reconciled",
                        "namespace": namespace,
                        "available_replicas": available,
                        "replicas": replicas,
                    },
                    "metadata": {
                        "executor": "DeployExecutor",
                        "provider": "imperative",
                        "simulated": False,
                        "duration_seconds": duration_seconds,
                    },
                    "logs": [
                        "Deployment imperativo iniciado",
                        f"Não reconciliou em {poll_timeout}s "
                        f"({available}/{replicas} disponíveis)",
                    ],
                }

            # 5) Evidência de reconciliação — satisfaz _evidence_deploy.
            result = self._build_reconciled_result(
                deployment_name=deployment_name,
                namespace=namespace,
                image=image,
                available=available,
                replicas=replicas,
                ephemeral=ephemeral,
                ttl_seconds=ttl_seconds,
                duration_seconds=duration_seconds,
            )

            # 6) Cleanup opcional após capturar evidência (default: GC por reaper).
            if cleanup_after and ephemeral:
                with contextlib.suppress(Exception):
                    await self._core_api.delete_namespace(name=namespace)
                    result["logs"].append(f"Namespace {namespace} apagado (cleanup_after)")

            self.log_execution(
                ticket_id,
                "deploy_completed",
                deployment_id=deployment_name,
                status="reconciled",
                duration_seconds=duration_seconds,
            )
            self._metric_deploy_status("success")
            if self.metrics and hasattr(self.metrics, "deploy_duration_seconds"):
                self.metrics.deploy_duration_seconds.labels(stage="imperative").observe(
                    duration_seconds
                )
            span.set_attribute("neural.hive.execution_status", "success")
            return result

        except Exception as exc:  # erro de API k8s (RBAC, etc.)
            self.log_execution(
                ticket_id,
                "deploy_imperative_error",
                level="error",
                degraded=True,
                deployment_name=deployment_name,
                error=str(exc),
            )
            self._metric_real_path_unavailable()
            self._metric_deploy_status("failed")
            span.set_attribute("neural.hive.execution_status", "failed")
            return {
                "success": False,
                "output": {
                    "deployment_id": deployment_name,
                    "status": "error",
                    "namespace": namespace,
                    "error": str(exc),
                },
                "metadata": {
                    "executor": "DeployExecutor",
                    "provider": "imperative",
                    "simulated": False,
                    "real_path_unavailable": True,
                },
                "logs": ["Deployment imperativo iniciado", f"Erro na API Kubernetes: {exc}"],
            }
