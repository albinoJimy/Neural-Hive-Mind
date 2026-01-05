"""Remediation coordinator for self-healing playbooks (Fluxo E4)"""
import asyncio
from typing import Dict, Any, Optional, List, Tuple
import structlog
from datetime import datetime, timezone
from enum import Enum

logger = structlog.get_logger()


# Importa cliente Self-Healing quando disponível
try:
    from src.clients.self_healing_client import SelfHealingClient
    SH_CLIENT_AVAILABLE = True
except ImportError:
    SH_CLIENT_AVAILABLE = False
    logger.warning("remediation_coordinator.sh_client_not_available")


class RemediationStatus(str, Enum):
    """Status de remediação"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RemediationType(str, Enum):
    """Tipos de remediação"""
    RESTART_POD = "restart_pod"
    SCALE_DEPLOYMENT = "scale_deployment"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    APPLY_NETWORK_POLICY = "apply_network_policy"
    CLEAR_CACHE = "clear_cache"
    TRIGGER_CHAOS = "trigger_chaos"
    EXEC_SCRIPT = "exec_script"


class RemediationCoordinator:
    """Coordena execução de playbooks de autocura seguindo Fluxo E4"""

    def __init__(
        self,
        k8s_client=None,
        mongodb_client=None,
        kafka_producer=None,
        self_healing_client=None,
        use_self_healing_engine: bool = True
    ):
        self.k8s = k8s_client
        self.mongodb = mongodb_client
        self.kafka_producer = kafka_producer
        self.self_healing_client = self_healing_client
        self.use_self_healing_engine = use_self_healing_engine and SH_CLIENT_AVAILABLE
        self.playbooks = self._load_playbooks()
        self.active_remediations = {}

    def _load_playbooks(self) -> Dict[str, Any]:
        """Carrega playbooks de autocura (Terraform/Ansible/Argo)"""
        return {
            "RB-SEC-001-CRITICAL": {
                "name": "Unauthorized Access Critical",
                "actions": [
                    {"type": RemediationType.APPLY_NETWORK_POLICY, "target": "isolate"},
                    {"type": RemediationType.EXEC_SCRIPT, "script": "revoke_tokens.sh"},
                ],
                "rollback_actions": [
                    {"type": RemediationType.APPLY_NETWORK_POLICY, "target": "restore"},
                ],
            },
            "RB-AVAIL-001-CRITICAL": {
                "name": "DoS Attack Critical",
                "actions": [
                    {"type": RemediationType.SCALE_DEPLOYMENT, "replicas": 10},
                    {"type": RemediationType.APPLY_NETWORK_POLICY, "target": "rate_limit"},
                ],
                "rollback_actions": [
                    {"type": RemediationType.SCALE_DEPLOYMENT, "replicas": 3},
                ],
            },
            "RB-PERF-001-HIGH": {
                "name": "Resource Abuse High",
                "actions": [
                    {"type": RemediationType.RESTART_POD, "selector": "app"},
                    {"type": RemediationType.CLEAR_CACHE, "cache": "redis"},
                ],
                "rollback_actions": [],
            },
            "RB-SEC-003-HIGH": {
                "name": "Malicious Payload High",
                "actions": [
                    {"type": RemediationType.ROLLBACK_DEPLOYMENT, "revision": "previous"},
                ],
                "rollback_actions": [],
            },
        }

    async def coordinate_remediation(
        self, incident: Dict[str, Any], enforcement_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Coordena remediação de incidente (E4: Executar ações)

        Args:
            incident: Incidente classificado
            enforcement_result: Resultado do policy enforcement

        Returns:
            Dict com resultado da remediação
        """
        try:
            incident_id = incident.get("incident_id")
            runbook_id = incident.get("runbook_id")

            logger.info(
                "remediation_coordinator.starting",
                incident_id=incident_id,
                runbook_id=runbook_id
            )

            # Buscar playbook
            playbook = self.playbooks.get(runbook_id)
            if not playbook:
                logger.warning(
                    "remediation_coordinator.playbook_not_found",
                    runbook_id=runbook_id
                )
                playbook = await self._create_generic_playbook(incident)

            # Iniciar remediação
            remediation_id = await self._start_remediation(incident, playbook)

            # E4: Sequenciar ações atomicamente
            remediation_result = await self._execute_playbook_actions(
                remediation_id, incident, playbook, enforcement_result
            )

            # Persistir resultado
            await self._persist_remediation_result(remediation_id, remediation_result)

            # Publicar evento de remediação
            await self._publish_remediation_event(remediation_id, remediation_result)

            logger.info(
                "remediation_coordinator.completed",
                remediation_id=remediation_id,
                status=remediation_result.get("status")
            )

            return remediation_result

        except Exception as e:
            logger.error(
                "remediation_coordinator.failed",
                incident_id=incident.get("incident_id"),
                error=str(e)
            )
            # E4: Falha > 2 tentativas → escalar para humano
            raise

    async def _start_remediation(
        self, incident: Dict[str, Any], playbook: Dict[str, Any]
    ) -> str:
        """Inicia remediação e retorna ID"""
        remediation_id = f"REM-{incident.get('incident_id')}-{int(datetime.now(timezone.utc).timestamp())}"

        self.active_remediations[remediation_id] = {
            "remediation_id": remediation_id,
            "incident_id": incident.get("incident_id"),
            "playbook_name": playbook.get("name"),
            "status": RemediationStatus.IN_PROGRESS,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "actions_completed": 0,
            "total_actions": len(playbook.get("actions", [])),
        }

        logger.info(
            "remediation_coordinator.started",
            remediation_id=remediation_id,
            playbook=playbook.get("name")
        )

        return remediation_id

    async def _execute_playbook_actions(
        self,
        remediation_id: str,
        incident: Dict[str, Any],
        playbook: Dict[str, Any],
        enforcement_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """E4: Executar ações do playbook atomicamente"""
        # Se usar self-healing engine, delegar execução
        if self.use_self_healing_engine and self.self_healing_client:
            return await self._execute_via_self_healing_engine(
                remediation_id, incident, playbook, enforcement_result
            )

        # Execução local (fallback)
        return await self._execute_actions_locally(
            remediation_id, incident, playbook, enforcement_result
        )

    async def _execute_via_self_healing_engine(
        self,
        remediation_id: str,
        incident: Dict[str, Any],
        playbook: Dict[str, Any],
        enforcement_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delega execução para Self-Healing Engine"""
        try:
            logger.info(
                "remediation_coordinator.delegating_to_engine",
                remediation_id=remediation_id,
                playbook=playbook.get("name")
            )

            # Mapear runbook_id para playbook_id do engine
            playbook_id = incident.get("runbook_id", "generic")

            # Solicitar execução ao engine
            result = await self.self_healing_client.trigger_remediation(
                remediation_id=remediation_id,
                incident_id=incident.get("incident_id"),
                playbook_id=playbook_id,
                parameters={
                    "incident": incident,
                    "enforcement": enforcement_result,
                    "playbook": playbook
                }
            )

            # Aguardar conclusão (com timeout de 5 minutos)
            final_result = await self.self_healing_client.wait_for_completion(
                remediation_id=remediation_id,
                poll_interval=2.0,
                max_wait=300.0
            )

            logger.info(
                "remediation_coordinator.engine_execution_complete",
                remediation_id=remediation_id,
                status=final_result.get("status")
            )

            # Mapear status do engine para formato esperado
            engine_status = final_result.get("status")
            if engine_status == "completed":
                status = RemediationStatus.COMPLETED
            elif engine_status == "failed":
                status = RemediationStatus.FAILED
            elif engine_status == "timeout":
                status = RemediationStatus.FAILED
            else:
                status = RemediationStatus.IN_PROGRESS

            return {
                "remediation_id": remediation_id,
                "status": status,
                "engine_result": final_result,
                "playbook": playbook.get("name"),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(
                "remediation_coordinator.engine_execution_failed",
                remediation_id=remediation_id,
                error=str(e)
            )
            # Fallback para execução local
            logger.info(
                "remediation_coordinator.falling_back_to_local",
                remediation_id=remediation_id
            )
            return await self._execute_actions_locally(
                remediation_id, incident, playbook, enforcement_result
            )

    async def _execute_actions_locally(
        self,
        remediation_id: str,
        incident: Dict[str, Any],
        playbook: Dict[str, Any],
        enforcement_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executa ações localmente (fallback ou modo direto)"""
        actions = playbook.get("actions", [])
        executed_actions = []
        errors = []
        attempt = 0
        max_attempts = 2

        logger.info(
            "remediation_coordinator.executing_locally",
            remediation_id=remediation_id,
            actions_count=len(actions)
        )

        for action in actions:
            action_attempt = 0

            while action_attempt <= max_attempts:
                try:
                    logger.info(
                        "remediation_coordinator.executing_action",
                        remediation_id=remediation_id,
                        action_type=action.get("type"),
                        attempt=action_attempt
                    )

                    action_result = await self._execute_remediation_action(
                        action, incident, remediation_id
                    )

                    executed_actions.append(action_result)

                    # Atualizar progresso
                    self.active_remediations[remediation_id]["actions_completed"] += 1

                    # Se bem-sucedido, sair do loop
                    if action_result.get("success"):
                        break

                except Exception as e:
                    errors.append({
                        "action": action,
                        "attempt": action_attempt,
                        "error": str(e)
                    })
                    action_attempt += 1

                    logger.warning(
                        "remediation_coordinator.action_retry",
                        remediation_id=remediation_id,
                        action_type=action.get("type"),
                        attempt=action_attempt,
                        max_attempts=max_attempts
                    )

            # E4: Falha > 2 tentativas → escalar para humano
            if action_attempt > max_attempts:
                logger.error(
                    "remediation_coordinator.action_max_retries",
                    remediation_id=remediation_id,
                    action=action
                )

                # Rollback
                await self._rollback_remediation(remediation_id, playbook, executed_actions)

                return {
                    "remediation_id": remediation_id,
                    "status": RemediationStatus.FAILED,
                    "actions": executed_actions,
                    "errors": errors,
                    "requires_human_intervention": True,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

        # Sucesso
        self.active_remediations[remediation_id]["status"] = RemediationStatus.COMPLETED

        return {
            "remediation_id": remediation_id,
            "status": RemediationStatus.COMPLETED,
            "actions": executed_actions,
            "playbook": playbook.get("name"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _execute_remediation_action(
        self, action: Dict[str, Any], incident: Dict[str, Any], remediation_id: str
    ) -> Dict[str, Any]:
        """Executa ação específica de remediação"""
        action_type = action.get("type")

        logger.info(
            "remediation_coordinator.action_executing",
            action_type=action_type,
            remediation_id=remediation_id
        )

        if action_type == RemediationType.RESTART_POD:
            return await self._restart_pod(action, incident)
        elif action_type == RemediationType.SCALE_DEPLOYMENT:
            return await self._scale_deployment(action, incident)
        elif action_type == RemediationType.ROLLBACK_DEPLOYMENT:
            return await self._rollback_deployment(action, incident)
        elif action_type == RemediationType.APPLY_NETWORK_POLICY:
            return await self._apply_network_policy(action, incident)
        elif action_type == RemediationType.CLEAR_CACHE:
            return await self._clear_cache(action, incident)
        elif action_type == RemediationType.TRIGGER_CHAOS:
            return await self._trigger_chaos(action, incident)
        elif action_type == RemediationType.EXEC_SCRIPT:
            return await self._exec_script(action, incident)
        else:
            return {
                "success": False,
                "action_type": action_type,
                "reason": "Unknown action type"
            }

    async def _restart_pod(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Reinicia pod via delete (Kubernetes recria automaticamente)

        Parses namespace and pod name from affected_resources entries (namespace/kind/name),
        deletes the pod with the correct namespace, then polls until a replacement pod
        reaches Running status (timeout ~60s).
        """
        selector = action.get("selector", "app")
        resources = incident.get("affected_resources", [])

        logger.info("remediation_coordinator.restarting_pod", selector=selector)

        success = False
        details = {"selector": selector, "resources": resources}

        if self.k8s:
            # Parse namespace and pod name from affected_resources
            namespace, pod_name = self._parse_pod_resource(resources)

            if pod_name:
                try:
                    # Get pod info before deletion to extract labels for finding replacement
                    pod_info = await self.k8s.get_pod(pod_name, namespace)
                    pod_labels = {}
                    pod_prefix = pod_name.rsplit("-", 2)[0] if "-" in pod_name else pod_name

                    if pod_info:
                        pod_labels = pod_info.get("metadata", {}).get("labels", {})

                    # Delete pod with the correct namespace
                    deleted = await self.k8s.delete_pod(pod_name, namespace)
                    if deleted:
                        details["pod_deleted"] = pod_name
                        details["namespace"] = namespace
                        logger.info(
                            "remediation_coordinator.pod_deleted",
                            pod=pod_name,
                            namespace=namespace
                        )

                        # Wait for replacement pod to reach Running status
                        replacement_result = await self._wait_for_replacement_pod(
                            pod_name=pod_name,
                            pod_prefix=pod_prefix,
                            pod_labels=pod_labels,
                            namespace=namespace,
                            timeout=60.0,
                            poll_interval=2.0
                        )

                        if replacement_result.get("success"):
                            success = True
                            details["replacement_pod"] = replacement_result.get("replacement_pod")
                            details["replacement_status"] = replacement_result.get("status")
                            logger.info(
                                "remediation_coordinator.pod_restarted",
                                pod=pod_name,
                                replacement=replacement_result.get("replacement_pod"),
                                namespace=namespace
                            )
                        else:
                            # Pod deleted but replacement not ready within timeout
                            success = False
                            details["warning"] = replacement_result.get("reason", "Replacement pod not ready")
                            details["replacement_pod"] = replacement_result.get("replacement_pod")
                            logger.warning(
                                "remediation_coordinator.replacement_pod_not_ready",
                                pod=pod_name,
                                namespace=namespace,
                                reason=replacement_result.get("reason")
                            )
                    else:
                        details["error"] = "Failed to delete pod"
                except Exception as e:
                    details["error"] = str(e)
                    logger.error(
                        "remediation_coordinator.restart_pod_failed",
                        pod=pod_name,
                        namespace=namespace,
                        error=str(e)
                    )
            else:
                logger.warning(
                    "remediation_coordinator.no_pod_found",
                    resources=resources
                )
                success = True  # Nao bloquear fluxo
                details["warning"] = "No pod name found in affected_resources"
        else:
            logger.warning("remediation_coordinator.k8s_not_available")
            success = True
            details["warning"] = "Kubernetes client not available"

        return {
            "success": success,
            "action_type": RemediationType.RESTART_POD,
            "details": details
        }

    def _parse_pod_resource(self, resources: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse namespace and pod name from affected_resources entries.

        Supports formats:
        - "namespace/pod/name" or "namespace/Pod/name"
        - "pod/name" (uses default namespace)
        - "name" (uses default namespace)

        Args:
            resources: List of resource strings

        Returns:
            Tuple of (namespace, pod_name), namespace may be None to use client default
        """
        for resource in resources:
            parts = resource.split("/")

            if len(parts) >= 3:
                # Format: namespace/kind/name
                namespace = parts[0]
                kind = parts[1]
                name = parts[2]
                if kind.lower() == "pod":
                    return (namespace, name)

            elif len(parts) == 2:
                # Format: kind/name (no namespace)
                kind = parts[0]
                name = parts[1]
                if kind.lower() == "pod":
                    return (None, name)

            elif len(parts) == 1 and resource:
                # Just the name, assume it's a pod
                return (None, resource)

        return (None, None)

    async def _wait_for_replacement_pod(
        self,
        pod_name: str,
        pod_prefix: str,
        pod_labels: Dict[str, str],
        namespace: Optional[str],
        timeout: float = 60.0,
        poll_interval: float = 2.0
    ) -> Dict[str, Any]:
        """
        Wait for a replacement pod to reach Running status after deletion.

        Args:
            pod_name: Original pod name that was deleted
            pod_prefix: Pod name prefix to match replacement pods
            pod_labels: Labels from the original pod for filtering
            namespace: Namespace to search in
            timeout: Maximum wait time in seconds
            poll_interval: Time between polling attempts

        Returns:
            Dict with success status and replacement pod info
        """
        start_time = asyncio.get_event_loop().time()
        replacement_pod = None

        # Build label selector from pod labels (prefer 'app' label)
        label_selector = None
        if pod_labels:
            if "app" in pod_labels:
                label_selector = f"app={pod_labels['app']}"
            elif "app.kubernetes.io/name" in pod_labels:
                label_selector = f"app.kubernetes.io/name={pod_labels['app.kubernetes.io/name']}"

        logger.info(
            "remediation_coordinator.waiting_for_replacement",
            pod_name=pod_name,
            pod_prefix=pod_prefix,
            label_selector=label_selector,
            namespace=namespace,
            timeout=timeout
        )

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            await asyncio.sleep(poll_interval)

            # First check if the original pod still exists (shouldn't)
            original_exists = await self.k8s.get_pod(pod_name, namespace)
            if original_exists:
                # Pod still being terminated
                continue

            # List pods matching the label selector or prefix
            pods = await self.k8s.list_pods(
                namespace=namespace,
                label_selector=label_selector
            )

            # Find a replacement pod (different name, Running status)
            for pod in pods:
                current_pod_name = pod.get("metadata", {}).get("name", "")
                pod_phase = pod.get("status", {}).get("phase", "")

                # Skip if it's the same pod name (shouldn't exist after deletion)
                if current_pod_name == pod_name:
                    continue

                # Check if pod matches prefix (same deployment/replicaset)
                if current_pod_name.startswith(pod_prefix):
                    replacement_pod = current_pod_name

                    if pod_phase == "Running":
                        # Check container statuses for readiness
                        container_statuses = pod.get("status", {}).get("containerStatuses", [])
                        all_ready = all(
                            cs.get("ready", False) for cs in container_statuses
                        ) if container_statuses else False

                        if all_ready or not container_statuses:
                            logger.info(
                                "remediation_coordinator.replacement_pod_ready",
                                replacement_pod=replacement_pod,
                                phase=pod_phase
                            )
                            return {
                                "success": True,
                                "replacement_pod": replacement_pod,
                                "status": pod_phase
                            }

        # Timeout reached
        logger.warning(
            "remediation_coordinator.replacement_pod_timeout",
            pod_name=pod_name,
            replacement_pod=replacement_pod,
            timeout=timeout
        )

        return {
            "success": False,
            "replacement_pod": replacement_pod,
            "reason": f"Timeout after {timeout}s waiting for replacement pod to reach Running status"
        }

    async def _scale_deployment(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Escala deployment"""
        replicas = action.get("replicas", 3)
        resources = incident.get("affected_resources", [])

        # Validar replicas (min: 0, max: 50)
        if replicas < 0:
            replicas = 0
        elif replicas > 50:
            replicas = 50

        logger.info("remediation_coordinator.scaling_deployment", replicas=replicas)

        success = False
        details = {"replicas": replicas, "resources": resources}

        if self.k8s:
            deployment_name = self._extract_resource_name(resources, "deployment")

            if deployment_name:
                try:
                    scaled = await self.k8s.scale_deployment(deployment_name, replicas)
                    if scaled:
                        success = True
                        details["deployment_scaled"] = deployment_name
                        logger.info(
                            "remediation_coordinator.deployment_scaled",
                            deployment=deployment_name,
                            replicas=replicas
                        )
                    else:
                        details["error"] = "Failed to scale deployment"
                except Exception as e:
                    details["error"] = str(e)
                    logger.error(
                        "remediation_coordinator.scale_deployment_failed",
                        deployment=deployment_name,
                        error=str(e)
                    )
            else:
                logger.warning(
                    "remediation_coordinator.no_deployment_found",
                    resources=resources
                )
                success = True
                details["warning"] = "No deployment name found in affected_resources"
        else:
            logger.warning("remediation_coordinator.k8s_not_available")
            success = True
            details["warning"] = "Kubernetes client not available"

        return {
            "success": success,
            "action_type": RemediationType.SCALE_DEPLOYMENT,
            "details": details
        }

    async def _rollback_deployment(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Faz rollback de deployment"""
        revision_str = action.get("revision", "previous")
        resources = incident.get("affected_resources", [])

        # Converter revision para int se especificado
        revision = None
        if revision_str and revision_str != "previous":
            try:
                revision = int(revision_str)
            except ValueError:
                revision = None

        logger.info("remediation_coordinator.rolling_back_deployment", revision=revision_str)

        success = False
        details = {"revision": revision_str, "resources": resources}

        if self.k8s:
            deployment_name = self._extract_resource_name(resources, "deployment")

            if deployment_name:
                try:
                    result = await self.k8s.rollback_deployment(deployment_name, revision)
                    if result.get("success"):
                        success = True
                        details["deployment_rolled_back"] = deployment_name
                        details["previous_revision"] = result.get("previous_revision")
                        details["target_revision"] = result.get("target_revision")
                        logger.info(
                            "remediation_coordinator.deployment_rolled_back",
                            deployment=deployment_name,
                            revision=revision_str
                        )
                    else:
                        details["error"] = result.get("error", "Rollback failed")
                except Exception as e:
                    details["error"] = str(e)
                    logger.error(
                        "remediation_coordinator.rollback_deployment_failed",
                        deployment=deployment_name,
                        error=str(e)
                    )
            else:
                logger.warning(
                    "remediation_coordinator.no_deployment_found",
                    resources=resources
                )
                success = True
                details["warning"] = "No deployment name found in affected_resources"
        else:
            logger.warning("remediation_coordinator.k8s_not_available")
            success = True
            details["warning"] = "Kubernetes client not available"

        return {
            "success": success,
            "action_type": RemediationType.ROLLBACK_DEPLOYMENT,
            "details": details
        }

    async def _apply_network_policy(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aplica NetworkPolicy"""
        target = action.get("target", "isolate")
        resources = incident.get("affected_resources", [])
        incident_id = incident.get("incident_id", "unknown")

        logger.info("remediation_coordinator.applying_network_policy", target=target)

        success = False
        details = {"target": target, "resources": resources}

        if self.k8s:
            # Gerar nome da policy baseado no incidente
            policy_name = f"guard-agents-{target}-{incident_id[:8]}"

            # Extrair pod selector de resources
            pod_selector = {}
            resource_name = self._extract_resource_name(resources, "pod")
            if resource_name:
                pod_selector = {"app": resource_name.split("-")[0]}

            policy_spec = {
                "target": target,
                "pod_selector": pod_selector,
                "type": "remediation"
            }

            try:
                result = await self.k8s.apply_network_policy(policy_name, policy_spec)
                if result.get("success"):
                    success = True
                    details["policy_name"] = policy_name
                    details["policy_action"] = result.get("action")
                    logger.info(
                        "remediation_coordinator.network_policy_applied",
                        policy=policy_name,
                        target=target
                    )
                else:
                    details["error"] = result.get("error", "Failed to apply policy")
            except Exception as e:
                details["error"] = str(e)
                logger.error(
                    "remediation_coordinator.apply_network_policy_failed",
                    policy=policy_name,
                    error=str(e)
                )
        else:
            logger.warning("remediation_coordinator.k8s_not_available")
            success = True
            details["warning"] = "Kubernetes client not available"

        return {
            "success": success,
            "action_type": RemediationType.APPLY_NETWORK_POLICY,
            "details": details
        }

    async def _clear_cache(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Limpa cache"""
        cache_type = action.get("cache", "redis")

        logger.info("remediation_coordinator.clearing_cache", cache_type=cache_type)

        # TODO: Clear Redis/Memcached
        return {
            "success": True,
            "action_type": RemediationType.CLEAR_CACHE,
            "details": {"cache": cache_type}
        }

    async def _trigger_chaos(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Trigger experimento de caos (ChaosMesh/Litmus)"""
        chaos_type = action.get("chaos_type")

        logger.info("remediation_coordinator.triggering_chaos", chaos_type=chaos_type)

        # TODO: Apply ChaosMesh experiment
        return {
            "success": True,
            "action_type": RemediationType.TRIGGER_CHAOS,
            "details": {"chaos_type": chaos_type}
        }

    async def _exec_script(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executa script"""
        script = action.get("script")

        logger.info("remediation_coordinator.executing_script", script=script)

        # TODO: Execute via Ansible/StackStorm
        return {
            "success": True,
            "action_type": RemediationType.EXEC_SCRIPT,
            "details": {"script": script}
        }

    async def _rollback_remediation(
        self,
        remediation_id: str,
        playbook: Dict[str, Any],
        executed_actions: List[Dict[str, Any]]
    ):
        """E4: Rollback automático em caso de falha"""
        logger.warning(
            "remediation_coordinator.rolling_back",
            remediation_id=remediation_id
        )

        rollback_actions = playbook.get("rollback_actions", [])

        for action in rollback_actions:
            try:
                await self._execute_remediation_action(action, {}, remediation_id)
            except Exception as e:
                logger.error(
                    "remediation_coordinator.rollback_failed",
                    remediation_id=remediation_id,
                    action=action,
                    error=str(e)
                )

        self.active_remediations[remediation_id]["status"] = RemediationStatus.ROLLED_BACK

    async def _persist_remediation_result(
        self, remediation_id: str, result: Dict[str, Any]
    ):
        """Persiste resultado no MongoDB"""
        if self.mongodb and self.mongodb.remediation_collection:
            try:
                await self.mongodb.remediation_collection.insert_one(result)
                logger.debug(
                    "remediation_coordinator.persisted",
                    remediation_id=remediation_id
                )
            except Exception as e:
                logger.error(
                    "remediation_coordinator.persist_failed",
                    remediation_id=remediation_id,
                    error=str(e)
                )

    async def _publish_remediation_event(
        self, remediation_id: str, result: Dict[str, Any]
    ):
        """Publica evento de remediação no Kafka"""
        if not self.kafka_producer:
            logger.warning(
                "remediation_coordinator.no_kafka_producer",
                remediation_id=remediation_id
            )
            return

        try:
            # Publica resultado completo da remediação
            published = await self.kafka_producer.publish_remediation_result(
                remediation_id=remediation_id,
                result=result
            )

            if published:
                logger.info(
                    "remediation_coordinator.event_published",
                    remediation_id=remediation_id,
                    status=result.get("status")
                )
            else:
                logger.error(
                    "remediation_coordinator.publish_failed",
                    remediation_id=remediation_id,
                    reason="Producer returned False"
                )

        except Exception as e:
            logger.error(
                "remediation_coordinator.publish_error",
                remediation_id=remediation_id,
                error=str(e)
            )

    async def _create_generic_playbook(
        self, incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Cria playbook genérico quando específico não existe"""
        severity = incident.get("severity", "medium")

        logger.info(
            "remediation_coordinator.creating_generic_playbook",
            severity=severity
        )

        # Playbook genérico baseado em severidade
        if severity == "critical":
            return {
                "name": "Generic Critical Remediation",
                "actions": [
                    {"type": RemediationType.APPLY_NETWORK_POLICY, "target": "isolate"},
                ],
                "rollback_actions": []
            }
        elif severity == "high":
            return {
                "name": "Generic High Remediation",
                "actions": [
                    {"type": RemediationType.RESTART_POD, "selector": "app"},
                ],
                "rollback_actions": []
            }
        else:
            return {
                "name": "Generic Remediation",
                "actions": [],
                "rollback_actions": []
            }

    def _extract_resource_name(
        self, resources: List[str], resource_type: str
    ) -> Optional[str]:
        """
        Extrai nome do recurso da lista de affected_resources

        Args:
            resources: Lista de recursos no formato "namespace/kind/name"
            resource_type: Tipo de recurso a buscar (pod, deployment, etc.)

        Returns:
            Nome do recurso ou None se nao encontrado
        """
        for resource in resources:
            parts = resource.split("/")
            if len(parts) >= 3 and parts[1].lower() == resource_type.lower():
                return parts[2]
            elif len(parts) == 2 and parts[0].lower() == resource_type.lower():
                return parts[1]
            elif len(parts) == 1:
                # Se nao tiver formato estruturado, usar como nome direto
                return resource
        return None
