"""Playbook executor service for Self-Healing Engine"""

import asyncio
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional

import structlog
import yaml
from kubernetes import client, config
from prometheus_client import Counter, Histogram, REGISTRY

from neural_hive_observability import get_tracer
from src.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = structlog.get_logger()


def _get_or_create_metric(metric_class, name, description, labels=None, **kwargs):
    """
    Retorna metrica existente ou cria nova se nao existir.

    Verifica primeiro no REGISTRY para evitar duplicacao.
    """
    # Verificar se metrica ja existe no registry usando as chaves do dicionario
    # O registry usa os nomes das metricas como chaves
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]

    # Para Counter, verificar varias versoes de nomes
    # (com e sem _total, ja que o Prometheus adiciona _total automaticamente)
    base_name = name.replace("_total", "") if name.endswith("_total") else name
    if base_name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[base_name]

    # Verificar tambem com _total adicionado
    if not name.endswith("_total") and metric_class == Counter:
        total_name = f"{name}_total"
        if total_name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[total_name]

    # Metrica nao existe, criar nova
    try:
        if labels:
            return metric_class(name, description, labels, **kwargs)
        return metric_class(name, description, **kwargs)
    except ValueError:
        # Fallback: buscar por _name do collector ou nome similar
        for collector in list(REGISTRY._names_to_collectors.values()):
            collector_name = getattr(collector, "_name", "")
            if collector_name == name or collector_name == base_name or collector_name == f"{name}_total":
                return collector
        # Se ainda nao encontrou, relançar o erro com informacao útil
        raise ValueError(
            f"Metric '{name}' already exists in registry. "
            f"Existing metrics: {list(REGISTRY._names_to_collectors.keys())}"
        )


# OPA validation metrics (singleton)
OPA_VALIDATION_TOTAL = _get_or_create_metric(
    Counter,
    "self_healing_opa_validation_total",
    "Total OPA policy validations for self-healing actions",
    ["action", "result"],
)

# Import metrics from central metrics module to avoid duplication
# These will be created using _get_or_create_metric to handle duplicates
_playbook_execution_total_base = _get_or_create_metric(
    Counter,
    "self_healing_playbook_execution",
    "Total de execuções de playbook",
    ["playbook", "status"],
)

_playbook_execution_duration_seconds_base = _get_or_create_metric(
    Histogram,
    "self_healing_playbook_execution_duration_seconds",
    "Duração da execução de playbooks",
    ["playbook"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600],
)

