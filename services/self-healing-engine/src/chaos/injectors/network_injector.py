"""
Network Fault Injector para Chaos Engineering.

Implementa injeção de falhas de rede como latência, perda de pacotes,
particionamento e limitação de bandwidth.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from kubernetes import client

from .base_injector import BaseFaultInjector, InjectionResult
from ..chaos_models import FaultInjection, FaultType, TargetSelector
from ..chaos_config import CHAOS_LABELS, CHAOS_ANNOTATIONS

logger = structlog.get_logger(__name__)


class NetworkFaultInjector(BaseFaultInjector):
    """
    Injetor de falhas de rede.

    Suporta:
    - Injeção de latência via tc (traffic control)
    - Perda de pacotes via tc
    - Particionamento de rede via NetworkPolicy
    - Limitação de bandwidth via tc
    """

    @property
    def supported_fault_types(self) -> List[FaultType]:
        return [
            FaultType.NETWORK_LATENCY,
            FaultType.NETWORK_PACKET_LOSS,
            FaultType.NETWORK_PARTITION,
            FaultType.NETWORK_BANDWIDTH_LIMIT,
        ]

    async def inject(self, injection: FaultInjection) -> InjectionResult:
        """Injeta falha de rede no sistema."""
        start_time = datetime.utcnow()

        if injection.fault_type not in self.supported_fault_types:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=f"Tipo de falha não suportado: {injection.fault_type}",
                start_time=start_time
            )

        try:
            if injection.fault_type == FaultType.NETWORK_PARTITION:
                result = await self._inject_network_partition(injection)
            else:
                result = await self._inject_tc_fault(injection)

            if result.success:
                injection.start_time = start_time
                injection.status = "active"
                injection.rollback_data = result.rollback_data
                self._track_active_injection(injection)

            self._record_injection_metrics(
                injection.fault_type.value,
                "success" if result.success else "failed",
                injection.target.namespace
            )

            return result

        except Exception as e:
            logger.error(
                "network_injector.inject_failed",
                injection_id=injection.id,
                fault_type=injection.fault_type.value,
                error=str(e)
            )
            self._record_injection_metrics(
                injection.fault_type.value,
                "error",
                injection.target.namespace
            )
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=str(e),
                start_time=start_time
            )

    async def _inject_tc_fault(self, injection: FaultInjection) -> InjectionResult:
        """
        Injeta falha de rede usando traffic control (tc).

        Executa comandos tc via kubectl exec em cada pod alvo.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado para injeção"
            )

        tc_command = self._build_tc_command(injection)
        if not tc_command:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Não foi possível construir comando tc"
            )

        affected_pods = []
        rollback_commands = {}

        for pod_name in pods:
            try:
                # Verificar se tc está disponível no pod
                container_name = injection.parameters.container_name or None

                # Aplicar regra tc
                exec_result = await self._exec_in_pod(
                    pod_name,
                    injection.target.namespace,
                    tc_command,
                    container_name
                )

                if exec_result.get("success"):
                    affected_pods.append(pod_name)
                    rollback_commands[pod_name] = self._build_tc_rollback_command()
                    logger.info(
                        "network_injector.tc_applied",
                        pod=pod_name,
                        fault_type=injection.fault_type.value
                    )
                else:
                    logger.warning(
                        "network_injector.tc_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "network_injector.pod_injection_failed",
                    pod=pod_name,
                    error=str(e)
                )

        if not affected_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao aplicar tc em todos os pods"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=affected_pods,
            blast_radius=len(affected_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "tc",
                "pods": rollback_commands,
                "namespace": injection.target.namespace,
                "container": injection.parameters.container_name,
            }
        )

    async def _inject_network_partition(self, injection: FaultInjection) -> InjectionResult:
        """
        Injeta particionamento de rede via NetworkPolicy.

        Cria uma NetworkPolicy que bloqueia tráfego de/para os pods alvo.
        """
        if not self.k8s_networking_v1:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Cliente NetworkingV1Api não disponível"
            )

        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado para particionamento"
            )

        try:
            policy_name = f"chaos-partition-{injection.id[:8]}"

            # Construir NetworkPolicy que bloqueia todo tráfego
            network_policy = client.V1NetworkPolicy(
                api_version="networking.k8s.io/v1",
                kind="NetworkPolicy",
                metadata=client.V1ObjectMeta(
                    name=policy_name,
                    namespace=injection.target.namespace,
                    labels={
                        **CHAOS_LABELS,
                        "chaos.neuralhive.io/injection-id": injection.id,
                    },
                    annotations={
                        **CHAOS_ANNOTATIONS,
                        "chaos.neuralhive.io/experiment-id": injection.id,
                        "chaos.neuralhive.io/created-at": datetime.utcnow().isoformat(),
                    }
                ),
                spec=client.V1NetworkPolicySpec(
                    pod_selector=client.V1LabelSelector(
                        match_labels=injection.target.labels or {}
                    ),
                    policy_types=["Ingress", "Egress"],
                    ingress=[],  # Bloqueia todo ingress
                    egress=[],   # Bloqueia todo egress
                )
            )

            # Se há labels específicos, usar; caso contrário, selecionar por pod names
            if not injection.target.labels and injection.target.pod_names:
                # Para pod names específicos, precisamos usar um label comum
                # Esta abordagem requer que os pods tenham um label identificável
                logger.warning(
                    "network_injector.partition_requires_labels",
                    note="Particionamento por pod_names requer labels comuns"
                )

            self.k8s_networking_v1.create_namespaced_network_policy(
                injection.target.namespace,
                network_policy
            )

            logger.info(
                "network_injector.partition_created",
                policy_name=policy_name,
                namespace=injection.target.namespace,
                affected_pods=len(pods)
            )

            return InjectionResult(
                success=True,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                affected_resources=pods,
                blast_radius=len(pods),
                start_time=datetime.utcnow(),
                rollback_data={
                    "type": "network_policy",
                    "policy_name": policy_name,
                    "namespace": injection.target.namespace,
                }
            )

        except Exception as e:
            logger.error(
                "network_injector.partition_failed",
                error=str(e)
            )
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message=str(e)
            )

    async def validate(self, injection_id: str) -> bool:
        """Valida se a injeção de rede está ativa."""
        if injection_id not in self._active_injections:
            return False

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data

        if rollback_data.get("type") == "network_policy":
            # Verificar se NetworkPolicy existe
            try:
                self.k8s_networking_v1.read_namespaced_network_policy(
                    rollback_data["policy_name"],
                    rollback_data["namespace"]
                )
                return True
            except Exception:
                return False

        elif rollback_data.get("type") == "tc":
            # Para tc, assumimos que está ativo se está na lista
            # Uma validação mais robusta requer exec no pod
            return True

        return False

    async def rollback(self, injection_id: str) -> InjectionResult:
        """Remove a injeção de rede e restaura o estado original."""
        if injection_id not in self._active_injections:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.NETWORK_LATENCY,
                error_message="Injeção não encontrada"
            )

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data

        try:
            if rollback_data.get("type") == "network_policy":
                result = await self._rollback_network_policy(injection_id, rollback_data)
            elif rollback_data.get("type") == "tc":
                result = await self._rollback_tc(injection_id, rollback_data)
            else:
                result = InjectionResult(
                    success=False,
                    injection_id=injection_id,
                    fault_type=injection.fault_type,
                    error_message=f"Tipo de rollback desconhecido: {rollback_data.get('type')}"
                )

            if result.success:
                self._untrack_active_injection(injection_id)
                self._record_rollback_metrics(injection.fault_type.value, "success")
            else:
                self._record_rollback_metrics(injection.fault_type.value, "failed")

            return result

        except Exception as e:
            logger.error(
                "network_injector.rollback_failed",
                injection_id=injection_id,
                error=str(e)
            )
            self._record_rollback_metrics(injection.fault_type.value, "error")
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=injection.fault_type,
                error_message=str(e)
            )

    async def _rollback_network_policy(
        self,
        injection_id: str,
        rollback_data: Dict[str, Any]
    ) -> InjectionResult:
        """Remove NetworkPolicy criada para particionamento."""
        try:
            self.k8s_networking_v1.delete_namespaced_network_policy(
                rollback_data["policy_name"],
                rollback_data["namespace"]
            )

            logger.info(
                "network_injector.partition_removed",
                policy_name=rollback_data["policy_name"],
                namespace=rollback_data["namespace"]
            )

            return InjectionResult(
                success=True,
                injection_id=injection_id,
                fault_type=FaultType.NETWORK_PARTITION,
                end_time=datetime.utcnow()
            )

        except Exception as e:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.NETWORK_PARTITION,
                error_message=str(e)
            )

    async def _rollback_tc(
        self,
        injection_id: str,
        rollback_data: Dict[str, Any]
    ) -> InjectionResult:
        """Remove regras tc dos pods."""
        pods_data = rollback_data.get("pods", {})
        namespace = rollback_data.get("namespace")
        container = rollback_data.get("container")

        failed_pods = []

        for pod_name, rollback_cmd in pods_data.items():
            try:
                exec_result = await self._exec_in_pod(
                    pod_name,
                    namespace,
                    rollback_cmd,
                    container
                )

                if not exec_result.get("success"):
                    failed_pods.append(pod_name)
                    logger.warning(
                        "network_injector.tc_rollback_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )
                else:
                    logger.info(
                        "network_injector.tc_removed",
                        pod=pod_name
                    )

            except Exception as e:
                failed_pods.append(pod_name)
                logger.error(
                    "network_injector.tc_rollback_error",
                    pod=pod_name,
                    error=str(e)
                )

        injection = self._active_injections.get(injection_id)
        fault_type = injection.fault_type if injection else FaultType.NETWORK_LATENCY

        if failed_pods:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=fault_type,
                error_message=f"Rollback falhou em pods: {failed_pods}",
                end_time=datetime.utcnow()
            )

        return InjectionResult(
            success=True,
            injection_id=injection_id,
            fault_type=fault_type,
            end_time=datetime.utcnow()
        )

    async def get_blast_radius(self, target: TargetSelector) -> int:
        """Calcula o número de pods que serão afetados."""
        pods = await self.get_target_pods(target)
        return len(pods)

    def _build_tc_command(self, injection: FaultInjection) -> Optional[str]:
        """Constrói o comando tc baseado no tipo de falha."""
        params = injection.parameters

        if injection.fault_type == FaultType.NETWORK_LATENCY:
            latency = params.latency_ms or 100
            jitter = params.jitter_ms or 0

            if jitter > 0:
                return f"tc qdisc add dev eth0 root netem delay {latency}ms {jitter}ms"
            return f"tc qdisc add dev eth0 root netem delay {latency}ms"

        elif injection.fault_type == FaultType.NETWORK_PACKET_LOSS:
            loss = params.packet_loss_percent or 10
            correlation = params.correlation_percent or 0

            if correlation > 0:
                return f"tc qdisc add dev eth0 root netem loss {loss}% {correlation}%"
            return f"tc qdisc add dev eth0 root netem loss {loss}%"

        elif injection.fault_type == FaultType.NETWORK_BANDWIDTH_LIMIT:
            rate = params.bandwidth_limit_kbps or 1000  # 1 Mbps default
            return f"tc qdisc add dev eth0 root tbf rate {rate}kbit burst 32kbit latency 400ms"

        return None

    def _build_tc_rollback_command(self) -> str:
        """Constrói comando para remover regras tc."""
        return "tc qdisc del dev eth0 root 2>/dev/null || true"

    async def _exec_in_pod(
        self,
        pod_name: str,
        namespace: str,
        command: str,
        container: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executa comando em um pod via Kubernetes API.

        Nota: Requer que o pod tenha capabilities NET_ADMIN para tc.
        """
        if not self.k8s_core_v1:
            return {"success": False, "error": "K8s client não disponível"}

        try:
            from kubernetes.stream import stream

            exec_command = ["/bin/sh", "-c", command]

            kwargs = {
                "command": exec_command,
                "stderr": True,
                "stdin": False,
                "stdout": True,
                "tty": False,
            }

            if container:
                kwargs["container"] = container

            resp = stream(
                self.k8s_core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                **kwargs
            )

            # Stream retorna string diretamente
            return {"success": True, "output": resp}

        except Exception as e:
            return {"success": False, "error": str(e)}
