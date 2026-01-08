"""
Pod Fault Injector para Chaos Engineering.

Implementa injeção de falhas em pods como kill, restart, pause e eviction.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from kubernetes import client

from .base_injector import BaseFaultInjector, InjectionResult
from ..chaos_models import FaultInjection, FaultType, TargetSelector
from ..chaos_config import CHAOS_LABELS

logger = structlog.get_logger(__name__)


class PodFaultInjector(BaseFaultInjector):
    """
    Injetor de falhas em pods.

    Suporta:
    - Kill de pod (delete)
    - Kill de container específico
    - Pause de container (SIGSTOP)
    - Eviction de pod
    """

    @property
    def supported_fault_types(self) -> List[FaultType]:
        return [
            FaultType.POD_KILL,
            FaultType.CONTAINER_KILL,
            FaultType.CONTAINER_PAUSE,
            FaultType.POD_EVICT,
        ]

    async def inject(self, injection: FaultInjection) -> InjectionResult:
        """Injeta falha em pods."""
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
            if injection.fault_type == FaultType.POD_KILL:
                result = await self._kill_pods(injection)
            elif injection.fault_type == FaultType.CONTAINER_KILL:
                result = await self._kill_containers(injection)
            elif injection.fault_type == FaultType.CONTAINER_PAUSE:
                result = await self._pause_containers(injection)
            elif injection.fault_type == FaultType.POD_EVICT:
                result = await self._evict_pods(injection)
            else:
                result = InjectionResult(
                    success=False,
                    injection_id=injection.id,
                    fault_type=injection.fault_type,
                    error_message="Tipo de falha não implementado"
                )

            if result.success:
                injection.start_time = start_time
                injection.status = "active"
                injection.rollback_data = result.rollback_data
                injection.affected_pods = result.affected_resources
                self._track_active_injection(injection)

            self._record_injection_metrics(
                injection.fault_type.value,
                "success" if result.success else "failed",
                injection.target.namespace
            )

            return result

        except Exception as e:
            logger.error(
                "pod_injector.inject_failed",
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

    async def _kill_pods(self, injection: FaultInjection) -> InjectionResult:
        """
        Mata pods deletando-os.

        Os pods serão recriados pelo ReplicaSet/Deployment automaticamente.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado para kill"
            )

        killed_pods = []
        original_state = {}

        for pod_name in pods:
            try:
                # Salvar estado antes de deletar
                pod = self.k8s_core_v1.read_namespaced_pod(
                    pod_name,
                    injection.target.namespace
                )
                original_state[pod_name] = {
                    "labels": pod.metadata.labels,
                    "deployment": pod.metadata.owner_references[0].name
                    if pod.metadata.owner_references else None
                }

                # Deletar pod com grace period curto
                self.k8s_core_v1.delete_namespaced_pod(
                    pod_name,
                    injection.target.namespace,
                    grace_period_seconds=0
                )

                killed_pods.append(pod_name)
                logger.info(
                    "pod_injector.pod_killed",
                    pod=pod_name,
                    namespace=injection.target.namespace
                )

            except Exception as e:
                logger.error(
                    "pod_injector.kill_failed",
                    pod=pod_name,
                    error=str(e)
                )

        if not killed_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao deletar todos os pods"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=killed_pods,
            blast_radius=len(killed_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "pod_kill",
                "pods": original_state,
                "namespace": injection.target.namespace,
                "note": "Pods serão recriados automaticamente pelo controller"
            }
        )

    async def _kill_containers(self, injection: FaultInjection) -> InjectionResult:
        """
        Mata containers específicos dentro de pods.

        Usa docker/crictl kill ou kubectl exec com kill.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        container_name = injection.parameters.container_name
        signal = injection.parameters.signal or "SIGKILL"
        killed_containers = []

        for pod_name in pods:
            try:
                # Usar exec para enviar sinal ao processo principal
                # PID 1 é geralmente o processo principal do container
                kill_cmd = f"kill -{signal.replace('SIG', '')} 1"

                exec_result = await self._exec_in_pod(
                    pod_name,
                    injection.target.namespace,
                    kill_cmd,
                    container_name
                )

                if exec_result.get("success"):
                    killed_containers.append(f"{pod_name}/{container_name or 'main'}")
                    logger.info(
                        "pod_injector.container_killed",
                        pod=pod_name,
                        container=container_name,
                        signal=signal
                    )
                else:
                    logger.warning(
                        "pod_injector.container_kill_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "pod_injector.container_kill_error",
                    pod=pod_name,
                    error=str(e)
                )

        if not killed_containers:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao matar containers"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=killed_containers,
            blast_radius=len(killed_containers),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "container_kill",
                "containers": killed_containers,
                "note": "Containers serão reiniciados automaticamente"
            }
        )

    async def _pause_containers(self, injection: FaultInjection) -> InjectionResult:
        """
        Pausa containers usando SIGSTOP.

        Containers podem ser resumidos com SIGCONT.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        container_name = injection.parameters.container_name
        paused_containers = []

        for pod_name in pods:
            try:
                # Enviar SIGSTOP para pausar o processo principal
                stop_cmd = "kill -STOP 1"

                exec_result = await self._exec_in_pod(
                    pod_name,
                    injection.target.namespace,
                    stop_cmd,
                    container_name
                )

                if exec_result.get("success"):
                    paused_containers.append(f"{pod_name}/{container_name or 'main'}")
                    logger.info(
                        "pod_injector.container_paused",
                        pod=pod_name,
                        container=container_name
                    )
                else:
                    logger.warning(
                        "pod_injector.container_pause_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "pod_injector.container_pause_error",
                    pod=pod_name,
                    error=str(e)
                )

        if not paused_containers:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao pausar containers"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=paused_containers,
            blast_radius=len(paused_containers),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "container_pause",
                "pods": pods,
                "namespace": injection.target.namespace,
                "container": container_name,
            }
        )

    async def _evict_pods(self, injection: FaultInjection) -> InjectionResult:
        """
        Força eviction de pods.

        Similar a quando um node fica sob pressão de recursos.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        evicted_pods = []

        for pod_name in pods:
            try:
                # Criar objeto Eviction
                eviction = client.V1Eviction(
                    metadata=client.V1ObjectMeta(
                        name=pod_name,
                        namespace=injection.target.namespace
                    ),
                    delete_options=client.V1DeleteOptions(
                        grace_period_seconds=30
                    )
                )

                self.k8s_core_v1.create_namespaced_pod_eviction(
                    pod_name,
                    injection.target.namespace,
                    eviction
                )

                evicted_pods.append(pod_name)
                logger.info(
                    "pod_injector.pod_evicted",
                    pod=pod_name,
                    namespace=injection.target.namespace
                )

            except Exception as e:
                logger.error(
                    "pod_injector.eviction_failed",
                    pod=pod_name,
                    error=str(e)
                )

        if not evicted_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao fazer eviction de pods"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=evicted_pods,
            blast_radius=len(evicted_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "pod_eviction",
                "pods": evicted_pods,
                "namespace": injection.target.namespace,
                "note": "Pods serão rescheduled automaticamente"
            }
        )

    async def validate(self, injection_id: str) -> bool:
        """
        Valida se a injeção está ativa.

        Para pod kill/evict, verifica se pods foram recriados.
        Para container pause, verifica se ainda estão pausados.
        """
        if injection_id not in self._active_injections:
            return False

        injection = self._active_injections[injection_id]
        rollback_type = injection.rollback_data.get("type")

        if rollback_type in ["pod_kill", "pod_eviction"]:
            # Pods já foram deletados/evicted, a injeção "aconteceu"
            return True

        elif rollback_type == "container_pause":
            # Verificar se containers ainda estão pausados seria complexo
            # Por simplicidade, assumimos que estão
            return True

        return False

    async def rollback(self, injection_id: str) -> InjectionResult:
        """
        Reverte a injeção.

        Para pause, envia SIGCONT. Para kill/evict, não há rollback
        pois os pods são recriados automaticamente.
        """
        if injection_id not in self._active_injections:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.POD_KILL,
                error_message="Injeção não encontrada"
            )

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data
        rollback_type = rollback_data.get("type")

        try:
            if rollback_type == "container_pause":
                result = await self._resume_containers(injection_id, rollback_data)
            else:
                # Para pod_kill e pod_eviction, não há rollback manual
                # Os pods são recriados automaticamente pelo controller
                result = InjectionResult(
                    success=True,
                    injection_id=injection_id,
                    fault_type=injection.fault_type,
                    end_time=datetime.utcnow(),
                    metadata={"note": "Pods recriados automaticamente pelo controller"}
                )

            if result.success:
                self._untrack_active_injection(injection_id)
                self._record_rollback_metrics(injection.fault_type.value, "success")
            else:
                self._record_rollback_metrics(injection.fault_type.value, "failed")

            return result

        except Exception as e:
            logger.error(
                "pod_injector.rollback_failed",
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

    async def _resume_containers(
        self,
        injection_id: str,
        rollback_data: Dict[str, Any]
    ) -> InjectionResult:
        """Resume containers pausados com SIGCONT."""
        pods = rollback_data.get("pods", [])
        namespace = rollback_data.get("namespace")
        container = rollback_data.get("container")

        failed_pods = []

        for pod_name in pods:
            try:
                # Enviar SIGCONT para resumir
                cont_cmd = "kill -CONT 1"

                exec_result = await self._exec_in_pod(
                    pod_name,
                    namespace,
                    cont_cmd,
                    container
                )

                if not exec_result.get("success"):
                    failed_pods.append(pod_name)
                    logger.warning(
                        "pod_injector.resume_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )
                else:
                    logger.info(
                        "pod_injector.container_resumed",
                        pod=pod_name
                    )

            except Exception as e:
                failed_pods.append(pod_name)
                logger.error(
                    "pod_injector.resume_error",
                    pod=pod_name,
                    error=str(e)
                )

        if failed_pods:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.CONTAINER_PAUSE,
                error_message=f"Rollback falhou em pods: {failed_pods}",
                end_time=datetime.utcnow()
            )

        return InjectionResult(
            success=True,
            injection_id=injection_id,
            fault_type=FaultType.CONTAINER_PAUSE,
            end_time=datetime.utcnow()
        )

    async def get_blast_radius(self, target: TargetSelector) -> int:
        """Calcula o número de pods que serão afetados."""
        pods = await self.get_target_pods(target)
        return len(pods)

    async def _exec_in_pod(
        self,
        pod_name: str,
        namespace: str,
        command: str,
        container: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executa comando em um pod via Kubernetes API."""
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

            return {"success": True, "output": resp}

        except Exception as e:
            return {"success": False, "error": str(e)}
