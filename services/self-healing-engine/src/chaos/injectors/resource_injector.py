"""
Resource Fault Injector para Chaos Engineering.

Implementa injeção de falhas de recursos como stress de CPU, memória,
preenchimento de disco e esgotamento de file descriptors.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

from .base_injector import BaseFaultInjector, InjectionResult
from ..chaos_models import FaultInjection, FaultType, TargetSelector

logger = structlog.get_logger(__name__)


class ResourceFaultInjector(BaseFaultInjector):
    """
    Injetor de falhas de recursos.

    Suporta:
    - Stress de CPU via stress-ng
    - Stress de memória via stress-ng
    - Preenchimento de disco via dd/fallocate
    - Esgotamento de file descriptors
    """

    @property
    def supported_fault_types(self) -> List[FaultType]:
        return [
            FaultType.CPU_STRESS,
            FaultType.MEMORY_STRESS,
            FaultType.DISK_FILL,
            FaultType.FD_EXHAUST,
        ]

    async def inject(self, injection: FaultInjection) -> InjectionResult:
        """Injeta falha de recursos no sistema."""
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
            if injection.fault_type == FaultType.CPU_STRESS:
                result = await self._stress_cpu(injection)
            elif injection.fault_type == FaultType.MEMORY_STRESS:
                result = await self._stress_memory(injection)
            elif injection.fault_type == FaultType.DISK_FILL:
                result = await self._fill_disk(injection)
            elif injection.fault_type == FaultType.FD_EXHAUST:
                result = await self._exhaust_fds(injection)
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
                "resource_injector.inject_failed",
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

    async def _stress_cpu(self, injection: FaultInjection) -> InjectionResult:
        """
        Aplica stress de CPU usando stress-ng.

        Requer stress-ng instalado no container ou usa fallback com loops.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        params = injection.parameters
        cpu_cores = params.cpu_cores or 1
        cpu_load = params.cpu_load_percent or 80
        duration = injection.duration_seconds

        affected_pods = []
        process_pids = {}

        for pod_name in pods:
            try:
                # Tentar usar stress-ng primeiro, fallback para loop
                stress_cmd = self._build_cpu_stress_command(cpu_cores, cpu_load, duration)

                exec_result = await self._exec_in_pod_background(
                    pod_name,
                    injection.target.namespace,
                    stress_cmd,
                    params.container_name
                )

                if exec_result.get("success"):
                    affected_pods.append(pod_name)
                    if exec_result.get("pid"):
                        process_pids[pod_name] = exec_result["pid"]
                    logger.info(
                        "resource_injector.cpu_stress_started",
                        pod=pod_name,
                        cores=cpu_cores,
                        load=cpu_load
                    )
                else:
                    logger.warning(
                        "resource_injector.cpu_stress_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "resource_injector.cpu_stress_error",
                    pod=pod_name,
                    error=str(e)
                )

        if not affected_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao aplicar stress de CPU"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=affected_pods,
            blast_radius=len(affected_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "cpu_stress",
                "pods": affected_pods,
                "pids": process_pids,
                "namespace": injection.target.namespace,
                "container": params.container_name,
            }
        )

    async def _stress_memory(self, injection: FaultInjection) -> InjectionResult:
        """
        Aplica stress de memória usando stress-ng.

        Aloca memória especificada para criar pressão no sistema.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        params = injection.parameters
        memory_bytes = params.memory_bytes or (256 * 1024 * 1024)  # 256MB default
        memory_mb = memory_bytes // (1024 * 1024)
        duration = injection.duration_seconds

        affected_pods = []
        process_pids = {}

        for pod_name in pods:
            try:
                stress_cmd = self._build_memory_stress_command(memory_mb, duration)

                exec_result = await self._exec_in_pod_background(
                    pod_name,
                    injection.target.namespace,
                    stress_cmd,
                    params.container_name
                )

                if exec_result.get("success"):
                    affected_pods.append(pod_name)
                    if exec_result.get("pid"):
                        process_pids[pod_name] = exec_result["pid"]
                    logger.info(
                        "resource_injector.memory_stress_started",
                        pod=pod_name,
                        memory_mb=memory_mb
                    )
                else:
                    logger.warning(
                        "resource_injector.memory_stress_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "resource_injector.memory_stress_error",
                    pod=pod_name,
                    error=str(e)
                )

        if not affected_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao aplicar stress de memória"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=affected_pods,
            blast_radius=len(affected_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "memory_stress",
                "pods": affected_pods,
                "pids": process_pids,
                "namespace": injection.target.namespace,
                "container": params.container_name,
            }
        )

    async def _fill_disk(self, injection: FaultInjection) -> InjectionResult:
        """
        Preenche disco com dados temporários.

        Usa fallocate ou dd para criar arquivos grandes.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        params = injection.parameters
        fill_bytes = params.disk_fill_bytes or (1024 * 1024 * 1024)  # 1GB default
        fill_mb = fill_bytes // (1024 * 1024)
        disk_path = params.disk_path or "/tmp"
        file_name = f"chaos-disk-{injection.id[:8]}.dat"

        affected_pods = []
        created_files = {}

        for pod_name in pods:
            try:
                file_path = f"{disk_path}/{file_name}"
                fill_cmd = self._build_disk_fill_command(file_path, fill_mb)

                exec_result = await self._exec_in_pod(
                    pod_name,
                    injection.target.namespace,
                    fill_cmd,
                    params.container_name
                )

                if exec_result.get("success"):
                    affected_pods.append(pod_name)
                    created_files[pod_name] = file_path
                    logger.info(
                        "resource_injector.disk_filled",
                        pod=pod_name,
                        size_mb=fill_mb,
                        path=file_path
                    )
                else:
                    logger.warning(
                        "resource_injector.disk_fill_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "resource_injector.disk_fill_error",
                    pod=pod_name,
                    error=str(e)
                )

        if not affected_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao preencher disco"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=affected_pods,
            blast_radius=len(affected_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "disk_fill",
                "pods": affected_pods,
                "files": created_files,
                "namespace": injection.target.namespace,
                "container": params.container_name,
            }
        )

    async def _exhaust_fds(self, injection: FaultInjection) -> InjectionResult:
        """
        Esgota file descriptors do processo.

        Abre muitos arquivos/sockets para esgotar o limite de FDs.
        """
        pods = await self.get_target_pods(injection.target)
        if not pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Nenhum pod encontrado"
            )

        params = injection.parameters
        duration = injection.duration_seconds

        affected_pods = []
        process_pids = {}

        for pod_name in pods:
            try:
                # Script para esgotar FDs
                fd_cmd = self._build_fd_exhaust_command(duration)

                exec_result = await self._exec_in_pod_background(
                    pod_name,
                    injection.target.namespace,
                    fd_cmd,
                    params.container_name
                )

                if exec_result.get("success"):
                    affected_pods.append(pod_name)
                    if exec_result.get("pid"):
                        process_pids[pod_name] = exec_result["pid"]
                    logger.info(
                        "resource_injector.fd_exhaust_started",
                        pod=pod_name
                    )
                else:
                    logger.warning(
                        "resource_injector.fd_exhaust_failed",
                        pod=pod_name,
                        error=exec_result.get("error")
                    )

            except Exception as e:
                logger.error(
                    "resource_injector.fd_exhaust_error",
                    pod=pod_name,
                    error=str(e)
                )

        if not affected_pods:
            return InjectionResult(
                success=False,
                injection_id=injection.id,
                fault_type=injection.fault_type,
                error_message="Falha ao esgotar file descriptors"
            )

        return InjectionResult(
            success=True,
            injection_id=injection.id,
            fault_type=injection.fault_type,
            affected_resources=affected_pods,
            blast_radius=len(affected_pods),
            start_time=datetime.utcnow(),
            rollback_data={
                "type": "fd_exhaust",
                "pods": affected_pods,
                "pids": process_pids,
                "namespace": injection.target.namespace,
                "container": params.container_name,
            }
        )

    async def validate(self, injection_id: str) -> bool:
        """Valida se a injeção de recursos está ativa."""
        if injection_id not in self._active_injections:
            return False

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data
        rollback_type = rollback_data.get("type")

        if rollback_type == "disk_fill":
            # Verificar se arquivos ainda existem
            files = rollback_data.get("files", {})
            namespace = rollback_data.get("namespace")
            container = rollback_data.get("container")

            for pod_name, file_path in files.items():
                try:
                    check_cmd = f"test -f {file_path} && echo 'exists'"
                    result = await self._exec_in_pod(
                        pod_name, namespace, check_cmd, container
                    )
                    if result.get("success") and "exists" in result.get("output", ""):
                        return True
                except Exception:
                    continue
            return False

        elif rollback_type in ["cpu_stress", "memory_stress", "fd_exhaust"]:
            # Para stress, verificar se processos ainda estão rodando
            pids = rollback_data.get("pids", {})
            if not pids:
                # Se não temos PIDs, assumir que está ativo se está na lista
                return True

            namespace = rollback_data.get("namespace")
            container = rollback_data.get("container")

            for pod_name, pid in pids.items():
                try:
                    check_cmd = f"kill -0 {pid} 2>/dev/null && echo 'running'"
                    result = await self._exec_in_pod(
                        pod_name, namespace, check_cmd, container
                    )
                    if result.get("success") and "running" in result.get("output", ""):
                        return True
                except Exception:
                    continue
            return False

        return False

    async def rollback(self, injection_id: str) -> InjectionResult:
        """Remove a injeção de recursos."""
        if injection_id not in self._active_injections:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.CPU_STRESS,
                error_message="Injeção não encontrada"
            )

        injection = self._active_injections[injection_id]
        rollback_data = injection.rollback_data
        rollback_type = rollback_data.get("type")

        try:
            if rollback_type == "disk_fill":
                result = await self._cleanup_disk_files(injection_id, rollback_data)
            elif rollback_type in ["cpu_stress", "memory_stress", "fd_exhaust"]:
                result = await self._kill_stress_processes(injection_id, rollback_data)
            else:
                result = InjectionResult(
                    success=False,
                    injection_id=injection_id,
                    fault_type=injection.fault_type,
                    error_message=f"Tipo de rollback desconhecido: {rollback_type}"
                )

            if result.success:
                self._untrack_active_injection(injection_id)
                self._record_rollback_metrics(injection.fault_type.value, "success")
            else:
                self._record_rollback_metrics(injection.fault_type.value, "failed")

            return result

        except Exception as e:
            logger.error(
                "resource_injector.rollback_failed",
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

    async def _cleanup_disk_files(
        self,
        injection_id: str,
        rollback_data: Dict[str, Any]
    ) -> InjectionResult:
        """Remove arquivos criados para disk fill."""
        files = rollback_data.get("files", {})
        namespace = rollback_data.get("namespace")
        container = rollback_data.get("container")

        failed_pods = []

        for pod_name, file_path in files.items():
            try:
                rm_cmd = f"rm -f {file_path}"
                result = await self._exec_in_pod(
                    pod_name, namespace, rm_cmd, container
                )

                if result.get("success"):
                    logger.info(
                        "resource_injector.disk_file_removed",
                        pod=pod_name,
                        file=file_path
                    )
                else:
                    failed_pods.append(pod_name)
                    logger.warning(
                        "resource_injector.disk_cleanup_failed",
                        pod=pod_name,
                        error=result.get("error")
                    )

            except Exception as e:
                failed_pods.append(pod_name)
                logger.error(
                    "resource_injector.disk_cleanup_error",
                    pod=pod_name,
                    error=str(e)
                )

        if failed_pods:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=FaultType.DISK_FILL,
                error_message=f"Cleanup falhou em pods: {failed_pods}",
                end_time=datetime.utcnow()
            )

        return InjectionResult(
            success=True,
            injection_id=injection_id,
            fault_type=FaultType.DISK_FILL,
            end_time=datetime.utcnow()
        )

    async def _kill_stress_processes(
        self,
        injection_id: str,
        rollback_data: Dict[str, Any]
    ) -> InjectionResult:
        """Mata processos de stress em execução."""
        pods = rollback_data.get("pods", [])
        pids = rollback_data.get("pids", {})
        namespace = rollback_data.get("namespace")
        container = rollback_data.get("container")
        rollback_type = rollback_data.get("type")

        failed_pods = []

        for pod_name in pods:
            try:
                if pod_name in pids:
                    # Matar PID específico
                    kill_cmd = f"kill -9 {pids[pod_name]} 2>/dev/null || true"
                else:
                    # Matar todos os processos stress-ng
                    kill_cmd = "pkill -9 stress-ng 2>/dev/null || pkill -9 stress 2>/dev/null || true"

                result = await self._exec_in_pod(
                    pod_name, namespace, kill_cmd, container
                )

                if result.get("success"):
                    logger.info(
                        "resource_injector.stress_killed",
                        pod=pod_name
                    )
                else:
                    failed_pods.append(pod_name)

            except Exception as e:
                failed_pods.append(pod_name)
                logger.error(
                    "resource_injector.kill_stress_error",
                    pod=pod_name,
                    error=str(e)
                )

        # Determinar fault_type baseado no rollback_type
        fault_type_map = {
            "cpu_stress": FaultType.CPU_STRESS,
            "memory_stress": FaultType.MEMORY_STRESS,
            "fd_exhaust": FaultType.FD_EXHAUST,
        }
        fault_type = fault_type_map.get(rollback_type, FaultType.CPU_STRESS)

        if failed_pods:
            return InjectionResult(
                success=False,
                injection_id=injection_id,
                fault_type=fault_type,
                error_message=f"Kill falhou em pods: {failed_pods}",
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

    def _build_cpu_stress_command(
        self,
        cores: int,
        load_percent: int,
        duration: int
    ) -> str:
        """Constrói comando para stress de CPU."""
        # Tentar stress-ng, fallback para loop de busy wait
        return (
            f"(stress-ng --cpu {cores} --cpu-load {load_percent} "
            f"--timeout {duration}s 2>/dev/null || "
            f"timeout {duration} sh -c 'while true; do :; done') &"
        )

    def _build_memory_stress_command(self, memory_mb: int, duration: int) -> str:
        """Constrói comando para stress de memória."""
        return (
            f"(stress-ng --vm 1 --vm-bytes {memory_mb}M "
            f"--timeout {duration}s 2>/dev/null || "
            f"timeout {duration} sh -c 'head -c {memory_mb}m /dev/zero | tail') &"
        )

    def _build_disk_fill_command(self, file_path: str, size_mb: int) -> str:
        """Constrói comando para preenchimento de disco."""
        return (
            f"fallocate -l {size_mb}M {file_path} 2>/dev/null || "
            f"dd if=/dev/zero of={file_path} bs=1M count={size_mb} 2>/dev/null"
        )

    def _build_fd_exhaust_command(self, duration: int) -> str:
        """Constrói comando para esgotar file descriptors."""
        return (
            f"timeout {duration} sh -c '"
            "exec 3>/dev/null; "
            "while true; do "
            "  exec 3>/dev/null 2>/dev/null || break; "
            "done; "
            f"sleep {duration}' &"
        )

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

    async def _exec_in_pod_background(
        self,
        pod_name: str,
        namespace: str,
        command: str,
        container: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executa comando em background em um pod.

        Retorna PID do processo para posterior cleanup.
        """
        # O comando já deve terminar com & para rodar em background
        # Adicionar captura de PID
        bg_command = f"{{ {command} }} & echo $!"

        result = await self._exec_in_pod(pod_name, namespace, bg_command, container)

        if result.get("success"):
            output = result.get("output", "").strip()
            try:
                pid = int(output.split("\n")[-1])
                result["pid"] = pid
            except (ValueError, IndexError):
                pass

        return result
