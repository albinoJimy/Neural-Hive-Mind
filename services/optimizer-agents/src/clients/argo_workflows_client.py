from typing import Dict, List, Optional

import structlog
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

from src.config.settings import get_settings

logger = structlog.get_logger()


class ArgoWorkflowsClient:
    """
    Cliente para Argo Workflows.

    Responsável por submissão, monitoramento e gerenciamento de experimentos via Argo Workflows.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.k8s_custom_api: Optional[k8s_client.CustomObjectsApi] = None
        self.namespace = self.settings.argo_workflows_namespace

    async def connect(self):
        """Configurar cliente Kubernetes."""
        try:
            # Carregar config do cluster (ou local se desenvolvimento)
            try:
                k8s_config.load_incluster_config()
                logger.info("kubernetes_config_loaded", mode="in_cluster")
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()
                logger.info("kubernetes_config_loaded", mode="local")

            # Criar API client para Custom Resources (Workflows)
            self.k8s_custom_api = k8s_client.CustomObjectsApi()

            logger.info("argo_workflows_client_connected", namespace=self.namespace)
        except Exception as e:
            logger.error("argo_workflows_client_connection_failed", error=str(e))
            raise

    async def submit_workflow(self, workflow_name: str, experiment_config: Dict) -> Optional[str]:
        """
        Submeter workflow de experimento.

        Args:
            workflow_name: Nome do workflow
            experiment_config: Configuração do experimento

        Returns:
            Workflow UID ou None se falhou
        """
        try:
            # Construir manifest do Workflow
            workflow_manifest = self._build_experiment_workflow(workflow_name, experiment_config)

            # Submeter via Kubernetes Custom Resource API
            response = self.k8s_custom_api.create_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="workflows",
                body=workflow_manifest,
            )

            workflow_uid = response.get("metadata", {}).get("uid")
            workflow_status = response.get("status", {}).get("phase", "Pending")

            logger.info(
                "workflow_submitted",
                workflow_name=workflow_name,
                workflow_uid=workflow_uid,
                status=workflow_status,
            )

            return workflow_uid

        except Exception as e:
            logger.error("workflow_submission_failed", workflow_name=workflow_name, error=str(e))
            return None

    def _build_experiment_workflow(self, workflow_name: str, experiment_config: Dict) -> Dict:
        """
        Construir manifest de Workflow Argo.

        Args:
            workflow_name: Nome do workflow
            experiment_config: Configuração do experimento

        Returns:
            Manifest do Workflow
        """
        experiment_type = experiment_config.get("experiment_type", "A_B_TEST")
        baseline_config = experiment_config.get("baseline_configuration", {})
        experimental_config = experiment_config.get("experimental_configuration", {})
        duration_seconds = experiment_config.get("duration_seconds", 3600)
        traffic_percentage = experiment_config.get("traffic_percentage", 0.1)

        # Template básico de Workflow Argo
        workflow = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "generateName": f"{workflow_name}-",
                "namespace": self.namespace,
                "labels": {
                    "experiment-type": experiment_type.lower(),
                    "managed-by": "optimizer-agents",
                },
            },
            "spec": {
                "entrypoint": "experiment-pipeline",
                "serviceAccountName": "argo-workflow",
                "templates": [
                    {
                        "name": "experiment-pipeline",
                        "steps": [
                            [{"name": "setup-baseline", "template": "deploy-baseline"}],
                            [{"name": "setup-experimental", "template": "deploy-experimental"}],
                            [{"name": "run-traffic-split", "template": "traffic-split"}],
                            [{"name": "monitor-experiment", "template": "monitor"}],
                            [{"name": "collect-metrics", "template": "collect-metrics"}],
                            [{"name": "analyze-results", "template": "analyze"}],
                            [{"name": "cleanup", "template": "cleanup"}],
                        ],
                    },
                    {
                        "name": "deploy-baseline",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "deploy_baseline.py"],
                            "env": [
                                {"name": "CONFIG", "value": str(baseline_config)},
                                {"name": "EXPERIMENT_TYPE", "value": experiment_type},
                            ],
                        },
                    },
                    {
                        "name": "deploy-experimental",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "deploy_experimental.py"],
                            "env": [
                                {"name": "CONFIG", "value": str(experimental_config)},
                                {"name": "TRAFFIC_PERCENTAGE", "value": str(traffic_percentage)},
                            ],
                        },
                    },
                    {
                        "name": "traffic-split",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "configure_traffic_split.py"],
                            "env": [
                                {"name": "BASELINE_WEIGHT", "value": str(1.0 - traffic_percentage)},
                                {"name": "EXPERIMENTAL_WEIGHT", "value": str(traffic_percentage)},
                            ],
                        },
                    },
                    {
                        "name": "monitor",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "monitor_experiment.py"],
                            "env": [
                                {"name": "DURATION_SECONDS", "value": str(duration_seconds)},
                                {"name": "GUARDRAILS", "value": str(experiment_config.get("guardrails", []))},
                            ],
                        },
                    },
                    {
                        "name": "collect-metrics",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "collect_metrics.py"],
                            "env": [
                                {"name": "METRICS_ENDPOINT", "value": self.settings.prometheus_url},
                            ],
                        },
                    },
                    {
                        "name": "analyze",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "analyze_results.py"],
                            "env": [
                                {
                                    "name": "SUCCESS_CRITERIA",
                                    "value": str(experiment_config.get("success_criteria", [])),
                                },
                            ],
                        },
                    },
                    {
                        "name": "cleanup",
                        "container": {
                            "image": "optimizer-agents/experiment-runner:latest",
                            "command": ["python", "cleanup_experiment.py"],
                        },
                    },
                ],
                "onExit": "cleanup-on-exit",
            },
        }

        return workflow

    async def get_workflow_status(self, workflow_uid: str) -> Optional[Dict]:
        """
        Obter status de um workflow.

        Args:
            workflow_uid: UID do workflow

        Returns:
            Status do workflow ou None se falhou
        """
        try:
            # Listar workflows e filtrar por UID
            workflows = self.k8s_custom_api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="workflows",
            )

            for workflow in workflows.get("items", []):
                if workflow.get("metadata", {}).get("uid") == workflow_uid:
                    status = {
                        "phase": workflow.get("status", {}).get("phase", "Unknown"),
                        "start_time": workflow.get("status", {}).get("startedAt"),
                        "finish_time": workflow.get("status", {}).get("finishedAt"),
                        "message": workflow.get("status", {}).get("message", ""),
                        "nodes": workflow.get("status", {}).get("nodes", {}),
                    }

                    logger.debug("workflow_status_retrieved", workflow_uid=workflow_uid, phase=status["phase"])
                    return status

            logger.warning("workflow_not_found", workflow_uid=workflow_uid)
            return None

        except Exception as e:
            logger.error("get_workflow_status_failed", workflow_uid=workflow_uid, error=str(e))
            return None

    async def abort_workflow(self, workflow_uid: str) -> bool:
        """
        Abortar workflow em execução.

        Args:
            workflow_uid: UID do workflow

        Returns:
            True se bem-sucedido
        """
        try:
            # Obter workflow
            workflows = self.k8s_custom_api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="workflows",
            )

            workflow_name = None
            for workflow in workflows.get("items", []):
                if workflow.get("metadata", {}).get("uid") == workflow_uid:
                    workflow_name = workflow.get("metadata", {}).get("name")
                    break

            if not workflow_name:
                logger.warning("workflow_not_found_for_abort", workflow_uid=workflow_uid)
                return False

            # Aplicar patch para abort
            patch_body = {"spec": {"shutdown": "Terminate"}}

            self.k8s_custom_api.patch_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="workflows",
                name=workflow_name,
                body=patch_body,
            )

            logger.info("workflow_aborted", workflow_uid=workflow_uid, workflow_name=workflow_name)
            return True

        except Exception as e:
            logger.error("abort_workflow_failed", workflow_uid=workflow_uid, error=str(e))
            return False

    async def get_workflow_logs(self, workflow_uid: str, step_name: Optional[str] = None) -> Optional[str]:
        """
        Obter logs de um workflow.

        Args:
            workflow_uid: UID do workflow
            step_name: Nome do step (opcional)

        Returns:
            Logs do workflow ou None se falhou
        """
        try:
            # Obter workflow
            workflows = self.k8s_custom_api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="workflows",
            )

            workflow_name = None
            for workflow in workflows.get("items", []):
                if workflow.get("metadata", {}).get("uid") == workflow_uid:
                    workflow_name = workflow.get("metadata", {}).get("name")
                    break

            if not workflow_name:
                logger.warning("workflow_not_found_for_logs", workflow_uid=workflow_uid)
                return None

            # Obter logs via Kubernetes Core API
            core_api = k8s_client.CoreV1Api()

            # Listar pods do workflow
            pods = core_api.list_namespaced_pod(
                namespace=self.namespace, label_selector=f"workflows.argoproj.io/workflow={workflow_name}"
            )

            logs = []
            for pod in pods.items:
                pod_name = pod.metadata.name

                # Filtrar por step se especificado
                if step_name and step_name not in pod_name:
                    continue

                try:
                    pod_logs = core_api.read_namespaced_pod_log(name=pod_name, namespace=self.namespace)
                    logs.append(f"=== Pod: {pod_name} ===\n{pod_logs}\n")
                except Exception as e:
                    logger.warning("failed_to_get_pod_logs", pod_name=pod_name, error=str(e))

            combined_logs = "\n".join(logs)
            logger.info("workflow_logs_retrieved", workflow_uid=workflow_uid, log_size=len(combined_logs))
            return combined_logs

        except Exception as e:
            logger.error("get_workflow_logs_failed", workflow_uid=workflow_uid, error=str(e))
            return None

    async def list_workflows(self, labels: Optional[Dict[str, str]] = None, limit: int = 50) -> List[Dict]:
        """
        Listar workflows.

        Args:
            labels: Filtros de labels
            limit: Limite de resultados

        Returns:
            Lista de workflows
        """
        try:
            label_selector = None
            if labels:
                label_selector = ",".join([f"{k}={v}" for k, v in labels.items()])

            workflows = self.k8s_custom_api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="workflows",
                label_selector=label_selector,
                limit=limit,
            )

            workflow_list = []
            for workflow in workflows.get("items", []):
                workflow_info = {
                    "name": workflow.get("metadata", {}).get("name"),
                    "uid": workflow.get("metadata", {}).get("uid"),
                    "phase": workflow.get("status", {}).get("phase", "Unknown"),
                    "start_time": workflow.get("status", {}).get("startedAt"),
                    "finish_time": workflow.get("status", {}).get("finishedAt"),
                    "labels": workflow.get("metadata", {}).get("labels", {}),
                }
                workflow_list.append(workflow_info)

            logger.info("workflows_listed", count=len(workflow_list), labels=labels)
            return workflow_list

        except Exception as e:
            logger.error("list_workflows_failed", error=str(e))
            return []
