"""Playbook executor service for Self-Healing Engine"""
import os
import yaml
from pathlib import Path
from typing import Optional
import structlog
from kubernetes import client, config

logger = structlog.get_logger()


class PlaybookExecutor:
    """Executes remediation playbooks"""

    def __init__(self, playbooks_dir: str, k8s_in_cluster: bool = True):
        self.playbooks_dir = Path(playbooks_dir)
        self.k8s_in_cluster = k8s_in_cluster
        self.core_v1: Optional[client.CoreV1Api] = None
        self.apps_v1: Optional[client.AppsV1Api] = None

    async def initialize(self):
        """Initialize Kubernetes clients"""
        try:
            if self.k8s_in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()

            logger.info("playbook_executor.initialized", in_cluster=self.k8s_in_cluster)
        except Exception as e:
            logger.error("playbook_executor.initialization_failed", error=str(e))
            raise

    async def execute_playbook(self, playbook_name: str, context: dict) -> dict:
        """Execute a remediation playbook"""
        try:
            playbook_path = self.playbooks_dir / f"{playbook_name}.yaml"

            if not playbook_path.exists():
                logger.error("playbook_executor.playbook_not_found", playbook=playbook_name)
                return {"success": False, "error": "Playbook not found"}

            with open(playbook_path) as f:
                playbook = yaml.safe_load(f)

            logger.info("playbook_executor.executing", playbook=playbook_name, context=context)

            # Execute playbook actions
            result = await self._execute_actions(playbook.get("actions", []), context)

            logger.info("playbook_executor.completed", playbook=playbook_name, result=result)
            return result

        except Exception as e:
            logger.error("playbook_executor.execution_failed", playbook=playbook_name, error=str(e))
            return {"success": False, "error": str(e)}

    async def _execute_actions(self, actions: list, context: dict) -> dict:
        """Execute playbook actions"""
        results = []

        for action in actions:
            action_type = action.get("type")

            if action_type == "restart_pod":
                result = await self._restart_pod(action, context)
            elif action_type == "scale_deployment":
                result = await self._scale_deployment(action, context)
            elif action_type == "update_policy":
                result = await self._update_policy(action, context)
            else:
                result = {"success": False, "error": f"Unknown action type: {action_type}"}

            results.append(result)

        all_success = all(r.get("success", False) for r in results)
        return {"success": all_success, "actions": results}

    async def _restart_pod(self, action: dict, context: dict) -> dict:
        """Restart a pod by deleting it"""
        try:
            pod_name = context.get("pod_name") or action.get("pod_name")
            namespace = context.get("namespace") or action.get("namespace", "default")

            self.core_v1.delete_namespaced_pod(pod_name, namespace)
            logger.info("playbook_executor.pod_restarted", pod=pod_name, namespace=namespace)

            return {"success": True, "action": "restart_pod", "pod": pod_name}
        except Exception as e:
            logger.error("playbook_executor.restart_pod_failed", error=str(e))
            return {"success": False, "action": "restart_pod", "error": str(e)}

    async def _scale_deployment(self, action: dict, context: dict) -> dict:
        """Scale a deployment"""
        try:
            deployment_name = context.get("deployment_name") or action.get("deployment_name")
            namespace = context.get("namespace") or action.get("namespace", "default")
            replicas = action.get("replicas", 1)

            deployment = self.apps_v1.read_namespaced_deployment(deployment_name, namespace)
            deployment.spec.replicas = replicas
            self.apps_v1.patch_namespaced_deployment_scale(deployment_name, namespace, deployment)

            logger.info("playbook_executor.deployment_scaled", deployment=deployment_name, replicas=replicas)

            return {"success": True, "action": "scale_deployment", "deployment": deployment_name, "replicas": replicas}
        except Exception as e:
            logger.error("playbook_executor.scale_deployment_failed", error=str(e))
            return {"success": False, "action": "scale_deployment", "error": str(e)}

    async def _update_policy(self, action: dict, context: dict) -> dict:
        """Update a policy (placeholder)"""
        logger.info("playbook_executor.update_policy", action=action)
        return {"success": True, "action": "update_policy", "note": "Policy update not yet implemented"}
