"""
Interface base para Fault Injectors.

Define a interface comum para todos os injetores de falha do módulo de Chaos Engineering.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from prometheus_client import Counter, Histogram

from ..chaos_models import FaultInjection, FaultType, TargetSelector

logger = structlog.get_logger(__name__)

# Métricas Prometheus para injetores de falha
INJECTION_TOTAL = Counter(
    'chaos_injection_total',
    'Total de injeções de falha executadas',
    ['injection_type', 'status', 'namespace']
)

INJECTION_DURATION_SECONDS = Histogram(
    'chaos_injection_duration_seconds',
    'Duração da injeção de falha',
    ['injection_type'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

ROLLBACK_TOTAL = Counter(
    'chaos_rollback_total',
    'Total de rollbacks executados',
    ['injection_type', 'status']
)


@dataclass
class InjectionResult:
    """Resultado de uma operação de injeção de falha."""
    success: bool
    injection_id: str
    fault_type: FaultType
    affected_resources: List[str] = field(default_factory=list)
    blast_radius: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    rollback_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte o resultado para dicionário."""
        return {
            "success": self.success,
            "injection_id": self.injection_id,
            "fault_type": self.fault_type.value if isinstance(self.fault_type, FaultType) else self.fault_type,
            "affected_resources": self.affected_resources,
            "blast_radius": self.blast_radius,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "rollback_data": self.rollback_data,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class BaseFaultInjector(ABC):
    """
    Interface base para todos os injetores de falha.

    Cada implementação deve fornecer métodos para:
    - inject: Injetar a falha no sistema
    - validate: Validar se a injeção foi bem-sucedida
    - rollback: Remover a falha e restaurar o estado original
    - get_blast_radius: Calcular o raio de impacto da falha
    """

    def __init__(
        self,
        k8s_core_v1=None,
        k8s_apps_v1=None,
        k8s_networking_v1=None,
        opa_client=None,
    ):
        """
        Inicializa o injetor de falhas.

        Args:
            k8s_core_v1: Cliente Kubernetes CoreV1Api
            k8s_apps_v1: Cliente Kubernetes AppsV1Api
            k8s_networking_v1: Cliente Kubernetes NetworkingV1Api
            opa_client: Cliente OPA para validação de políticas
        """
        self.k8s_core_v1 = k8s_core_v1
        self.k8s_apps_v1 = k8s_apps_v1
        self.k8s_networking_v1 = k8s_networking_v1
        self.opa_client = opa_client
        self._active_injections: Dict[str, FaultInjection] = {}

    @property
    @abstractmethod
    def supported_fault_types(self) -> List[FaultType]:
        """Retorna os tipos de falha suportados por este injetor."""
        pass

    @abstractmethod
    async def inject(self, injection: FaultInjection) -> InjectionResult:
        """
        Injeta a falha especificada no sistema.

        Args:
            injection: Configuração da injeção de falha

        Returns:
            InjectionResult com detalhes da injeção
        """
        pass

    @abstractmethod
    async def validate(self, injection_id: str) -> bool:
        """
        Valida se a injeção de falha está ativa.

        Args:
            injection_id: ID da injeção a validar

        Returns:
            True se a injeção está ativa, False caso contrário
        """
        pass

    @abstractmethod
    async def rollback(self, injection_id: str) -> InjectionResult:
        """
        Remove a falha injetada e restaura o estado original.

        Args:
            injection_id: ID da injeção a reverter

        Returns:
            InjectionResult com detalhes do rollback
        """
        pass

    @abstractmethod
    async def get_blast_radius(self, target: TargetSelector) -> int:
        """
        Calcula o número de recursos que serão afetados pela injeção.

        Args:
            target: Seletor de alvos para a falha

        Returns:
            Número estimado de recursos afetados
        """
        pass

    async def validate_with_opa(
        self,
        injection: FaultInjection,
        environment: str,
        requester_role: str,
        requester_name: str = "unknown",
        requester_groups: Optional[List[str]] = None,
        approved_by: Optional[str] = None,
        blast_radius_limit: int = 5,
    ) -> tuple[bool, List[str]]:
        """
        Valida a injeção com políticas OPA antes de executar.

        O input deve ter o formato esperado pelo Rego:
        - input.experiment: dados do experimento
        - input.executor: dados do executor
        - input.approval: dados de aprovação

        Args:
            injection: Configuração da injeção
            environment: Ambiente de execução (staging, production, etc)
            requester_role: Role do usuário que está requisitando
            requester_name: Nome do executor
            requester_groups: Grupos do executor
            approved_by: Quem aprovou (se aplicável)
            blast_radius_limit: Limite de blast radius

        Returns:
            Tupla (allowed, violations) - allowed é True se permitido,
            violations contém lista de violações encontradas
        """
        if not self.opa_client:
            logger.warning(
                "injector.opa_client_unavailable",
                injection_id=injection.id,
                note="Permitindo injeção sem validação OPA"
            )
            return True, []

        try:
            # Construir input no formato esperado pelo Rego policy
            opa_input = {
                "input": {
                    "experiment": {
                        "id": injection.id,
                        "environment": environment,
                        "blast_radius_limit": blast_radius_limit,
                        "fault_injections": [{
                            "id": injection.id,
                            "fault_type": injection.fault_type.value,
                            "target": {
                                "namespace": injection.target.namespace,
                                "service_name": injection.target.service_name,
                                "labels": injection.target.labels,
                                "deployment_name": injection.target.deployment_name,
                                "percentage": injection.target.percentage,
                            },
                            "parameters": injection.parameters.model_dump() if hasattr(injection.parameters, 'model_dump') else {},
                            "duration_seconds": injection.duration_seconds,
                        }],
                        "rollback_strategy": injection.rollback_data.get("strategy", "automatic"),
                    },
                    "executor": {
                        "name": requester_name,
                        "role": requester_role,
                        "groups": requester_groups or [],
                    },
                    "approval": {
                        "opa_approved": approved_by is not None,
                        "approved_by": approved_by or "",
                        "business_hours_override": False,
                    },
                }
            }

            policy_path = "neuralhive/chaos/experiment_validation"
            result = await self.opa_client.evaluate_policy(policy_path, opa_input)

            violations = result.get("result", {}).get("violations", [])
            allowed = len(violations) == 0

            if not allowed:
                logger.warning(
                    "injector.opa_validation_denied",
                    injection_id=injection.id,
                    violations=violations
                )

            return allowed, violations

        except Exception as e:
            logger.error(
                "injector.opa_validation_error",
                injection_id=injection.id,
                error=str(e)
            )
            # Fail-open: permitir em caso de erro de comunicação com OPA
            return True, []

    async def get_target_pods(self, target: TargetSelector) -> List[str]:
        """
        Obtém lista de pods que correspondem ao seletor de alvos.

        Args:
            target: Seletor de alvos

        Returns:
            Lista de nomes de pods
        """
        if not self.k8s_core_v1:
            logger.warning("injector.k8s_client_unavailable")
            return []

        try:
            pods = []

            if target.pod_names:
                # Usar nomes específicos de pods
                for pod_name in target.pod_names:
                    try:
                        pod = self.k8s_core_v1.read_namespaced_pod(pod_name, target.namespace)
                        if pod.status.phase == "Running":
                            pods.append(pod_name)
                    except Exception:
                        continue
            elif target.labels:
                # Buscar por labels
                label_selector = ",".join([f"{k}={v}" for k, v in target.labels.items()])
                pod_list = self.k8s_core_v1.list_namespaced_pod(
                    target.namespace,
                    label_selector=label_selector
                )
                pods = [
                    pod.metadata.name
                    for pod in pod_list.items
                    if pod.status.phase == "Running"
                ]
            elif target.deployment_name:
                # Buscar pods do deployment
                try:
                    deployment = self.k8s_apps_v1.read_namespaced_deployment(
                        target.deployment_name,
                        target.namespace
                    )
                    selector = deployment.spec.selector.match_labels
                    label_selector = ",".join([f"{k}={v}" for k, v in selector.items()])
                    pod_list = self.k8s_core_v1.list_namespaced_pod(
                        target.namespace,
                        label_selector=label_selector
                    )
                    pods = [
                        pod.metadata.name
                        for pod in pod_list.items
                        if pod.status.phase == "Running"
                    ]
                except Exception as e:
                    logger.error(
                        "injector.deployment_not_found",
                        deployment=target.deployment_name,
                        error=str(e)
                    )

            # Aplicar percentual se especificado
            if target.percentage < 100 and pods:
                import random
                count = max(1, int(len(pods) * target.percentage / 100))
                pods = random.sample(pods, count)

            return pods

        except Exception as e:
            logger.error(
                "injector.get_target_pods_failed",
                namespace=target.namespace,
                error=str(e)
            )
            return []

    def _record_injection_metrics(
        self,
        injection_type: str,
        status: str,
        namespace: str,
        duration_seconds: Optional[float] = None
    ):
        """Registra métricas de injeção."""
        try:
            INJECTION_TOTAL.labels(
                injection_type=injection_type,
                status=status,
                namespace=namespace
            ).inc()

            if duration_seconds is not None:
                INJECTION_DURATION_SECONDS.labels(
                    injection_type=injection_type
                ).observe(duration_seconds)
        except Exception as e:
            logger.warning("injector.metrics_recording_failed", error=str(e))

    def _record_rollback_metrics(self, injection_type: str, status: str):
        """Registra métricas de rollback."""
        try:
            ROLLBACK_TOTAL.labels(
                injection_type=injection_type,
                status=status
            ).inc()
        except Exception as e:
            logger.warning("injector.metrics_recording_failed", error=str(e))

    def _track_active_injection(self, injection: FaultInjection):
        """Registra uma injeção como ativa."""
        self._active_injections[injection.id] = injection

    def _untrack_active_injection(self, injection_id: str):
        """Remove uma injeção do rastreamento de ativas."""
        self._active_injections.pop(injection_id, None)

    def get_active_injections(self) -> List[FaultInjection]:
        """Retorna lista de injeções ativas."""
        return list(self._active_injections.values())

    async def cleanup_all(self) -> List[InjectionResult]:
        """
        Executa rollback de todas as injeções ativas.

        Returns:
            Lista de resultados de rollback
        """
        results = []
        for injection_id in list(self._active_injections.keys()):
            try:
                result = await self.rollback(injection_id)
                results.append(result)
            except Exception as e:
                logger.error(
                    "injector.cleanup_failed",
                    injection_id=injection_id,
                    error=str(e)
                )
                results.append(InjectionResult(
                    success=False,
                    injection_id=injection_id,
                    fault_type=self._active_injections.get(injection_id, FaultInjection(
                        fault_type=FaultType.POD_KILL
                    )).fault_type,
                    error_message=str(e)
                ))
        return results
