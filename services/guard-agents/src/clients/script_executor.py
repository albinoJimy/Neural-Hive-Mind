"""Script executor for running remediation scripts via Kubernetes Jobs"""
import asyncio
from typing import Dict, Any, Optional, List
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog
from datetime import datetime, timezone
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Prometheus metrics
script_executions_total = Counter(
    'guard_agents_script_executions_total',
    'Total de execucoes de scripts',
    ['script_type', 'status']
)

script_execution_duration = Histogram(
    'guard_agents_script_execution_duration_seconds',
    'Duracao das execucoes de scripts',
    ['script_type'],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)


class ScriptExecutor:
    """
    Executor de scripts via Kubernetes Jobs.

    Executa scripts de remediação em containers isolados usando Jobs,
    permitindo execução segura e auditável de operações de autocura.
    """

    DEFAULT_IMAGE = "alpine:3.18"
    DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutos
    DEFAULT_TTL_SECONDS = 3600  # 1 hora após conclusão

    def __init__(
        self,
        in_cluster: bool = True,
        namespace: str = "neural-hive",
        enabled: bool = True,
        default_image: Optional[str] = None,
        service_account: str = "guard-agents-executor"
    ):
        self.in_cluster = in_cluster
        self.namespace = namespace
        self.enabled = enabled
        self.default_image = default_image or self.DEFAULT_IMAGE
        self.service_account = service_account
        self.batch_v1: Optional[client.BatchV1Api] = None
        self.core_v1: Optional[client.CoreV1Api] = None
        self._connected = False

    async def connect(self):
        """Conecta ao cluster Kubernetes"""
        if not self.enabled:
            logger.info("script_executor.disabled")
            return

        try:
            if self.in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.batch_v1 = client.BatchV1Api()
            self.core_v1 = client.CoreV1Api()
            self._connected = True

            logger.info(
                "script_executor.connected",
                namespace=self.namespace,
                service_account=self.service_account
            )

        except Exception as e:
            logger.error(
                "script_executor.connection_failed",
                error=str(e)
            )
            self._connected = False

    def is_healthy(self) -> bool:
        """Verifica se executor está saudável"""
        return self.enabled and self._connected and self.batch_v1 is not None

    async def execute_script(
        self,
        script: str,
        script_name: str,
        namespace: Optional[str] = None,
        image: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        incident_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executa um script via Kubernetes Job.

        Args:
            script: Conteúdo do script ou comando a executar
            script_name: Nome identificador do script
            namespace: Namespace para o Job
            image: Imagem Docker para execução
            env_vars: Variáveis de ambiente
            timeout_seconds: Timeout máximo
            incident_id: ID do incidente para rastreamento

        Returns:
            Dict com resultado da execução
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "Script executor not available",
                "script_name": script_name
            }

        ns = namespace or self.namespace
        job_name = self._generate_job_name(script_name, incident_id)

        with script_execution_duration.labels(script_type=script_name).time():
            try:
                # Criar Job
                job = self._build_job(
                    job_name=job_name,
                    script=script,
                    namespace=ns,
                    image=image or self.default_image,
                    env_vars=env_vars,
                    timeout_seconds=timeout_seconds,
                    incident_id=incident_id
                )

                # Submeter Job
                result = self.batch_v1.create_namespaced_job(
                    namespace=ns,
                    body=job
                )

                logger.info(
                    "script_executor.job_created",
                    job_name=job_name,
                    namespace=ns,
                    script_name=script_name
                )

                # Aguardar conclusão
                job_result = await self._wait_for_job_completion(
                    job_name=job_name,
                    namespace=ns,
                    timeout_seconds=timeout_seconds
                )

                # Capturar logs
                logs = await self._get_job_logs(job_name, ns)

                script_executions_total.labels(
                    script_type=script_name,
                    status="success" if job_result.get("succeeded") else "failed"
                ).inc()

                return {
                    "success": job_result.get("succeeded", False),
                    "job_name": job_name,
                    "script_name": script_name,
                    "namespace": ns,
                    "exit_code": job_result.get("exit_code"),
                    "duration_seconds": job_result.get("duration_seconds"),
                    "logs": logs,
                    "status": job_result.get("status")
                }

            except ApiException as e:
                script_executions_total.labels(
                    script_type=script_name,
                    status="error"
                ).inc()

                logger.error(
                    "script_executor.job_failed",
                    job_name=job_name,
                    error=str(e)
                )

                return {
                    "success": False,
                    "job_name": job_name,
                    "script_name": script_name,
                    "error": str(e)
                }

    def _generate_job_name(
        self,
        script_name: str,
        incident_id: Optional[str]
    ) -> str:
        """Gera nome único para o Job"""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        base_name = script_name.replace("_", "-").replace(".", "-").lower()

        if incident_id:
            return f"guard-script-{base_name[:20]}-{incident_id[:8]}-{timestamp}"
        else:
            return f"guard-script-{base_name[:30]}-{timestamp}"

    def _build_job(
        self,
        job_name: str,
        script: str,
        namespace: str,
        image: str,
        env_vars: Optional[Dict[str, str]],
        timeout_seconds: int,
        incident_id: Optional[str]
    ) -> client.V1Job:
        """Constrói objeto Job do Kubernetes"""

        # Construir variáveis de ambiente
        env_list = [
            client.V1EnvVar(name="GUARD_AGENTS_JOB", value="true"),
            client.V1EnvVar(name="SCRIPT_TIMEOUT", value=str(timeout_seconds))
        ]

        if incident_id:
            env_list.append(
                client.V1EnvVar(name="INCIDENT_ID", value=incident_id)
            )

        if env_vars:
            for key, value in env_vars.items():
                env_list.append(client.V1EnvVar(name=key, value=value))

        # Construir container
        container = client.V1Container(
            name="script-executor",
            image=image,
            command=["/bin/sh", "-c"],
            args=[script],
            env=env_list,
            resources=client.V1ResourceRequirements(
                requests={"cpu": "100m", "memory": "128Mi"},
                limits={"cpu": "500m", "memory": "512Mi"}
            ),
            security_context=client.V1SecurityContext(
                run_as_non_root=True,
                run_as_user=1000,
                allow_privilege_escalation=False,
                read_only_root_filesystem=True
            )
        )

        # Construir Pod template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app.kubernetes.io/managed-by": "guard-agents",
                    "guard-agents/job-type": "script-execution"
                },
                annotations={
                    "guard-agents/incident-id": incident_id or "none"
                }
            ),
            spec=client.V1PodSpec(
                containers=[container],
                restart_policy="Never",
                service_account_name=self.service_account,
                automount_service_account_token=False
            )
        )

        # Construir Job
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=namespace,
                labels={
                    "app.kubernetes.io/managed-by": "guard-agents",
                    "guard-agents/job-type": "script-execution"
                }
            ),
            spec=client.V1JobSpec(
                template=template,
                backoff_limit=0,  # Não retry automaticamente
                active_deadline_seconds=timeout_seconds,
                ttl_seconds_after_finished=self.DEFAULT_TTL_SECONDS
            )
        )

        return job

    async def _wait_for_job_completion(
        self,
        job_name: str,
        namespace: str,
        timeout_seconds: int,
        poll_interval: float = 2.0
    ) -> Dict[str, Any]:
        """Aguarda conclusão do Job com polling"""
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            try:
                job = self.batch_v1.read_namespaced_job_status(job_name, namespace)
                status = job.status

                # Verificar conclusão
                if status.succeeded and status.succeeded > 0:
                    duration = asyncio.get_event_loop().time() - start_time
                    return {
                        "succeeded": True,
                        "status": "completed",
                        "exit_code": 0,
                        "duration_seconds": duration
                    }

                if status.failed and status.failed > 0:
                    duration = asyncio.get_event_loop().time() - start_time
                    return {
                        "succeeded": False,
                        "status": "failed",
                        "exit_code": 1,
                        "duration_seconds": duration
                    }

                # Ainda em execução
                await asyncio.sleep(poll_interval)

            except ApiException as e:
                logger.error(
                    "script_executor.status_check_failed",
                    job_name=job_name,
                    error=str(e)
                )
                await asyncio.sleep(poll_interval)

        # Timeout
        duration = asyncio.get_event_loop().time() - start_time
        logger.warning(
            "script_executor.job_timeout",
            job_name=job_name,
            timeout_seconds=timeout_seconds
        )

        return {
            "succeeded": False,
            "status": "timeout",
            "exit_code": -1,
            "duration_seconds": duration
        }

    async def _get_job_logs(
        self,
        job_name: str,
        namespace: str,
        max_lines: int = 1000
    ) -> Optional[str]:
        """Obtém logs do Pod do Job"""
        try:
            # Encontrar pod do job
            pods = self.core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"job-name={job_name}"
            )

            if not pods.items:
                return None

            pod_name = pods.items[0].metadata.name

            # Obter logs
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=max_lines
            )

            return logs

        except ApiException as e:
            logger.warning(
                "script_executor.get_logs_failed",
                job_name=job_name,
                error=str(e)
            )
            return None

    async def get_job_status(
        self,
        job_name: str,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtém status de um Job.

        Args:
            job_name: Nome do Job
            namespace: Namespace do Job

        Returns:
            Dict com status do Job
        """
        if not self.is_healthy():
            return {
                "success": False,
                "error": "Script executor not available",
                "job_name": job_name
            }

        ns = namespace or self.namespace

        try:
            job = self.batch_v1.read_namespaced_job_status(job_name, ns)
            status = job.status

            return {
                "success": True,
                "job_name": job_name,
                "namespace": ns,
                "active": status.active or 0,
                "succeeded": status.succeeded or 0,
                "failed": status.failed or 0,
                "start_time": status.start_time.isoformat() if status.start_time else None,
                "completion_time": status.completion_time.isoformat() if status.completion_time else None
            }

        except ApiException as e:
            return {
                "success": False,
                "job_name": job_name,
                "error": str(e)
            }

    async def cleanup_job(
        self,
        job_name: str,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Remove um Job e seus pods.

        Args:
            job_name: Nome do Job
            namespace: Namespace do Job

        Returns:
            True se removido com sucesso
        """
        if not self.is_healthy():
            return False

        ns = namespace or self.namespace

        try:
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=ns,
                propagation_policy="Foreground"
            )

            logger.info(
                "script_executor.job_cleaned_up",
                job_name=job_name,
                namespace=ns
            )

            return True

        except ApiException as e:
            if e.status == 404:
                return True

            logger.error(
                "script_executor.cleanup_failed",
                job_name=job_name,
                error=str(e)
            )
            return False
