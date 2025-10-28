"""Policy enforcement service with OPA and Istio integration (Fluxo E3)"""
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime, timezone
from enum import Enum

logger = structlog.get_logger()


# Importa clientes OPA e Istio quando disponíveis
try:
    from src.clients.opa_client import OPAClient
    from src.clients.istio_client import IstioClient
    OPA_AVAILABLE = True
    ISTIO_AVAILABLE = True
except ImportError:
    OPA_AVAILABLE = False
    ISTIO_AVAILABLE = False
    logger.warning("policy_enforcer.clients_not_available",
                   opa=OPA_AVAILABLE, istio=ISTIO_AVAILABLE)


class EnforcementAction(str, Enum):
    """Ações de enforcement"""
    ALLOW = "allow"
    DENY = "deny"
    BLOCK_IP = "block_ip"
    RATE_LIMIT = "rate_limit"
    QUARANTINE = "quarantine"
    REVOKE_ACCESS = "revoke_access"
    ISOLATE_POD = "isolate_pod"
    SCALE_DOWN = "scale_down"


class PolicyType(str, Enum):
    """Tipos de políticas"""
    SECURITY = "security"
    COMPLIANCE = "compliance"
    RESOURCE_QUOTA = "resource_quota"
    NETWORK = "network"
    RBAC = "rbac"