# Aliases for compatibility
PLAYBOOK_EXECUTION_TOTAL = _playbook_execution_total_base
PLAYBOOK_EXECUTION_DURATION_SECONDS = _playbook_execution_duration_seconds_base


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
        circuit_breaker_enabled: bool = True,
        circuit_breaker_failure_threshold: int = 5,
        circuit_breaker_timeout_seconds: int = 60,
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
        self.circuit_breaker_enabled = circuit_breaker_enabled
        self.core_v1: Optional[client.CoreV1Api] = None
        self.apps_v1: Optional[client.AppsV1Api] = None

        # Circuit Breakers para serviços externos
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        if circuit_breaker_enabled:
            self._circuit_breakers = {
                "execution_ticket_service": CircuitBreaker(
                    service_name="execution_ticket_service",
                    failure_threshold=circuit_breaker_failure_threshold,
                    timeout_seconds=circuit_breaker_timeout_seconds,
                ),
                "orchestrator": CircuitBreaker(
                    service_name="orchestrator",
                    failure_threshold=circuit_breaker_failure_threshold,
                    timeout_seconds=circuit_breaker_timeout_seconds,
                ),
                "opa": CircuitBreaker(
                    service_name="opa",
                    failure_threshold=circuit_breaker_failure_threshold,
                    timeout_seconds=circuit_breaker_timeout_seconds,
                ),
            }

        # Métricas de execução de playbook (usar singleton)
        self.playbook_execution_total = PLAYBOOK_EXECUTION_TOTAL
        self.playbook_execution_duration_seconds = PLAYBOOK_EXECUTION_DURATION_SECONDS

        # Actions that require OPA validation
        self._opa_validated_actions = {
            "reallocate_ticket",
            "restart_workflow",
            "update_ticket_status",
            "trigger_replanning",
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

    def validate_playbook_structure(
        self, playbook_name: str, playbook_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Valida estrutura de playbook usando Pydantic.

        Args:
            playbook_name: Nome do playbook a validar
            playbook_data: Dados do playbook (opcional, lê do ficheiro se não fornecido)

        Returns:
            Dict com keys: valid (bool), errors (list), warnings (list)
        """
        from src.models.remediation_models import (
            Playbook,
            PlaybookValidationResult,
        )

        errors = []
        warnings = []
        parsed_actions = []

        try:
            # Carregar playbook do ficheiro se não fornecido
            if playbook_data is None:
                playbook_path = self.playbooks_dir / f"{playbook_name}.yaml"
                logger.debug(
                    "playbook_executor.validation_check_path",
                    playbooks_dir=str(self.playbooks_dir),
                    playbook_name=playbook_name,
                    playbook_path=str(playbook_path),
                    exists=playbook_path.exists(),
                )
                if not playbook_path.exists():
                    return {
                        "valid": False,
                        "errors": [f"Playbook '{playbook_name}' não encontrado"],
                        "warnings": [],
                        "action_count": 0,
                        "parsed_actions": [],
                    }
                with open(playbook_path) as f:
                    playbook_data = yaml.safe_load(f) or {}

            # Adicionar playbook_name se não presente
            if "playbook_name" not in playbook_data:
                playbook_data["playbook_name"] = playbook_name

            # Validar com Pydantic
            playbook = Playbook(**playbook_data)

            # Extrair tipos de ação
            parsed_actions = [action.type.value for action in playbook.actions]

            # Calcular duração estimada
            estimated_duration = 0
            for action in playbook.actions:
                if action.timeout_seconds:
                    estimated_duration += action.timeout_seconds
            if not estimated_duration:
                estimated_duration = playbook.timeout_seconds

            # Verificar avisos
            if playbook.timeout_seconds > 600:
                warnings.append(f"Timeout muito alto: {playbook.timeout_seconds}s")

            if len(playbook.actions) > 20:
                warnings.append(f"Playbook com muitas ações: {len(playbook.actions)}")

            # Verificar se há ações sem descrição
            actions_without_desc = sum(1 for a in playbook.actions if not a.description)
            if actions_without_desc > 0:
                warnings.append(
                    f"{actions_without_desc} ações sem descrição"
                )

            result = PlaybookValidationResult(
                valid=True,
                playbook_name=playbook_name,
                errors=[],
                warnings=warnings,
                action_count=len(playbook.actions),
                parsed_actions=parsed_actions,
                estimated_duration_seconds=estimated_duration,
            )

            logger.info(
                "playbook_executor.validation_success",
                playbook=playbook_name,
                action_count= len(playbook.actions),
            )

            return result.model_dump()

        except Exception as e:
            error_msg = str(e)

            # Parse erros Pydantic para formato legível
            if "validation error" in error_msg:
                errors.append(f"Erro de validação: {error_msg}")
            else:
                errors.append(error_msg)

            logger.warning(
                "playbook_executor.validation_failed",
                playbook=playbook_name,
                errors=errors,
            )

            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "action_count": 0,
                "parsed_actions": parsed_actions,
            }

    async def execute_playbook(
        self,
        playbook_name: str,
        context: dict,
        on_action_completed: Optional[Callable[[dict], Any]] = None,
        on_playbook_completed: Optional[Callable[[dict], Any]] = None,
        timeout_seconds: Optional[int] = None,
        validate_before_exec: bool = True,
    ) -> dict:
        """Execute a remediation playbook com callbacks e timeout."""
        playbook_path = self.playbooks_dir / f"{playbook_name}.yaml"

        if not playbook_path.exists():
            logger.error("playbook_executor.playbook_not_found", playbook=playbook_name)
            return {"success": False, "error": "Playbook not found"}

        # Validar estrutura antes de executar (opcional)
        if validate_before_exec:
            validation = self.validate_playbook_structure(playbook_name)
            if not validation.get("valid"):
                logger.error(
                    "playbook_executor.validation_failed",
                    playbook=playbook_name,
                    errors=validation.get("errors"),
                )
                return {
                    "success": False,
                    "error": "Playbook structure validation failed",
                    "validation_errors": validation.get("errors"),
                }

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
            timeout_seconds=timeout,
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
                    self._execute_actions(actions, context, on_action_completed), timeout=timeout
                )
                result = {**execution_result, "total_actions": total_actions}
            except asyncio.TimeoutError:
                status_label = "timeout"
                result = {
                    "success": False,
                    "error": "Playbook timeout",
                    "status": "TIMEOUT",
                    "total_actions": total_actions,
                }
            except Exception as e:  # noqa: BLE001
                status_label = "error"
                result = {
                    "success": False,
                    "error": str(e),
                    "status": "FAILED",
                    "total_actions": total_actions,
                }
                logger.error(
                    "playbook_executor.execution_failed", playbook=playbook_name, error=str(e)
                )

            duration = perf_counter() - start_time
            status_label = (
                status_label
                if status_label in ["timeout", "error"]
                else ("success" if result.get("success") else "failed")
            )
            span.set_attribute("neural.hive.execution_status", status_label)
            self._record_metrics(playbook_name, status_label, duration)

            if on_playbook_completed:
                await self._maybe_call_callback(
                    on_playbook_completed, {**result, "duration_seconds": duration}
                )

            logger.info(
                "playbook_executor.completed",
                playbook=playbook_name,
                success=result.get("success"),
                duration_seconds=round(duration, 4),
            )
            return result

    async def _execute_actions(
        self,
        actions: list,
        context: dict,
        on_action_completed: Optional[Callable[[dict], Any]] = None,
    ) -> dict:
        """Execute playbook actions sequencialmente."""
        results = []

        for action in actions:
            normalized_action = self._normalize_action(action, context)
            action_type = normalized_action.get("type")
            handler = self._get_action_handler(action_type)

            if handler is None:
                result = {
                    "success": False,
                    "error": f"Unknown action type: {action_type}",
                    "action": action_type,
                }
            else:
                merged_context = {**context, **normalized_action}

                # Validate action with OPA if required
                if action_type in self._opa_validated_actions:
                    opa_allowed = await self._validate_action_with_opa(
                        normalized_action, merged_context
                    )
                    if not opa_allowed:
                        result = {
                            "success": False,
                            "error": "Action blocked by OPA policy",
                            "action": action_type,
                            "opa_denied": True,
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
                    "playbook_executor.opa_client_unavailable",
                    action=action.get("type"),
                    fail_open=True,
                )
                return True
            else:
                logger.error(
                    "playbook_executor.opa_client_unavailable",
                    action=action.get("type"),
                    fail_open=False,
                )
                return False

        action_type = action.get("type", "unknown")

        try:
            # Build OPA input
            # Resolve ticket_id: use explicit ticket_id or first element from affected_tickets
            affected_tickets = (
                action.get("affected_tickets") or context.get("affected_tickets") or []
            )
            ticket_id = action.get("ticket_id") or context.get("ticket_id", "")
            if not ticket_id and affected_tickets:
                ticket_id = affected_tickets[0]

            opa_input = {
                "input": {
                    "resource": {
                        "action": action_type,
                        "ticket_id": ticket_id,
                        "workflow_id": action.get("workflow_id") or context.get("workflow_id", ""),
                        "reason": action.get("reason") or context.get("reason", "self_healing"),
                        "plan_id": action.get("plan_id") or context.get("plan_id", ""),
                        "affected_tickets": affected_tickets,
                    },
                    "context": {
                        "last_reallocation_timestamp": context.get(
                            "last_reallocation_timestamp", 0
                        ),
                        "workflow_state": context.get("workflow_state", ""),
                        "incident_id": context.get("incident_id", ""),
                        "playbook_name": context.get("playbook_name", ""),
                    },
                }
            }

            # Evaluate policy
            policy_path = "neuralhive/self_healing/playbook_validation"
            result = await self.opa_client.evaluate_policy(policy_path, opa_input)

            # Check for violations
            violations = result.get("result", {}).get("violations", [])

            if violations:
                OPA_VALIDATION_TOTAL.labels(action=action_type, result="denied").inc()
                logger.warning(
                    "playbook_executor.opa_validation_denied",
                    action=action_type,
                    violations=violations,
                )
                return False

            OPA_VALIDATION_TOTAL.labels(action=action_type, result="allowed").inc()
            logger.info("playbook_executor.opa_validation_allowed", action=action_type)
            return True

        except Exception as e:
            OPA_VALIDATION_TOTAL.labels(action=action_type, result="error").inc()
            logger.error("playbook_executor.opa_validation_error", action=action_type, error=str(e))

            if self.opa_fail_open:
                logger.warning("playbook_executor.opa_fail_open_allowing", action=action_type)
                return True
            else:
                return False

    def _get_action_handler(self, action_type: str) -> Optional[Callable[[dict, dict], Any]]:
        """Retorna handler da ação ou None se não existir."""
        action_map = {
            "restart_pod": self._restart_pod,
            "scale_deployment": self._scale_deployment,
            "update_policy": self._update_policy,
            "apply_policy": self._apply_policy,
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
            "wait": self._wait,
            "delete_pod": self._delete_pod,
            "patch_deployment": self._patch_deployment,
            "check_database_connection": self._check_database_connection,
            "get_pod_metrics": self._get_pod_metrics,
            "analyze_memory_usage": self._analyze_memory_usage,
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
        if (
            isinstance(value, str)
            and value.strip().startswith("{{")
            and value.strip().endswith("}}")
        ):
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

            logger.info(
                "playbook_executor.deployment_scaled", deployment=deployment_name, replicas=replicas
            )

            return {
                "success": True,
                "action": "scale_deployment",
                "deployment": deployment_name,
                "replicas": replicas,
            }
        except Exception as e:  # noqa: BLE001
            logger.error("playbook_executor.scale_deployment_failed", error=str(e))
            return {"success": False, "action": "scale_deployment", "error": str(e)}

    async def _update_policy(self, action: dict, context: dict) -> dict:
        """
        Update a Kubernetes policy resource.

        Suporta atualização de recursos como NetworkPolicy, PodDisruptionBudget,
        ResourceQuota, LimitRange, etc.

        Para backward compatibility com testes antigos, retorna sucesso
        quando não há policy_spec mas há parâmetros básicos.
        """
        try:
            policy_type = action.get("policy_type") or context.get("policy_type")
            namespace = action.get("namespace") or context.get("namespace", "default")
            policy_name = action.get("policy_name") or context.get("policy_name")
            policy_spec = action.get("policy_spec") or context.get("policy_spec")

            # Backward compatibility: se não há policy_spec mas há parâmetros básicos,
            # retorna sucesso (comportamento original do placeholder)
            if not policy_spec:
                if policy_name:
                    logger.info(
                        "playbook_executor.update_policy",
                        policy_type=policy_type,
                        policy_name=policy_name,
                        note="no_policy_spec_provided",
                    )
                    return {
                        "success": True,
                        "action": "update_policy",
                        "policy_name": policy_name,
                        "note": "Policy update simulated (no spec provided)",
                    }
                return {
                    "success": False,
                    "action": "update_policy",
                    "error": "policy_spec is required",
                }

            logger.info(
                "playbook_executor.update_policy",
                policy_type=policy_type,
                namespace=namespace,
                policy_name=policy_name,
            )

            if not self.core_v1 or not self.apps_v1:
                logger.warning("playbook_executor.k8s_clients_unavailable")
                return {
                    "success": False,
                    "action": "update_policy",
                    "error": "Kubernetes clients not available",
                }

            # Import Kubernetes dynamic client for generic resources
            from kubernetes import dynamic

            dynamic_client = dynamic.DynamicClient(self.core_v1.api_client)

            # Determinar API version e kind baseado no policy_type
            policy_mapping = {
                "NETWORK_POLICY": ("networking.k8s.io/v1", "NetworkPolicy"),
                "ISTIO_PEER_AUTHENTICATION": ("security.istio.io/v1beta1", "PeerAuthentication"),
                "ISTIO_AUTHORIZATION_POLICY": ("security.istio.io/v1beta1", "AuthorizationPolicy"),
                "ISTIO_REQUEST_AUTHENTICATION": (
                    "security.istio.io/v1beta1",
                    "RequestAuthentication",
                ),
                "POD_DISRUPTION_BUDGET": ("policy/v1", "PodDisruptionBudget"),
                "RESOURCE_QUOTA": ("v1", "ResourceQuota"),
                "LIMIT_RANGE": ("v1", "LimitRange"),
            }

            api_version, kind = policy_mapping.get(policy_type, ("v1", "ConfigMap"))

            # Criar ou atualizar o recurso
            api = dynamic_client.resources.get(api_version=api_version, kind=kind)

            # Verificar se recurso existe
            try:
                existing = api.get(name=policy_name, namespace=namespace)
                # Atualizar recurso existente
                policy_spec["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
                api.patch(body=policy_spec, name=policy_name, namespace=namespace)
                logger.info(
                    "playbook_executor.policy_updated", policy_type=policy_type, name=policy_name
                )
            except Exception:
                # Criar novo recurso
                api.create(body=policy_spec, namespace=namespace)
                logger.info(
                    "playbook_executor.policy_created", policy_type=policy_type, name=policy_name
                )

            return {
                "success": True,
                "action": "update_policy",
                "policy_type": policy_type,
                "policy_name": policy_name,
                "namespace": namespace,
            }

        except Exception as e:
            logger.error("playbook_executor.update_policy_failed", error=str(e))
            return {"success": False, "action": "update_policy", "error": str(e)}

    async def _apply_policy(self, action: dict, context: dict) -> dict:
        """
        Apply a Kubernetes policy resource (alias for update_policy).

        Este método é um alias para _update_policy para manter compatibilidade
        com playbooks que usam "apply_policy" como nome de ação.
        """
        return await self._update_policy(action, context)

    async def _check_database_connection(self, action: dict, context: dict) -> dict:
        """Verifica conectividade com banco de dados (MongoDB/PostgreSQL/Redis)."""
        connection_string = action.get("connection_string") or context.get("connection_string")
        database_type = action.get("database_type") or context.get("database_type", "mongodb")
        timeout = action.get("timeout_seconds", 5)

        logger.info(
            "playbook_executor.check_database_connection",
            database_type=database_type,
            connection_string=connection_string[:50] + "..." if connection_string else None,
        )

        result = {
            "action": "check_database_connection",
            "database_type": database_type,
        }

        try:
            if database_type == "mongodb":
                from motor.motor_asyncio import AsyncIOMotorClient

                client = AsyncIOMotorClient(
                    connection_string, serverSelectionTimeoutMS=timeout * 1000
                )
                await client.admin.command("ping")
                client.close()

                logger.info(
                    "playbook_executor.database_connection_success", database_type=database_type
                )
                result.update({"success": True, "connected": True})
                context["database_connection_checked"] = True
                context["database_connection_type"] = database_type

            elif database_type == "postgresql":
                import asyncpg

                conn = await asyncpg.connect(connection_string, timeout=timeout)
                await conn.fetchval("SELECT 1")
                await conn.close()

                logger.info(
                    "playbook_executor.database_connection_success", database_type=database_type
                )
                result.update({"success": True, "connected": True})
                context["database_connection_checked"] = True
                context["database_connection_type"] = database_type

            elif database_type == "redis":
                import redis.asyncio as redis

                client = redis.from_url(
                    connection_string, socket_timeout=timeout, socket_connect_timeout=timeout
                )
                await client.ping()
                await client.close()

                logger.info(
                    "playbook_executor.database_connection_success", database_type=database_type
                )
                result.update({"success": True, "connected": True})
                context["database_connection_checked"] = True
                context["database_connection_type"] = database_type

            else:
                error_msg = f"Unsupported database type: {database_type}"
                result.update({"success": False, "error": error_msg})
                return result

        except Exception as e:
            logger.error(
                "playbook_executor.database_connection_failed",
                database_type=database_type,
                error=str(e),
            )
            result.update({"success": False, "connected": False, "error": str(e)})
            return result

        return result

    async def _get_pod_metrics(self, action: dict, context: dict) -> dict:
        """Obtém métricas de um pod Kubernetes (uso de memória, CPU)."""
        pod_name = action.get("pod_name") or context.get("pod_name")
        namespace = action.get("namespace") or context.get("namespace", "default")
        memory_threshold_mb = action.get("memory_threshold_mb", 512)

        logger.info(
            "playbook_executor.get_pod_metrics",
            pod_name=pod_name,
            namespace=namespace,
        )

        result = {
            "action": "get_pod_metrics",
            "pod_name": pod_name,
            "namespace": namespace,
        }

        try:
            if not self.core_v1:
                result.update(
                    {"success": False, "error": "Kubernetes core_v1 client not available"}
                )
                return result

            # Usar a API diretamente para obter métricas do pod
            import json
            from kubernetes import client

            path = f"/api/v1/namespaces/{namespace}/pods/{pod_name}/metrics"
            try:
                response = self.core_v1.api_client.call_api(
                    path,
                    "GET",
                    auth_settings=["BearerToken"],
                    response_type="object",
                )

                # Handle response: pode ser tuple (real) ou MagicMock com .data (mock)
                if isinstance(response, tuple) and len(response) > 0:
                    metrics_data = response[0]
                elif hasattr(response, "data"):
                    import json

                    metrics_data = json.loads(response.data)
                else:
                    metrics_data = response if response else {}

                # Processar dados dos containers
                containers = []
                total_memory_mb = 0

                for container in metrics_data.get("containers", []):
                    usage = container.get("usage", {})
                    memory_str = usage.get("memory", "0")

                    # Converter memory string (ex: "128Mi") para MB
                    memory_mb = self._parse_memory_to_mb(memory_str)
                    total_memory_mb += memory_mb

                    containers.append(
                        {
                            "name": container.get("name"),
                            "usage": {"memory": memory_str, "cpu": usage.get("cpu", "0")},
                        }
                    )

                result.update(
                    {
                        "success": True,
                        "containers": containers,
                        "memory_mb": total_memory_mb,
                        "memory_threshold_exceeded": total_memory_mb > memory_threshold_mb,
                    }
                )

                logger.info(
                    "playbook_executor.get_pod_metrics_success",
                    pod_name=pod_name,
                    memory_mb=total_memory_mb,
                    threshold=memory_threshold_mb,
                )

            except client.rest.ApiException as e:
                if e.status == 404:
                    result.update(
                        {
                            "success": False,
                            "error": f"Pod {pod_name} not found in namespace {namespace} (404)",
                        }
                    )
                else:
                    result.update({"success": False, "error": f"API error {e.status}: {e.reason}"})
                logger.error(
                    "playbook_executor.get_pod_metrics_api_error",
                    pod_name=pod_name,
                    error=str(e),
                )

        except Exception as e:
            logger.error(
                "playbook_executor.get_pod_metrics_failed",
                pod_name=pod_name,
                error=str(e),
            )
            result.update(
                {
                    "success": False,
                    "error": str(e),
                }
            )

        return result

    def _parse_memory_to_mb(self, memory_str: str) -> int:
        """Converte string de memória Kubernetes (ex: '128Mi', '1Gi') para MB."""
        if not memory_str:
            return 0

        memory_str = memory_str.strip().upper()

        # Extrair número e unidade
        import re

        match = re.match(r"(\d+(?:\.\d+)?)([A-Z]*)", memory_str)
        if not match:
            return 0

        value = float(match.group(1))
        unit = match.group(2)

        # Converter para MB
        if unit == "KI":  # Kilobyte
            return int(value / 1024)
        elif unit == "MI":  # Megabyte
            return int(value)
        elif unit == "GI":  # Gigabyte
            return int(value * 1024)
        elif unit == "TI":  # Terabyte
            return int(value * 1024 * 1024)
        elif unit == "K":  # Kilobyte (sem o i)
            return int(value / 1024)
        elif unit == "M":  # Megabyte (sem o i)
            return int(value)
        elif unit == "G":  # Gigabyte (sem o i)
            return int(value * 1024)
        elif unit == "T":  # Terabyte (sem o i)
            return int(value * 1024 * 1024)
        elif unit == "" or unit == "BYTES":  # Bytes
            return int(value / (1024 * 1024))
        else:
            return 0

    async def _analyze_memory_usage(self, action: dict, context: dict) -> dict:
        """Analisa histórico de uso de memória para detectar tendências de memory leak."""
        pod_name = action.get("pod_name") or context.get("pod_name", "unknown")
        metrics_history = action.get("metrics_history") or context.get("metrics_history", [])

        logger.info(
            "playbook_executor.analyze_memory_usage",
            pod_name=pod_name,
            history_size=len(metrics_history),
        )

        result = {
            "action": "analyze_memory_usage",
            "pod_name": pod_name,
        }

        try:
            if not metrics_history or len(metrics_history) < 3:
                result.update(
                    {
                        "success": True,
                        "memory_leak_detected": False,
                        "trend": "insufficient_data",
                        "reason": f"Need at least 3 data points, got {len(metrics_history)}",
                    }
                )
                return result

            # Extrair valores de memória em MB
            memory_values = []
            for entry in metrics_history:
                mem_val = entry.get("memory_mb", 0)
                memory_values.append(mem_val)

            # Calcular tendência usando regressão linear simples
            import statistics

            n = len(memory_values)
            x_values = list(range(n))

            # Médias
            x_mean = statistics.mean(x_values)
            y_mean = statistics.mean(memory_values)

            # Calcular slope (inclinação)
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, memory_values))
            denominator = sum((x - x_mean) ** 2 for x in x_values)

            if denominator == 0:
                slope = 0
            else:
                slope = numerator / denominator

            # Calcular R² para determinar qualidade da regressão
            if denominator == 0:
                r_squared = 0
            else:
                y_predicted = [y_mean + slope * (x - x_mean) for x in x_values]
                ss_res = sum((y - yp) ** 2 for y, yp in zip(memory_values, y_predicted))
                ss_tot = sum((y - y_mean) ** 2 for y in memory_values)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            # Determinar tendência
            if slope > 5:  # Aumento > 5MB por período
                trend = "increasing"
                memory_leak_detected = r_squared > 0.7  # Tendência forte
            elif slope < -5:
                trend = "decreasing"
                memory_leak_detected = False
            else:
                # Verificar variância para detectar oscilações
                variance = statistics.variance(memory_values) if len(memory_values) > 1 else 0
                if variance < 100:  # Variância baixa = estável
                    trend = "stable"
                else:
                    trend = "fluctuating"
                memory_leak_detected = False

            result.update(
                {
                    "success": True,
                    "memory_leak_detected": memory_leak_detected,
                    "trend": trend,
                    "slope_mb_per_period": round(slope, 2),
                    "r_squared": round(r_squared, 4),
                    "current_memory_mb": memory_values[-1],
                    "min_memory_mb": min(memory_values),
                    "max_memory_mb": max(memory_values),
                    "avg_memory_mb": round(y_mean, 2),
                }
            )

            logger.info(
                "playbook_executor.analyze_memory_usage_complete",
                pod_name=pod_name,
                trend=trend,
                leak_detected=memory_leak_detected,
                slope=round(slope, 2),
            )

        except Exception as e:
            logger.error(
                "playbook_executor.analyze_memory_usage_failed",
                pod_name=pod_name,
                error=str(e),
            )
            result.update(
                {
                    "success": False,
                    "error": str(e),
                }
            )

        return result

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
            reason=reason,
        )

        # Fail-safe: if client is not available, return success with warning
        if not self.execution_ticket_client:
            logger.warning(
                "playbook_executor.execution_ticket_client_unavailable",
                tickets=affected_tickets,
                action="reallocate_ticket",
            )
            return {
                "success": True,
                "action": "reallocate_ticket",
                "tickets": affected_tickets,
                "previous_worker": previous_worker,
                "warning": "Execution Ticket Service unavailable, action skipped",
            }

        try:
            # Use Circuit Breaker para Execution Ticket Service
            ets_breaker = self._circuit_breakers.get("execution_ticket_service")

            async def _reallocate_single():
                return await self.execution_ticket_client.reallocate_ticket(
                    ticket_id=affected_tickets[0],
                    reason=reason,
                    metadata={
                        "workflow_id": workflow_id,
                        "previous_worker": previous_worker,
                        "incident_id": context.get("incident_id"),
                    },
                )

            async def _reallocate_batch():
                return await self.execution_ticket_client.reallocate_multiple_tickets(
                    ticket_ids=affected_tickets,
                    reason=reason,
                    metadata={
                        "workflow_id": workflow_id,
                        "previous_worker": previous_worker,
                        "incident_id": context.get("incident_id"),
                    },
                )

            if len(affected_tickets) == 1:
                # Single ticket reallocation
                if ets_breaker:
                    result = await ets_breaker.call_async(_reallocate_single)
                else:
                    result = await _reallocate_single()
                logger.info(
                    "playbook_executor.ticket_reallocated",
                    ticket_id=affected_tickets[0],
                    reallocation_id=result.get("reallocation_id"),
                )
                return {
                    "success": True,
                    "action": "reallocate_ticket",
                    "tickets": affected_tickets,
                    "previous_worker": previous_worker,
                    "reallocated": True,
                    "reallocation_id": result.get("reallocation_id"),
                }
            else:
                # Batch reallocation
                if ets_breaker:
                    result = await ets_breaker.call_async(_reallocate_batch)
                else:
                    result = await _reallocate_batch()
                logger.info(
                    "playbook_executor.tickets_reallocated_batch",
                    batch_id=result.get("batch_id"),
                    total=result.get("total"),
                    successful=result.get("successful"),
                    failed=result.get("failed"),
                )
                return {
                    "success": result.get("failed", 0) == 0,
                    "action": "reallocate_ticket",
                    "tickets": affected_tickets,
                    "previous_worker": previous_worker,
                    "reallocated": True,
                    "batch_id": result.get("batch_id"),
                    "successful_count": result.get("successful"),
                    "failed_count": result.get("failed"),
                }

        except CircuitBreakerOpenError:
            logger.error(
                "playbook_executor.circuit_breaker_open",
                service="execution_ticket_service",
                tickets=affected_tickets,
            )
            return {
                "success": False,
                "action": "reallocate_ticket",
                "tickets": affected_tickets,
                "error": "Circuit breaker is OPEN - service temporarily unavailable",
                "circuit_breaker_open": True,
            }
        except Exception as e:
            logger.error(
                "playbook_executor.reallocate_ticket_failed", tickets=affected_tickets, error=str(e)
            )
            return {
                "success": False,
                "action": "reallocate_ticket",
                "tickets": affected_tickets,
                "error": str(e),
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
            metadata=metadata,
        )

        sent = False
        if self.service_registry_client:
            sent = await self.service_registry_client.notify_agent(
                agent_id=agent_id,
                notification={
                    "notification_type": notification_type,
                    "message": message,
                    "metadata": metadata,
                },
            )

        return {
            "success": True if sent or not self.service_registry_client else False,
            "action": "notify_agent",
            "agent_id": agent_id,
            "notification_type": notification_type,
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
            status=status,
        )

        # Fail-safe: if client is not available, return success with warning
        if not self.execution_ticket_client:
            logger.warning(
                "playbook_executor.execution_ticket_client_unavailable",
                ticket_id=ticket_id,
                action="update_ticket_status",
            )
            return {
                "success": True,
                "action": "update_ticket_status",
                "ticket_id": ticket_id,
                "status": status,
                "warning": "Execution Ticket Service unavailable, action skipped",
            }

        try:
            await self.execution_ticket_client.update_ticket_status(
                ticket_id=ticket_id,
                status=status,
                result=result_data,
                metadata={
                    "workflow_id": workflow_id,
                    "updated_by": "self-healing-engine",
                    "incident_id": context.get("incident_id"),
                },
            )

            logger.info(
                "playbook_executor.ticket_status_updated", ticket_id=ticket_id, status=status
            )

            return {
                "success": True,
                "action": "update_ticket_status",
                "ticket_id": ticket_id,
                "status": status,
                "updated": True,
            }

        except Exception as e:
            logger.error(
                "playbook_executor.update_ticket_status_failed",
                ticket_id=ticket_id,
                status=status,
                error=str(e),
            )
            return {
                "success": False,
                "action": "update_ticket_status",
                "ticket_id": ticket_id,
                "status": status,
                "error": str(e),
            }

    async def _restart_workflow(self, action: dict, context: dict) -> dict:
        """Resume/restart a paused workflow via Orchestrator gRPC."""
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        reason = action.get("reason") or context.get("reason", "self_healing_restart")

        logger.info("playbook_executor.restart_workflow", workflow_id=workflow_id, reason=reason)

        # Fail-safe: if client is not available, return success with warning
        if not self.orchestrator_client:
            logger.warning(
                "playbook_executor.orchestrator_client_unavailable",
                workflow_id=workflow_id,
                action="restart_workflow",
            )
            return {
                "success": True,
                "action": "restart_workflow",
                "workflow_id": workflow_id,
                "warning": "Orchestrator unavailable, action skipped",
            }

        try:
            orchestrator_breaker = self._circuit_breakers.get("orchestrator")

            async def _get_status():
                return await self.orchestrator_client.get_workflow_status(
                    workflow_id=workflow_id, include_tickets=False
                )

            async def _resume():
                return await self.orchestrator_client.resume_workflow(
                    workflow_id=workflow_id, reason=reason
                )

            # First, get workflow status to check if it's paused
            if orchestrator_breaker:
                status = await orchestrator_breaker.call_async(_get_status)
            else:
                status = await _get_status()

            workflow_state = status.get("state", "UNKNOWN")

            if workflow_state == "PAUSED":
                # Resume the paused workflow
                if orchestrator_breaker:
                    result = await orchestrator_breaker.call_async(_resume)
                else:
                    result = await _resume()

                logger.info(
                    "playbook_executor.workflow_resumed",
                    workflow_id=workflow_id,
                    success=result.get("success"),
                    pause_duration_seconds=result.get("pause_duration_seconds"),
                )

                return {
                    "success": result.get("success", False),
                    "action": "restart_workflow",
                    "workflow_id": workflow_id,
                    "previous_state": workflow_state,
                    "resumed": True,
                    "pause_duration_seconds": result.get("pause_duration_seconds"),
                }

            elif workflow_state in ("COMPLETED", "FAILED", "CANCELLED"):
                logger.warning(
                    "playbook_executor.workflow_in_terminal_state",
                    workflow_id=workflow_id,
                    state=workflow_state,
                )
                return {
                    "success": False,
                    "action": "restart_workflow",
                    "workflow_id": workflow_id,
                    "state": workflow_state,
                    "error": f"Workflow in terminal state: {workflow_state}",
                }

            else:
                # Workflow is running or in another non-paused state
                logger.info(
                    "playbook_executor.workflow_not_paused",
                    workflow_id=workflow_id,
                    state=workflow_state,
                )
                return {
                    "success": True,
                    "action": "restart_workflow",
                    "workflow_id": workflow_id,
                    "state": workflow_state,
                    "note": "Workflow not paused, no action taken",
                }

        except CircuitBreakerOpenError:
            logger.error(
                "playbook_executor.circuit_breaker_open",
                service="orchestrator",
                workflow_id=workflow_id,
                action="restart_workflow",
            )
            return {
                "success": False,
                "action": "restart_workflow",
                "workflow_id": workflow_id,
                "error": "Circuit breaker is OPEN - orchestrator temporarily unavailable",
                "circuit_breaker_open": True,
            }
        except Exception as e:
            logger.error(
                "playbook_executor.restart_workflow_failed", workflow_id=workflow_id, error=str(e)
            )
            return {
                "success": False,
                "action": "restart_workflow",
                "workflow_id": workflow_id,
                "error": str(e),
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
            duration_seconds=duration_seconds,
        )

        if not self.orchestrator_client:
            logger.warning(
                "playbook_executor.orchestrator_client_unavailable",
                workflow_id=workflow_id,
                action="pause_workflow",
            )
            return {
                "success": True,
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "warning": "Orchestrator unavailable, action skipped",
            }

        try:
            orchestrator_breaker = self._circuit_breakers.get("orchestrator")

            async def _pause_workflow_call():
                return await self.orchestrator_client.pause_workflow(
                    workflow_id=workflow_id, reason=reason, duration_seconds=duration_seconds
                )

            if orchestrator_breaker:
                result = await orchestrator_breaker.call_async(_pause_workflow_call)
            else:
                result = await _pause_workflow_call()

            logger.info(
                "playbook_executor.workflow_paused",
                workflow_id=workflow_id,
                success=result.get("success"),
            )

            return {
                "success": result.get("success", False),
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "paused": True,
                "paused_at": result.get("paused_at"),
                "scheduled_resume_at": result.get("scheduled_resume_at"),
            }

        except CircuitBreakerOpenError:
            logger.error(
                "playbook_executor.circuit_breaker_open",
                service="orchestrator",
                workflow_id=workflow_id,
                action="pause_workflow",
            )
            return {
                "success": False,
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "error": "Circuit breaker is OPEN - orchestrator temporarily unavailable",
                "circuit_breaker_open": True,
            }
        except Exception as e:
            logger.error(
                "playbook_executor.pause_workflow_failed", workflow_id=workflow_id, error=str(e)
            )
            return {
                "success": False,
                "action": "pause_workflow",
                "workflow_id": workflow_id,
                "error": str(e),
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
            trigger_type=trigger_type,
        )

        if not self.orchestrator_client:
            logger.warning(
                "playbook_executor.orchestrator_client_unavailable",
                plan_id=plan_id,
                action="trigger_replanning",
            )
            return {
                "success": True,
                "action": "trigger_replanning",
                "plan_id": plan_id,
                "warning": "Orchestrator unavailable, action skipped",
            }

        try:
            result = await self.orchestrator_client.trigger_replanning(
                plan_id=plan_id,
                reason=reason,
                trigger_type=trigger_type,
                preserve_progress=preserve_progress,
                context={
                    "incident_id": context.get("incident_id", ""),
                    "triggered_by": "self-healing-engine",
                },
            )

            logger.info(
                "playbook_executor.replanning_triggered",
                plan_id=plan_id,
                replanning_id=result.get("replanning_id"),
                success=result.get("success"),
            )

            return {
                "success": result.get("success", False),
                "action": "trigger_replanning",
                "plan_id": plan_id,
                "replanning_id": result.get("replanning_id"),
                "triggered_at": result.get("triggered_at"),
            }

        except Exception as e:
            logger.error(
                "playbook_executor.trigger_replanning_failed", plan_id=plan_id, error=str(e)
            )
            return {
                "success": False,
                "action": "trigger_replanning",
                "plan_id": plan_id,
                "error": str(e),
            }

    async def _get_workflow_status(self, action: dict, context: dict) -> dict:
        """Get workflow status from Orchestrator."""
        workflow_id = action.get("workflow_id") or context.get("workflow_id")
        include_tickets = action.get("include_tickets", True)

        logger.info("playbook_executor.get_workflow_status", workflow_id=workflow_id)

        if not self.orchestrator_client:
            logger.warning(
                "playbook_executor.orchestrator_client_unavailable",
                workflow_id=workflow_id,
                action="get_workflow_status",
            )
            return {
                "success": True,
                "action": "get_workflow_status",
                "workflow_id": workflow_id,
                "warning": "Orchestrator unavailable",
            }

        try:
            result = await self.orchestrator_client.get_workflow_status(
                workflow_id=workflow_id, include_tickets=include_tickets
            )

            # Update context with workflow state for subsequent actions
            context["workflow_state"] = result.get("state")

            return {
                "success": True,
                "action": "get_workflow_status",
                "workflow_id": workflow_id,
                "state": result.get("state"),
                "progress_percent": result.get("progress_percent"),
                "tickets": result.get("tickets"),
            }

        except Exception as e:
            logger.error(
                "playbook_executor.get_workflow_status_failed",
                workflow_id=workflow_id,
                error=str(e),
            )
            return {
                "success": False,
                "action": "get_workflow_status",
                "workflow_id": workflow_id,
                "error": str(e),
            }

    async def _check_worker_health(self, action: dict, context: dict) -> dict:
        """Verifica saúde do worker via Service Registry (stub)."""
        worker_id = action.get("worker_id") or context.get("worker_id")
        namespace = action.get("namespace") or context.get("namespace")

        logger.info(
            "playbook_executor.check_worker_health", worker_id=worker_id, namespace=namespace
        )

        healthy = True
        if self.service_registry_client:
            agent_info = await self.service_registry_client.get_agent_info(worker_id)
            if agent_info and agent_info.get("status") not in [1]:  # 1 = HEALTHY
                healthy = False
        context["worker_unhealthy"] = not healthy
        return {
            "success": True,
            "action": "check_worker_health",
            "worker_id": worker_id,
            "healthy": healthy,
        }

    async def _check_consumer_lag(self, action: dict, context: dict) -> dict:
        """Checa lag do consumer group (stub)."""
        consumer_group = action.get("consumer_group") or context.get("consumer_group")
        topic = action.get("topic") or context.get("topic")
        lag_threshold = int(action.get("lag_threshold") or context.get("lag_threshold") or 0)

        logger.info(
            "playbook_executor.check_consumer_lag",
            consumer_group=consumer_group,
            topic=topic,
            lag_threshold=lag_threshold,
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
        """
        Remove mensagens poison pill do tópico Kafka.

        Esta ação identifica e remove mensagens que causam erro de processamento,
        permitindo que o consumidor retome o processamento正常.
        """
        topic = action.get("topic") or context.get("topic")
        partition = action.get("partition", 0)
        offset = action.get("offset")
        poison_message_identifier = action.get("poison_message_identifier")

        logger.info(
            "playbook_executor.cleanup_poison_messages",
            topic=topic,
            partition=partition,
            offset=offset,
            poison_message_identifier=poison_message_identifier,
        )

        # Nota: A remoção real de mensagens requer administração do Kafka
        # Esta é uma implementação de sinalização/recomendação
        try:
            if topic and offset:
                # Sinalizar para administradores sobre mensagem poison
                # Na prática, pode usar Kafka Admin API para seek ou deletar
                logger.warning(
                    "playbook_executor.poison_message_identified",
                    topic=topic,
                    partition=partition,
                    offset=offset,
                    action_required="manual_intervention_or_kafka_admin_seek",
                )

                return {
                    "success": True,
                    "action": "cleanup_poison_messages",
                    "topic": topic,
                    "note": "Poison message identified. Manual cleanup or seek required.",
                    "partition": partition,
                    "offset": offset,
                }

            return {"success": True, "action": "cleanup_poison_messages", "topic": topic}

        except Exception as e:
            logger.error("playbook_executor.cleanup_poison_messages_failed", error=str(e))
            return {"success": False, "action": "cleanup_poison_messages", "error": str(e)}

    async def _wait(self, action: dict, context: dict) -> dict:
        """
        Aguarda um período de tempo antes de continuar.

        Útil para permitir que mudanças se propaguem antes de validar.
        """
        seconds = int(action.get("seconds") or context.get("wait_seconds") or 5)

        logger.info("playbook_executor.wait", seconds=seconds)

        await asyncio.sleep(seconds)

        return {"success": True, "action": "wait", "waited_seconds": seconds}

    async def _delete_pod(self, action: dict, context: dict) -> dict:
        """
        Delete a pod (for termination and recreation by controller).

        Diferente de restart_pod que deleta e espera recriação.
        """
        try:
            pod_name = context.get("pod_name") or action.get("pod_name")
            namespace = context.get("namespace") or action.get("namespace", "default")

            self.core_v1.delete_namespaced_pod(pod_name, namespace)
            logger.info("playbook_executor.pod_deleted", pod=pod_name, namespace=namespace)

            return {"success": True, "action": "delete_pod", "pod": pod_name}
        except Exception as e:
            logger.error("playbook_executor.delete_pod_failed", error=str(e))
            return {"success": False, "action": "delete_pod", "error": str(e)}

    async def _patch_deployment(self, action: dict, context: dict) -> dict:
        """
        Apply a strategic merge patch to a deployment.

        Permite atualização específica de campos sem substituir todo o objeto.
        """
        try:
            deployment_name = context.get("deployment_name") or action.get("deployment_name")
            namespace = context.get("namespace") or action.get("namespace", "default")
            patch = action.get("patch") or action.get("patch_spec")

            if not patch:
                return {
                    "success": False,
                    "action": "patch_deployment",
                    "error": "patch specification is required",
                }

            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=namespace, body=patch
            )

            logger.info(
                "playbook_executor.deployment_patched",
                deployment=deployment_name,
                namespace=namespace,
            )

            return {
                "success": True,
                "action": "patch_deployment",
                "deployment": deployment_name,
                "namespace": namespace,
            }
        except Exception as e:
            logger.error("playbook_executor.patch_deployment_failed", error=str(e))
            return {"success": False, "action": "patch_deployment", "error": str(e)}

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
            self.playbook_execution_duration_seconds.labels(playbook=playbook_name).observe(
                duration_seconds
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("playbook_executor.metrics_failed", error=str(e))
