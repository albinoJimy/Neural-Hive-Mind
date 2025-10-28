"""Remediation coordinator for self-healing playbooks (Fluxo E4)"""
from typing import Dict, Any, Optional, List
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
        """Reinicia pod"""
        selector = action.get("selector", "app")
        resources = incident.get("affected_resources", [])

        logger.info("remediation_coordinator.restarting_pod", selector=selector)

        if self.k8s:
            # TODO: Delete pod para forçar restart
            pass

        return {
            "success": True,
            "action_type": RemediationType.RESTART_POD,
            "details": {"selector": selector, "resources": resources}
        }

    async def _scale_deployment(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Escala deployment"""
        replicas = action.get("replicas", 3)
        resources = incident.get("affected_resources", [])

        logger.info("remediation_coordinator.scaling_deployment", replicas=replicas)

        if self.k8s:
            # TODO: Patch deployment scale
            pass

        return {
            "success": True,
            "action_type": RemediationType.SCALE_DEPLOYMENT,
            "details": {"replicas": replicas, "resources": resources}
        }

    async def _rollback_deployment(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Faz rollback de deployment"""
        revision = action.get("revision", "previous")

        logger.info("remediation_coordinator.rolling_back_deployment", revision=revision)

        if self.k8s:
            # TODO: kubectl rollout undo deployment
            pass

        return {
            "success": True,
            "action_type": RemediationType.ROLLBACK_DEPLOYMENT,
            "details": {"revision": revision}
        }

    async def _apply_network_policy(
        self, action: Dict[str, Any], incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aplica NetworkPolicy"""
        target = action.get("target")

        logger.info("remediation_coordinator.applying_network_policy", target=target)

        if self.k8s:
            # TODO: Apply K8s NetworkPolicy
            pass

        return {
            "success": True,
            "action_type": RemediationType.APPLY_NETWORK_POLICY,
            "details": {"target": target}
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