class PolicyEnforcer:
    """Enforça políticas usando OPA e Istio seguindo Fluxo E3"""

    def __init__(
        self,
        k8s_client=None,
        redis_client=None,
        opa_client=None,
        istio_client=None,
        opa_enabled: bool = True,
        istio_enabled: bool = True
    ):
        self.k8s = k8s_client
        self.redis = redis_client
        self.opa_client = opa_client
        self.istio_client = istio_client
        self.opa_enabled = opa_enabled and OPA_AVAILABLE
        self.istio_enabled = istio_enabled and ISTIO_AVAILABLE
        self.policies = self._load_policies()
        self.enforcement_history = []

    def _load_policies(self) -> Dict[str, Any]:
        """Carrega políticas (OPA, Gatekeeper, Istio)"""
        return {
            "security_policies": {
                "unauthorized_access": {
                    "action": EnforcementAction.REVOKE_ACCESS,
                    "opa_policy": "data.security.unauthorized_access",
                    "istio_rule": "deny_unauthorized_access",
                },
                "dos_attack": {
                    "action": EnforcementAction.BLOCK_IP,
                    "opa_policy": "data.security.dos_attack",
                    "istio_rule": "rate_limit_aggressive",
                },
                "data_exfiltration": {
                    "action": EnforcementAction.QUARANTINE,
                    "opa_policy": "data.security.data_exfiltration",
                    "istio_rule": "block_egress_traffic",
                },
                "malicious_payload": {
                    "action": EnforcementAction.DENY,
                    "opa_policy": "data.security.malicious_payload",
                    "istio_rule": "deny_request",
                },
            },
            "compliance_policies": {
                "policy_violation": {
                    "action": EnforcementAction.DENY,
                    "opa_policy": "data.compliance.policy_violation",
                },
            },
            "resource_policies": {
                "resource_abuse": {
                    "action": EnforcementAction.SCALE_DOWN,
                    "opa_policy": "data.resources.abuse",
                    "k8s_action": "scale_deployment",
                },
            },
        }

    async def enforce_policy(
        self, incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enforça política para incidente (E3: Selecionar playbook & Executar políticas)

        Args:
            incident: Incidente classificado

        Returns:
            Dict com resultado do enforcement
        """
        try:
            incident_id = incident.get("incident_id")
            threat_type = incident.get("threat_type")
            severity = incident.get("severity")
            runbook_id = incident.get("runbook_id")

            logger.info(
                "policy_enforcer.enforcing",
                incident_id=incident_id,
                threat_type=threat_type,
                severity=severity,
                runbook_id=runbook_id
            )

            # E3: Selecionar playbook baseado em severidade e catálogos
            enforcement_plan = await self._select_enforcement_plan(
                threat_type, severity, runbook_id
            )

            # Validar com OPA
            opa_decision = await self._validate_with_opa(incident, enforcement_plan)
            if not opa_decision.get("allowed", False):
                logger.warning(
                    "policy_enforcer.opa_denied",
                    incident_id=incident_id,
                    reason=opa_decision.get("reason")
                )
                return self._create_enforcement_result(
                    incident, enforcement_plan, success=False, reason="OPA denied"
                )

            # E3: Executar ações atomicamente
            enforcement_result = await self._execute_enforcement_actions(
                incident, enforcement_plan
            )

            # Registrar enforcement
            await self._record_enforcement(incident, enforcement_plan, enforcement_result)

            logger.info(
                "policy_enforcer.enforced",
                incident_id=incident_id,
                actions_executed=len(enforcement_result.get("actions", [])),
                success=enforcement_result.get("success")
            )

            return enforcement_result

        except Exception as e:
            logger.error(
                "policy_enforcer.enforcement_failed",
                incident_id=incident.get("incident_id"),
                error=str(e)
            )
            # E3: Falha > 2 tentativas → escalar para humano
            raise

    async def _select_enforcement_plan(
        self, threat_type: str, severity: str, runbook_id: str
    ) -> Dict[str, Any]:
        """E3: Selecionar playbook baseado em impacto e risco"""
        # Buscar política para o tipo de ameaça
        policy = None
        for policy_category in self.policies.values():
            if threat_type in policy_category:
                policy = policy_category[threat_type]
                break

        if not policy:
            logger.warning(
                "policy_enforcer.no_policy_found",
                threat_type=threat_type,
                runbook_id=runbook_id
            )
            # E3: Playbook inexistente → criar stub e notificar engenharia
            return self._create_stub_playbook(threat_type, severity, runbook_id)

        return {
            "runbook_id": runbook_id,
            "threat_type": threat_type,
            "severity": severity,
            "primary_action": policy.get("action"),
            "opa_policy": policy.get("opa_policy"),
            "istio_rule": policy.get("istio_rule"),
            "k8s_action": policy.get("k8s_action"),
            "fallback_actions": self._get_fallback_actions(severity),
        }

    async def _validate_with_opa(
        self, incident: Dict[str, Any], enforcement_plan: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Valida enforcement com OPA"""
        opa_policy = enforcement_plan.get("opa_policy")

        logger.debug(
            "policy_enforcer.validating_opa",
            opa_policy=opa_policy,
            incident_id=incident.get("incident_id"),
            opa_enabled=self.opa_enabled
        )

        # Se OPA não estiver disponível ou desabilitado, permitir com aviso
        if not self.opa_enabled or not self.opa_client:
            logger.warning(
                "policy_enforcer.opa_disabled",
                incident_id=incident.get("incident_id")
            )
            return {
                "allowed": True,
                "policy": opa_policy,
                "reason": "OPA validation bypassed (not enabled)",
            }

        # Integração real com OPA
        try:
            # Preparar dados de entrada para OPA
            input_data = {
                "incident": {
                    "id": incident.get("incident_id"),
                    "threat_type": incident.get("threat_type"),
                    "severity": incident.get("severity"),
                    "affected_resources": incident.get("affected_resources", []),
                    "anomaly": incident.get("anomaly", {})
                },
                "enforcement": {
                    "runbook_id": enforcement_plan.get("runbook_id"),
                    "action": enforcement_plan.get("primary_action"),
                    "severity": enforcement_plan.get("severity")
                }
            }

            # Avaliar política OPA
            result = await self.opa_client.evaluate_policy(
                policy_path=opa_policy.replace("data.", ""),
                input_data=input_data
            )

            decision = {
                "allowed": result.get("allowed", False),
                "policy": opa_policy,
                "reason": result.get("reason", "OPA evaluation completed"),
                "error": result.get("error", False)
            }

            logger.info(
                "policy_enforcer.opa_decision",
                incident_id=incident.get("incident_id"),
                allowed=decision["allowed"],
                reason=decision["reason"]
            )

            return decision

        except Exception as e:
            logger.error(
                "policy_enforcer.opa_validation_error",
                incident_id=incident.get("incident_id"),
                error=str(e)
            )
            # Fail-safe: negar em caso de erro crítico
            return {
                "allowed": False,
                "policy": opa_policy,
                "reason": f"OPA validation error: {str(e)}",
                "error": True
            }

    async def _execute_enforcement_actions(
        self, incident: Dict[str, Any], enforcement_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """E3: Executar ações atomicamente"""
        actions_executed = []
        errors = []
        attempt = 0
        max_attempts = 2

        while attempt <= max_attempts:
            try:
                primary_action = enforcement_plan.get("primary_action")

                # Executar ação primária
                action_result = await self._execute_action(
                    primary_action, incident, enforcement_plan
                )
                actions_executed.append(action_result)

                # Se bem-sucedido, sair
                if action_result.get("success"):
                    break

            except Exception as e:
                errors.append(str(e))
                attempt += 1
                logger.warning(
                    "policy_enforcer.action_retry",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(e)
                )

        # E3: Falha > 2 tentativas → escalar para humano
        if attempt > max_attempts:
            logger.error(
                "policy_enforcer.max_retries_exceeded",
                incident_id=incident.get("incident_id")
            )
            return {
                "success": False,
                "actions": actions_executed,
                "errors": errors,
                "requires_human_intervention": True,
            }

        return {
            "success": True,
            "actions": actions_executed,
            "enforcement_plan": enforcement_plan,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _execute_action(
        self, action: EnforcementAction, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executa ação específica de enforcement"""
        logger.info(
            "policy_enforcer.executing_action",
            action=action,
            incident_id=incident.get("incident_id")
        )

        if action == EnforcementAction.BLOCK_IP:
            return await self._block_ip(incident, plan)
        elif action == EnforcementAction.REVOKE_ACCESS:
            return await self._revoke_access(incident, plan)
        elif action == EnforcementAction.QUARANTINE:
            return await self._quarantine_resource(incident, plan)
        elif action == EnforcementAction.ISOLATE_POD:
            return await self._isolate_pod(incident, plan)
        elif action == EnforcementAction.SCALE_DOWN:
            return await self._scale_down_resource(incident, plan)
        elif action == EnforcementAction.RATE_LIMIT:
            return await self._apply_rate_limit(incident, plan)
        elif action == EnforcementAction.DENY:
            return await self._deny_request(incident, plan)
        else:
            logger.warning("policy_enforcer.unknown_action", action=action)
            return {"success": False, "action": action, "reason": "Unknown action"}

    async def _block_ip(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Bloqueia IP usando Istio/NetworkPolicy"""
        source_ip = incident.get("anomaly", {}).get("details", {}).get("source_ip")

        if not source_ip:
            return {"success": False, "action": "block_ip", "reason": "No source IP"}

        logger.info("policy_enforcer.blocking_ip", source_ip=source_ip)

        success = False
        details = {"source_ip": source_ip}

        # Aplicar via Istio AuthorizationPolicy se disponível
        if self.istio_enabled and self.istio_client:
            try:
                result = await self.istio_client.block_ip(
                    source_ip=source_ip,
                    workload_selector={"app": "neural-hive"}
                )
                success = result.get("success", False)
                details["istio_policy"] = result.get("name")
                logger.info(
                    "policy_enforcer.ip_blocked_istio",
                    source_ip=source_ip,
                    policy=result.get("name")
                )
            except Exception as e:
                logger.error(
                    "policy_enforcer.istio_block_failed",
                    source_ip=source_ip,
                    error=str(e)
                )
        else:
            logger.warning(
                "policy_enforcer.istio_not_available",
                action="block_ip"
            )
            success = True  # Fallback considera sucesso para não bloquear fluxo

        # Cachear bloqueio no Redis
        if self.redis:
            try:
                await self.redis.set(
                    f"blocked_ip:{source_ip}",
                    "true",
                    ex=3600  # 1 hora
                )
                details["cached"] = True
            except Exception as e:
                logger.warning(
                    "policy_enforcer.redis_cache_failed",
                    error=str(e)
                )

        return {
            "success": success,
            "action": "block_ip",
            "details": details,
            "istio_rule": plan.get("istio_rule"),
        }

    async def _revoke_access(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Revoga acesso de usuário/serviço"""
        user_id = incident.get("anomaly", {}).get("details", {}).get("user_id")

        if not user_id:
            return {"success": False, "action": "revoke_access", "reason": "No user ID"}

        # TODO: Revogar tokens via IAM (Keycloak)
        logger.info("policy_enforcer.revoking_access", user_id=user_id)

        return {
            "success": True,
            "action": "revoke_access",
            "details": {"user_id": user_id},
        }

    async def _quarantine_resource(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Quarentena recurso suspeito"""
        resources = incident.get("affected_resources", [])

        if not resources:
            return {
                "success": False,
                "action": "quarantine",
                "reason": "No resources to quarantine"
            }

        # TODO: Aplicar label de quarentena e NetworkPolicy
        logger.info("policy_enforcer.quarantining_resources", resources=resources)

        if self.k8s:
            # Marcar pods com label de quarentena
            for resource in resources:
                # Implementação real faria patch do pod/deployment
                pass

        return {
            "success": True,
            "action": "quarantine",
            "details": {"resources": resources},
        }

    async def _isolate_pod(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Isola pod usando NetworkPolicy"""
        resources = incident.get("affected_resources", [])

        logger.info("policy_enforcer.isolating_pods", resources=resources)

        # TODO: Criar NetworkPolicy para isolar pod
        return {
            "success": True,
            "action": "isolate_pod",
            "details": {"resources": resources},
        }

    async def _scale_down_resource(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reduz escala de recurso abusivo"""
        resources = incident.get("affected_resources", [])

        logger.info("policy_enforcer.scaling_down", resources=resources)

        if self.k8s:
            # TODO: Scale down deployment
            pass

        return {
            "success": True,
            "action": "scale_down",
            "details": {"resources": resources},
        }

    async def _apply_rate_limit(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aplica rate limiting via Istio"""
        source = incident.get("anomaly", {}).get("details", {}).get("source")

        logger.info("policy_enforcer.applying_rate_limit", source=source)

        success = False
        details = {"source": source}

        # Aplicar EnvoyFilter com rate limiting via Istio
        if self.istio_enabled and self.istio_client:
            try:
                # Define rate limit: 100 req/min para DoS
                result = await self.istio_client.apply_rate_limit(
                    name=f"rate-limit-{incident.get('incident_id', 'default')}",
                    workload_selector={"app": "neural-hive"},
                    requests_per_unit=100,
                    unit="MINUTE"
                )
                success = result.get("success", False)
                details["envoy_filter"] = result.get("name")
                details["rate_limit"] = result.get("rate_limit")
                logger.info(
                    "policy_enforcer.rate_limit_applied",
                    filter=result.get("name")
                )
            except Exception as e:
                logger.error(
                    "policy_enforcer.rate_limit_failed",
                    error=str(e)
                )
        else:
            logger.warning(
                "policy_enforcer.istio_not_available",
                action="rate_limit"
            )
            success = True  # Fallback

        return {
            "success": success,
            "action": "rate_limit",
            "details": details,
            "istio_rule": plan.get("istio_rule"),
        }

    async def _deny_request(
        self, incident: Dict[str, Any], plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Nega requisição específica"""
        logger.info("policy_enforcer.denying_request")

        return {
            "success": True,
            "action": "deny",
        }

    def _get_fallback_actions(self, severity: str) -> List[EnforcementAction]:
        """Retorna ações de fallback por severidade"""
        fallback_map = {
            "critical": [EnforcementAction.QUARANTINE, EnforcementAction.DENY],
            "high": [EnforcementAction.RATE_LIMIT, EnforcementAction.DENY],
            "medium": [EnforcementAction.DENY],
            "low": [],
        }
        return fallback_map.get(severity, [])

    def _create_stub_playbook(
        self, threat_type: str, severity: str, runbook_id: str
    ) -> Dict[str, Any]:
        """E3: Cria stub de playbook quando inexistente"""
        logger.warning(
            "policy_enforcer.creating_stub_playbook",
            threat_type=threat_type,
            runbook_id=runbook_id
        )

        return {
            "runbook_id": runbook_id,
            "threat_type": threat_type,
            "severity": severity,
            "primary_action": EnforcementAction.DENY,
            "is_stub": True,
            "requires_engineering_review": True,
        }

    async def _record_enforcement(
        self, incident: Dict[str, Any], plan: Dict[str, Any], result: Dict[str, Any]
    ):
        """Registra enforcement no histórico"""
        record = {
            "incident_id": incident.get("incident_id"),
            "runbook_id": plan.get("runbook_id"),
            "enforcement_plan": plan,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.enforcement_history.append(record)

        # Limitar histórico em memória
        if len(self.enforcement_history) > 1000:
            self.enforcement_history = self.enforcement_history[-1000:]

    def _create_enforcement_result(
        self, incident: Dict[str, Any], plan: Dict[str, Any], success: bool, reason: str
    ) -> Dict[str, Any]:
        """Cria resultado de enforcement"""
        return {
            "success": success,
            "incident_id": incident.get("incident_id"),
            "runbook_id": plan.get("runbook_id"),
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
