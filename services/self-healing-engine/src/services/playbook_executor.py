"""Playbook executor service for Self-Healing Engine"""
import asyncio
import yaml
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Optional, Callable, List, Dict, Any
import structlog
from kubernetes import client, config
from prometheus_client import Counter, Histogram
from neural_hive_observability import get_tracer

logger = structlog.get_logger()

# OPA validation metrics
OPA_VALIDATION_TOTAL = Counter(
    'self_healing_opa_validation_total',
    'Total OPA policy validations for self-healing actions',
    ['action', 'result']
)


class PlaybookExecutor:
    """Executa playbooks de remediação com callbacks e métricas."""

    def __init__(
        self,
        playbooks_dir: str,
        k8s_in_cluster: bool = True,
        default_timeout_seconds: int = 300,
        service_registry_client=None,
        execution_ticket_client=None,
        orchestrator_client=None,
        opa_client=None,
        opa_enabled: bool = True,
        opa_fail_open: bool = True,
    ):
        self.playbooks_dir = Path(playbooks_dir)
        self.k8s_in_cluster = k8s_in_cluster
        self.default_timeout_seconds = default_timeout_seconds
        self.service_registry_client = service_registry_client
        self.execution_ticket_client = execution_ticket_client
        self.orchestrator_client = orchestrator_client
        self.opa_client = opa_client
        self.opa_enabled = opa_enabled
        self.opa_fail_open = opa_fail_open
        self.core_v1: Optional[client.CoreV1Api] = None
        self.apps_v1: Optional[client.AppsV1Api] = None

        # Métricas de execução de playbook
        self.playbook_execution_total = Counter(
            "self_healing_playbook_execution_total",
            "Total de execuções de playbook",
            ["playbook", "status"]
        )
        self.playbook_execution_duration_seconds = Histogram(
            "self_healing_playbook_execution_duration_seconds",
            "Duração da execução de playbooks",
            ["playbook"],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]
        )

        # Actions that require OPA validation
        self._opa_validated_actions = {
            'reallocate_ticket',
            'restart_workflow',
            'update_ticket_status',
            'trigger_replanning',
        }

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
        except Exception as e:  # noqa: BLE001
            logger.error("playbook_executor.initialization_failed", error=str(e))
            raise

    def list_playbooks(self) -> List[str]:
        """Lista playbooks disponíveis no diretório configurado."""
        return sorted([p.stem for p in self.playbooks_dir.glob("*.yaml")])

    def playbook_exists(self, playbook_name: str) -> bool:
        """Verifica se o playbook existe no diretório."""
        return (self.playbooks_dir / f"{playbook_name}.yaml").exists()

    def get_playbook_metadata(self, playbook_name: str) -> Dict[str, Any]:
        """Retorna metadados básicos de um playbook (fail-open)."""
        try:
            playbook_path = self.playbooks_dir / f"{playbook_name}.yaml"
            if not playbook_path.exists():
                return {"actions": []}

            with open(playbook_path) as f:
                playbook = yaml.safe_load(f) or {}
            return playbook
        except Exception:
            return {"actions": []}

    async def execute_playbook(
        self,
        playbook_name: str,
        context: dict,
        on_action_completed: Optional[Callable[[dict], Any]] = None,
        on_playbook_completed: Optional[Callable[[dict], Any]] = None,
        timeout_seconds: Optional[int] = None
    ) -> dict:
        """Execute a remediation playbook com callbacks e timeout."""
        playbook_path = self.playbooks_dir / f"{playbook_name}.yaml"

        if not playbook_path.exists():
            logger.error("playbook_executor.playbook_not_found", playbook=playbook_name)
            return {"success": False, "error": "Playbook not found"}

        with open(playbook_path) as f:
            playbook = yaml.safe_load(f) or {}

        actions = playbook.get("actions", [])
        total_actions = len(actions)
        timeout = timeout_seconds or playbook.get("timeout_seconds") or self.default_timeout_seconds

        logger.info(
            "playbook_executor.executing",
            playbook=playbook_name,
            context=context,
            total_actions=total_actions,
            timeout_seconds=timeout
        )

        tracer = get_tracer()
        with tracer.start_as_current_span("playbook_execution") as span:
            span.set_attribute("neural.hive.playbook_name", playbook_name)
            span.set_attribute("neural.hive.incident_id", context.get("incident_id"))

            start_time = perf_counter()
            status_label = "success"
            result: Dict[str, Any] = {}

            try:
                execution_result = await asyncio.wait_for(
                    self._execute_actions(actions, context, on_action_completed),
                    timeout=timeout
                )
                result = {
                    **execution_result,
                    "total_actions": total_actions
                }
            except asyncio.TimeoutError:
                status_label = "timeout"
                result = {
                    "success": False,
                    "error": "Playbook timeout",
                    "status": "TIMEOUT",
                    "total_actions": total_actions
                }
            except Exception as e:  # noqa: BLE001
                status_label = "error"
                result = {
                    "success": False,
                    "error": str(e),
                    "status": "FAILED",
                    "total_actions": total_actions
                }
                logger.error("playbook_executor.execution_failed", playbook=playbook_name, error=str(e))

            duration = perf_counter() - start_time
            status_label = status_label if status_label in ["timeout", "error"] else ("success" if result.get("success") else "failed")
            span.set_attribute("neural.hive.execution_status", status_label)
            self._record_metrics(playbook_name, status_label, duration)

            if on_playbook_completed:
                await self._maybe_call_callback(on_playbook_completed, {**result, "duration_seconds": duration})

            logger.info(
                "playbook_executor.completed",
                playbook=playbook_name,
                success=result.get("success"),
                duration_seconds=round(duration, 4)
            )
            return result

    async def _execute_actions(
        self,
        actions: list,
        context: dict,
        on_action_completed: Optional[Callable[[dict], Any]] = None
    ) -> dict:
        """Execute playbook actions sequencialmente."""
        results = []

        for action in actions:
            normalized_action = self._normalize_action(action, context)
            action_type = normalized_action.get("type")
            handler = self._get_action_handler(action_type)

            if handler is None:
                result = {"success": False, "error": f"Unknown action type: {action_type}", "action": action_type}
            else:
                merged_context = {**context, **normalized_action}

                # Validate action with OPA if required
                if action_type in self._opa_validated_actions:
                    opa_allowed = await self._validate_action_with_opa(normalized_action, merged_context)
                    if not opa_allowed:
                        result = {
                            "success": False,
                            "error": "Action blocked by OPA policy",
                            "action": action_type,
                            "opa_denied": True
                        }
                        results.append(result)
                        if on_action_completed:
                            await self._maybe_call_callback(on_action_completed, result)
                        continue

                result = await handler(normalized_action, merged_context)

            results.append(result)

            if on_action_completed:
                await self._maybe_call_callback(on_action_completed, result)

        all_success = all(r.get("success", False) for r in results)
        return {"success": all_success, "actions": results}

    async def _validate_action_with_opa(self, action: dict, context: dict) -> bool:
        """
        Validate action with OPA policy engine.

        Args:
            action: Action to validate
            context: Execution context

        Returns:
            True if action is allowed, False if denied
        """
        if not self.opa_enabled:
            return True

        if not self.opa_client:
            if self.opa_fail_open:
                logger.warning(
                    'playbook_executor.opa_client_unavailable',
                    action=action.get('type'),
                    fail_open=True
                )
                return True
            else:
                logger.error(
                    'playbook_executor.opa_client_unavailable',
                    action=action.get('type'),
                    fail_open=False
                )
                return False

        action_type = action.get('type', 'unknown')

        try:
            # Build OPA input
            # Resolve ticket_id: use explicit ticket_id or first element from affected_tickets
            affected_tickets = action.get('affected_tickets') or context.get('affected_tickets') or []
            ticket_id = action.get('ticket_id') or context.get('ticket_id', '')
            if not ticket_id and affected_tickets:
                ticket_id = affected_tickets[0]

            opa_input = {
                'input': {
                    'resource': {
                        'action': action_type,
                        'ticket_id': ticket_id,
                        'workflow_id': action.get('workflow_id') or context.get('workflow_id', ''),
                        'reason': action.get('reason') or context.get('reason', 'self_healing'),
                        'plan_id': action.get('plan_id') or context.get('plan_id', ''),
                        'affected_tickets': affected_tickets,
                    },
                    'context': {
                        'last_reallocation_timestamp': context.get('last_reallocation_timestamp', 0),
                        'workflow_state': context.get('workflow_state', ''),
                        'incident_id': context.get('incident_id', ''),
                        'playbook_name': context.get('playbook_name', ''),
                    }
                }
            }

            # Evaluate policy
            policy_path = 'neuralhive/self_healing/playbook_validation'
            result = await self.opa_client.evaluate_policy(policy_path, opa_input)

            # Check for violations
            violations = result.get('result', {}).get('violations', [])

            if violations:
                OPA_VALIDATION_TOTAL.labels(action=action_type, result='denied').inc()
                logger.warning(
                    'playbook_executor.opa_validation_denied',
                    action=action_type,
                    violations=violations
                )
                return False

            OPA_VALIDATION_TOTAL.labels(action=action_type, result='allowed').inc()
            logger.info(
                'playbook_executor.opa_validation_allowed',
                action=action_type
            )
            return True

        except Exception as e:
            OPA_VALIDATION_TOTAL.labels(action=action_type, result='error').inc()
            logger.error(
                'playbook_executor.opa_validation_error',
                action=action_type,
                error=str(e)
            )

            if self.opa_fail_open:
                logger.warning(
                    'playbook_executor.opa_fail_open_allowing',
                    action=action_type
                )
                return True
            else:
                return False

    def _get_action_handler(self, action_type: str) -> Optional[Callable[[dict, dict], Any]]:
        """Retorna handler da ação ou None se não existir."""
        action_map = {
            "restart_pod": self._restart_pod,
            "scale_deployment": self._scale_deployment,
            "update_policy": self._update_policy,
            "reallocate_ticket": self._reallocate_ticket,
            "notify_agent": self._notify_agent,
            "update_ticket_status": self._update_ticket_status,
            "check_worker_health": self._check_worker_health,
            "check_consumer_lag": self._check_consumer_lag,
            "pause_producers": self._pause_producers,
            "cleanup_poison_messages": self._cleanup_poison_messages,
            "restart_workflow": self._restart_workflow,
            "pause_workflow": self._pause_workflow,
            "trigger_replanning": self._trigger_replanning,
            "get_workflow_status": self._get_workflow_status,
        }
        return action_map.get(action_type)

    def _normalize_action(self, action: dict, context: dict) -> dict:
        """Flattens parameters and resolves placeholders in ações."""
        normalized = dict(action)
        if "type" not in normalized and "action" in normalized:
            normalized["type"] = normalized.get("action")

        parameters = normalized.get("parameters", {})
        for key, value in parameters.items():
            normalized[key] = self._resolve_placeholder(value, context)

        return normalized

    def _resolve_placeholder(self, value, context: dict):
        """Resolve placeholders simples no formato {{ key }} usando o contexto."""
        if isinstance(value, str) and value.strip().startswith("{{") and value.strip().endswith("}}"):
            key = value.strip().strip("{{").strip("}}").strip()
            return context.get(key)
        return value

    async def _restart_pod(self, action: dict, context: dict) -> dict:
        """Restart a pod by deleting it"""
        try:
            pod_name = context.get("pod_name") or action.get("pod_name")
            namespace = context.get("namespace") or action.get("namespace", "default")

            self.core_v1.delete_namespaced_pod(pod_name, namespace)
            logger.info("playbook_executor.pod_restarted", pod=pod_name, namespace=namespace)

            return {"success": True, "action": "restart_pod", "pod": pod_name}
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
            logger.error("playbook_executor.scale_deployment_failed", error=str(e))
            return {"success": False, "action": "scale_deployment", "error": str(e)}

    async def _update_policy(self, action: dict, context: dict) -> dict:
        """Update a policy (placeholder)"""
        logger.info("playbook_executor.update_policy", action=action)
        return {"success": True, "action": "update_policy", "note": "Policy update not yet implemented"}

    async def _reallocate_ticket(self, action: dict, context: dict) -> dict:
        """Reallocate ticket(s) for re-execution via Execution Ticket Service."""
        ticket_id = action.get("ticket_id") or context.get("ticket_id")
        affected_tickets = action.get("affected_tickets") or context.get("affected_tickets") or []
        previous_worker = action.get("previous_worker_id") or context.get("worker_id")
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        reason = action.get("reason") or context.get("reason", "self_healing_reallocation")

        if ticket_id:
            affected_tickets = [ticket_id]

        logger.info(
            "playbook_executor.reallocate_ticket",
            tickets=affected_tickets,
            previous_worker=previous_worker,
            workflow_id=workflow_id,
            reason=reason
        )

        # Fail-safe: if client is not available, return success with warning
        if not self.execution_ticket_client:
            logger.warning(
                'playbook_executor.execution_ticket_client_unavailable',
                tickets=affected_tickets,
                action='reallocate_ticket'
            )
            return {
                "success": True,
                "action": "reallocate_ticket",
                "tickets": affected_tickets,
                "previous_worker": previous_worker,
                "warning": "Execution Ticket Service unavailable, action skipped"
            }

        try:
            if len(affected_tickets) == 1:
                # Single ticket reallocation
                result = await self.execution_ticket_client.reallocate_ticket(
                    ticket_id=affected_tickets[0],
                    reason=reason,
                    metadata={
                        'workflow_id': workflow_id,
                        'previous_worker': previous_worker,
                        'incident_id': context.get('incident_id'),
                    }
                )
                logger.info(
                    'playbook_executor.ticket_reallocated',
                    ticket_id=affected_tickets[0],
                    reallocation_id=result.get('reallocation_id')
                )
                return {
                    "success": True,
                    "action": "reallocate_ticket",
                    "tickets": affected_tickets,
                    "previous_worker": previous_worker,
                    "reallocated": True,
                    "reallocation_id": result.get('reallocation_id')
                }
            else:
                # Batch reallocation
                result = await self.execution_ticket_client.reallocate_multiple_tickets(
                    ticket_ids=affected_tickets,
                    reason=reason,
                    metadata={
                        'workflow_id': workflow_id,
                        'previous_worker': previous_worker,
                        'incident_id': context.get('incident_id'),
                    }
                )
                logger.info(
                    'playbook_executor.tickets_reallocated_batch',
                    batch_id=result.get('batch_id'),
                    total=result.get('total'),
                    successful=result.get('successful'),
                    failed=result.get('failed')
                )
                return {
                    "success": result.get('failed', 0) == 0,
                    "action": "reallocate_ticket",
                    "tickets": affected_tickets,
                    "previous_worker": previous_worker,
                    "reallocated": True,
                    "batch_id": result.get('batch_id'),
                    "successful_count": result.get('successful'),
                    "failed_count": result.get('failed')
                }

        except Exception as e:
            logger.error(
                'playbook_executor.reallocate_ticket_failed',
                tickets=affected_tickets,
                error=str(e)
            )
            return {
                "success": False,
                "action": "reallocate_ticket",
                "tickets": affected_tickets,
                "error": str(e)
            }

    async def _notify_agent(self, action: dict, context: dict) -> dict:
        """Notifica agente via Service Registry/Kafka (stub)."""
        agent_id = action.get("agent_id") or context.get("agent_id")
        notification_type = action.get("notification_type") or "INFO"
        message = action.get("message") or ""
        metadata = action.get("metadata") or {}

        logger.info(
            "playbook_executor.notify_agent",
            agent_id=agent_id,
            notification_type=notification_type,
            message=message,
            metadata=metadata
        )

        sent = False
        if self.service_registry_client:
            sent = await self.service_registry_client.notify_agent(
                agent_id=agent_id,
                notification={
                    "notification_type": notification_type,
                    "message": message,
                    "metadata": metadata
                }
            )

        return {
            "success": True if sent or not self.service_registry_client else False,
            "action": "notify_agent",
            "agent_id": agent_id,
            "notification_type": notification_type
        }

    async def _update_ticket_status(self, action: dict, context: dict) -> dict:
        """Update ticket status via Execution Ticket Service."""
        ticket_id = action.get("ticket_id") or context.get("ticket_id")
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        status = action.get("status") or context.get("status", "UNKNOWN")
        result_data = action.get("result") or context.get("result")

        logger.info(
            "playbook_executor.update_ticket_status",
            ticket_id=ticket_id,
            workflow_id=workflow_id,
            status=status
        )

        # Fail-safe: if client is not available, return success with warning
        if not self.execution_ticket_client:
            logger.warning(
                'playbook_executor.execution_ticket_client_unavailable',
                ticket_id=ticket_id,
                action='update_ticket_status'
            )
            return {
                "success": True,
                "action": "update_ticket_status",
                "ticket_id": ticket_id,
                "status": status,
                "warning": "Execution Ticket Service unavailable, action skipped"
            }

        try:
            result = await self.execution_ticket_client.update_ticket_status(
                ticket_id=ticket_id,
                status=status,
                result=result_data,
                metadata={
                    'workflow_id': workflow_id,
                    'updated_by': 'self-healing-engine',
                    'incident_id': context.get('incident_id'),
                }
            )

            logger.info(
                'playbook_executor.ticket_status_updated',
                ticket_id=ticket_id,
                status=status
            )

            return {
                "success": True,
                "action": "update_ticket_status",
                "ticket_id": ticket_id,
                "status": status,
                "updated": True
            }

        except Exception as e:
            logger.error(
                'playbook_executor.update_ticket_status_failed',
                ticket_id=ticket_id,
                status=status,
                error=str(e)
            )
            return {
                "success": False,
                "action": "update_ticket_status",
                "ticket_id": ticket_id,
                "status": status,
                "error": str(e)
            }

    async def _restart_workflow(self, action: dict, context: dict) -> dict:
        """Resume/restart a paused workflow via Orchestrator gRPC."""
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        reason = action.get("reason") or context.get("reason", "self_healing_restart")

        logger.info(
            "playbook_executor.restart_workflow",
            workflow_id=workflow_id,
            reason=reason
        )

        # Fail-safe: if client is not available, return success with warning
        if not self.orchestrator_client:
            logger.warning(
                'playbook_executor.orchestrator_client_unavailable',
                workflow_id=workflow_id,
                action='restart_workflow'
            )
            return {
                "success": True,
                "action": "restart_workflow",
                "workflow_id": workflow_id,
                "warning": "Orchestrator unavailable, action skipped"
            }

        try:
            # First, get workflow status to check if it's paused
            status = await self.orchestrator_client.get_workflow_status(
                workflow_id=workflow_id,
                include_tickets=False
            )

            workflow_state = status.get('state', 'UNKNOWN')

            if workflow_state == 'PAUSED':
                # Resume the paused workflow
                result = await self.orchestrator_client.resume_workflow(
                    workflow_id=workflow_id,
                    reason=reason
                )

                logger.info(
                    'playbook_executor.workflow_resumed',
                    workflow_id=workflow_id,
                    success=result.get('success'),
                    pause_duration_seconds=result.get('pause_duration_seconds')
                )

                return {
                    "success": result.get('success', False),
                    "action": "restart_workflow",
                    "workflow_id": workflow_id,
                    "previous_state": workflow_state,
                    "resumed": True,
                    "pause_duration_seconds": result.get('pause_duration_seconds')
                }

            elif workflow_state in ('COMPLETED', 'FAILED', 'CANCELLED'):
                logger.warning(
                    'playbook_executor.workflow_in_terminal_state',
                    workflow_id=workflow_id,
                    state=workflow_state
                )
                return {
                    "success": False,
                    "action": "restart_workflow",
                    "workflow_id": workflow_id,
                    "state": workflow_state,
                    "error": f"Workflow in terminal state: {workflow_state}"
                }

            else:
                # Workflow is running or in another non-paused state
                logger.info(
                    'playbook_executor.workflow_not_paused',
                    workflow_id=workflow_id,
                    state=workflow_state
                )
                return {
                    "success": True,
                    "action": "restart_workflow",
                    "workflow_id": workflow_id,
                    "state": workflow_state,
                    "note": "Workflow not paused, no action taken"
                }

        except Exception as e:
            logger.error(
                'playbook_executor.restart_workflow_failed',
                workflow_id=workflow_id,
                error=str(e)
            )
            return {
                "success": False,
                "action": "restart_workflow",
                "workflow_id": workflow_id,
                "error": str(e)
            }

    async def _pause_workflow(self, action: dict, context: dict) -> dict:
        """Pause a running workflow via Orchestrator gRPC."""
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        reason = action.get("reason") or context.get("reason", "self_healing_investigation")
        duration_seconds = action.get("duration_seconds") or context.get("pause_duration_seconds")

        logger.info(
            "playbook_executor.pause_workflow",
            workflow_id=workflow_id,
            reason=reason,
            duration_seconds=duration_seconds
        )

        if not self.orchestrator_client:
            logger.warning(
                'playbook_executor.orchestrator_client_unavailable',
                workflow_id=workflow_id,
                action='pause_workflow'
            )
            return {
                "success": True,
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "warning": "Orchestrator unavailable, action skipped"
            }

        try:
            result = await self.orchestrator_client.pause_workflow(
                workflow_id=workflow_id,
                reason=reason,
                duration_seconds=duration_seconds
            )

            logger.info(
                'playbook_executor.workflow_paused',
                workflow_id=workflow_id,
                success=result.get('success')
            )

            return {
                "success": result.get('success', False),
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "paused": True,
                "paused_at": result.get('paused_at'),
                "scheduled_resume_at": result.get('scheduled_resume_at')
            }

        except Exception as e:
            logger.error(
                'playbook_executor.pause_workflow_failed',
                workflow_id=workflow_id,
                error=str(e)
            )
            return {
                "success": False,
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "error": str(e)
            }

    async def _trigger_replanning(self, action: dict, context: dict) -> dict:
        """Trigger replanning for a workflow plan via Orchestrator gRPC."""
        plan_id = action.get("plan_id") or context.get("plan_id")
        reason = action.get("reason") or context.get("reason", "self_healing_replanning")
        trigger_type = action.get("trigger_type") or "TRIGGER_TYPE_FAILURE"
        preserve_progress = action.get("preserve_progress", True)

        logger.info(
            "playbook_executor.trigger_replanning",
            plan_id=plan_id,
            reason=reason,
            trigger_type=trigger_type
        )

        if not self.orchestrator_client:
            logger.warning(
                'playbook_executor.orchestrator_client_unavailable',
                plan_id=plan_id,
                action='trigger_replanning'
            )
            return {
                "success": True,
                "action": "trigger_replanning",
                "plan_id": plan_id,
                "warning": "Orchestrator unavailable, action skipped"
            }

        try:
            result = await self.orchestrator_client.trigger_replanning(
                plan_id=plan_id,
                reason=reason,
                trigger_type=trigger_type,
                preserve_progress=preserve_progress,
                context={
                    'incident_id': context.get('incident_id', ''),
                    'triggered_by': 'self-healing-engine',
                }
            )

            logger.info(
                'playbook_executor.replanning_triggered',
                plan_id=plan_id,
                replanning_id=result.get('replanning_id'),
                success=result.get('success')
            )

            return {
                "success": result.get('success', False),
                "action": "trigger_replanning",
                "plan_id": plan_id,
                "replanning_id": result.get('replanning_id'),
                "triggered_at": result.get('triggered_at')
            }

        except Exception as e:
            logger.error(
                'playbook_executor.trigger_replanning_failed',
                plan_id=plan_id,
                error=str(e)
            )
            return {
                "success": False,
                "action": "trigger_replanning",
                "plan_id": plan_id,
                "error": str(e)
            }

    async def _get_workflow_status(self, action: dict, context: dict) -> dict:
        """Get workflow status from Orchestrator."""
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        include_tickets = action.get("include_tickets", True)

        logger.info(
            "playbook_executor.get_workflow_status",
            workflow_id=workflow_id
        )

        if not self.orchestrator_client:
            logger.warning(
                'playbook_executor.orchestrator_client_unavailable',
                workflow_id=workflow_id,
                action='get_workflow_status'
            )
            return {
                "success": True,
                "action": "get_workflow_status",
                "workflow_id": workflow_id,
                "warning": "Orchestrator unavailable"
            }

        try:
            result = await self.orchestrator_client.get_workflow_status(
                workflow_id=workflow_id,
                include_tickets=include_tickets
            )

            # Update context with workflow state for subsequent actions
            context['workflow_state'] = result.get('state')

            return {
                "success": True,
                "action": "get_workflow_status",
                "workflow_id": workflow_id,
                "state": result.get('state'),
                "progress_percent": result.get('progress_percent'),
                "tickets": result.get('tickets')
            }

        except Exception as e:
            logger.error(
                'playbook_executor.get_workflow_status_failed',
                workflow_id=workflow_id,
                error=str(e)
            )
            return {
                "success": False,
                "action": "get_workflow_status",
                "workflow_id": workflow_id,
                "error": str(e)
            }

    async def _check_worker_health(self, action: dict, context: dict) -> dict:
        """Verifica saúde do worker via Service Registry (stub)."""
        worker_id = action.get("worker_id") or context.get("worker_id")
        namespace = action.get("namespace") or context.get("namespace")

        logger.info(
            "playbook_executor.check_worker_health",
            worker_id=worker_id,
            namespace=namespace
        )

        healthy = True
        if self.service_registry_client:
            agent_info = await self.service_registry_client.get_agent_info(worker_id)
            if agent_info and agent_info.get("status") not in [1]:  # 1 = HEALTHY
                healthy = False
        context["worker_unhealthy"] = not healthy
        return {"success": True, "action": "check_worker_health", "worker_id": worker_id, "healthy": healthy}

    async def _check_consumer_lag(self, action: dict, context: dict) -> dict:
        """Checa lag do consumer group (stub)."""
        consumer_group = action.get("consumer_group") or context.get("consumer_group")
        topic = action.get("topic") or context.get("topic")
        lag_threshold = int(action.get("lag_threshold") or context.get("lag_threshold") or 0)

        logger.info(
            "playbook_executor.check_consumer_lag",
            consumer_group=consumer_group,
            topic=topic,
            lag_threshold=lag_threshold
        )
        context["consumer_lag_checked"] = True
        return {"success": True, "action": "check_consumer_lag", "lag_below_threshold": True}

    async def _pause_producers(self, action: dict, context: dict) -> dict:
        """Pausa produtores temporariamente (stub)."""
        topic = action.get("topic") or context.get("topic")
        consumer_group = action.get("consumer_group") or context.get("consumer_group")
        logger.info("playbook_executor.pause_producers", topic=topic, consumer_group=consumer_group)
        return {"success": True, "action": "pause_producers", "topic": topic}

    async def _cleanup_poison_messages(self, action: dict, context: dict) -> dict:
        """Remove mensagens poison pill (stub)."""
        topic = action.get("topic") or context.get("topic")
        logger.info("playbook_executor.cleanup_poison_messages", topic=topic)
        return {"success": True, "action": "cleanup_poison_messages", "topic": topic}

    async def _maybe_call_callback(self, callback: Callable, payload: dict):
        """Executa callback síncrono ou assíncrono (fail-open)."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(payload)
            else:
                callback(payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("playbook_executor.callback_failed", error=str(e))

    def _record_metrics(self, playbook_name: str, status: str, duration_seconds: float):
        """Atualiza métricas de execução de playbook."""
        try:
            self.playbook_execution_total.labels(playbook=playbook_name, status=status).inc()
            self.playbook_execution_duration_seconds.labels(playbook=playbook_name).observe(duration_seconds)
        except Exception as e:  # noqa: BLE001
            logger.warning("playbook_executor.metrics_failed", error=str(e))
