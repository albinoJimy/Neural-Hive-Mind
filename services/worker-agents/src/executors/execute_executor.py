"""
Executor para task_type=EXECUTE com suporte multi-runtime.

Suporta execução de comandos via:
- Kubernetes Jobs (isolamento completo)
- Docker containers (isolamento de filesystem)
- AWS Lambda (serverless)
- Local subprocess (fallback)
- Simulação (fallback final)
"""

import asyncio
import random
import time
from typing import Any, Dict, Optional, List
from neural_hive_integration.clients.code_forge_client import CodeForgeClient
from neural_hive_observability import get_tracer
from .base_executor import BaseTaskExecutor


class ExecuteExecutor(BaseTaskExecutor):
    """Executor para task_type=EXECUTE com suporte multi-runtime."""

    def get_task_type(self) -> str:
        return 'EXECUTE'

    def __init__(
        self,
        config,
        vault_client=None,
        code_forge_client: Optional[CodeForgeClient] = None,
        metrics=None,
        docker_client=None,
        k8s_jobs_client=None,
        lambda_client=None,
        local_client=None
    ):
        """
        Inicializa ExecuteExecutor com clientes de runtime.

        Args:
            config: Configurações do worker agent
            vault_client: Cliente Vault para secrets
            code_forge_client: Cliente Code Forge para geração de código
            metrics: Objeto de métricas Prometheus
            docker_client: DockerRuntimeClient para execução via Docker
            k8s_jobs_client: KubernetesJobsClient para execução via K8s Jobs
            lambda_client: LambdaRuntimeClient para execução via Lambda
            local_client: LocalRuntimeClient para execução local
        """
        super().__init__(config, vault_client=vault_client, code_forge_client=code_forge_client, metrics=metrics)
        self.docker_client = docker_client
        self.k8s_jobs_client = k8s_jobs_client
        self.lambda_client = lambda_client
        self.local_client = local_client

    def _get_available_runtimes(self) -> List[str]:
        """Retorna lista de runtimes disponíveis."""
        available = []
        if self.k8s_jobs_client:
            available.append('k8s')
        if self.docker_client:
            available.append('docker')
        if self.lambda_client:
            available.append('lambda')
        if self.local_client:
            available.append('local')
        available.append('simulation')
        return available

    def _select_runtime(self, requested_runtime: Optional[str]) -> str:
        """
        Seleciona runtime baseado em preferência e disponibilidade.

        Args:
            requested_runtime: Runtime solicitado pelo ticket

        Returns:
            Nome do runtime a usar
        """
        available = self._get_available_runtimes()

        # Se runtime específico solicitado e disponível
        if requested_runtime and requested_runtime in available:
            return requested_runtime

        # Usar runtime padrão se disponível
        default = getattr(self.config, 'default_runtime', 'local')
        if default in available:
            return default

        # Seguir cadeia de fallback
        fallback_chain = getattr(self.config, 'runtime_fallback_chain', ['k8s', 'docker', 'local', 'simulation'])
        for runtime in fallback_chain:
            if runtime in available:
                return runtime

        # Fallback final
        return 'simulation'

    async def _execute_k8s(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa via Kubernetes Jobs."""
        from ..clients.k8s_jobs_client import K8sJobRequest, K8sResourceRequirements, K8sJobStatus

        self.log_execution(ticket_id, 'k8s_execution_starting', runtime='k8s')

        # Construir request
        command = parameters.get('command', 'echo')
        if isinstance(command, str):
            command = command.split()

        args = parameters.get('args', [])
        if isinstance(args, str):
            args = args.split()

        request = K8sJobRequest(
            namespace=getattr(self.config, 'k8s_jobs_namespace', 'neural-hive-execution'),
            image=parameters.get('image', 'python:3.11-slim'),
            command=command,
            args=args if args else None,
            env_vars=parameters.get('env_vars'),
            timeout_seconds=parameters.get('timeout_seconds', getattr(self.config, 'k8s_jobs_timeout_seconds', 600)),
            resource_limits=K8sResourceRequirements(
                cpu_request=parameters.get('cpu_request', getattr(self.config, 'k8s_jobs_default_cpu_request', '100m')),
                cpu_limit=parameters.get('cpu_limit', getattr(self.config, 'k8s_jobs_default_cpu_limit', '1000m')),
                memory_request=parameters.get('memory_request', getattr(self.config, 'k8s_jobs_default_memory_request', '128Mi')),
                memory_limit=parameters.get('memory_limit', getattr(self.config, 'k8s_jobs_default_memory_limit', '512Mi')),
            ),
            service_account=parameters.get('service_account', getattr(self.config, 'k8s_jobs_service_account', None)),
        )

        result = await self.k8s_jobs_client.execute_job(request, metrics=self.metrics)

        success = result.status == K8sJobStatus.SUCCEEDED
        exit_code = result.exit_code if result.exit_code is not None else (0 if success else 1)

        self.log_execution(
            ticket_id,
            'k8s_execution_completed',
            job_name=result.job_name,
            status=result.status.value,
            exit_code=exit_code,
            duration_ms=result.duration_ms
        )

        span.set_attribute('neural.hive.runtime', 'k8s')
        span.set_attribute('neural.hive.job_name', result.job_name)

        return {
            'success': success,
            'output': {
                'exit_code': exit_code,
                'stdout': result.logs,
                'stderr': '',
                'job_name': result.job_name,
                'pod_name': result.pod_name,
            },
            'metadata': {
                'executor': 'ExecuteExecutor',
                'runtime': 'k8s',
                'simulated': False,
                'duration_seconds': result.duration_ms / 1000
            },
            'logs': [
                'Execution started via Kubernetes Job',
                f'Job: {result.job_name}',
                f'Pod: {result.pod_name}',
                f'Status: {result.status.value}',
                f'Exit code: {exit_code}',
                'Execution completed'
            ]
        }

    async def _execute_docker(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa via Docker container."""
        from ..clients.docker_runtime_client import DockerExecutionRequest, ResourceLimits, DockerNetworkMode

        self.log_execution(ticket_id, 'docker_execution_starting', runtime='docker')

        # Construir request
        command = parameters.get('command', ['echo', 'hello'])
        if isinstance(command, str):
            command = command.split()

        args = parameters.get('args', [])
        if isinstance(args, str):
            args = args.split()

        request = DockerExecutionRequest(
            image=parameters.get('image', 'python:3.11-slim'),
            command=command,
            args=args if args else None,
            env_vars=parameters.get('env_vars'),
            working_dir=parameters.get('working_dir'),
            timeout_seconds=parameters.get('timeout_seconds', getattr(self.config, 'docker_timeout_seconds', 600)),
            resource_limits=ResourceLimits(
                cpu_limit=parameters.get('cpu_limit', getattr(self.config, 'docker_default_cpu_limit', 1.0)),
                memory_limit=parameters.get('memory_limit', getattr(self.config, 'docker_default_memory_limit', '512m')),
            ),
            network_mode=DockerNetworkMode(parameters.get('network_mode', getattr(self.config, 'docker_network_mode', 'bridge'))),
        )

        result = await self.docker_client.execute_command(request, metrics=self.metrics)

        success = result.exit_code == 0

        self.log_execution(
            ticket_id,
            'docker_execution_completed',
            container_id=result.container_id,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms
        )

        span.set_attribute('neural.hive.runtime', 'docker')
        span.set_attribute('neural.hive.container_id', result.container_id)

        return {
            'success': success,
            'output': {
                'exit_code': result.exit_code,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'container_id': result.container_id,
            },
            'metadata': {
                'executor': 'ExecuteExecutor',
                'runtime': 'docker',
                'simulated': False,
                'duration_seconds': result.duration_ms / 1000,
                'image_pulled': result.image_pulled
            },
            'logs': [
                'Execution started via Docker',
                f'Container: {result.container_id}',
                f'Image: {request.image}',
                f'Exit code: {result.exit_code}',
                'Execution completed'
            ]
        }

    async def _execute_lambda(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa via AWS Lambda."""
        from ..clients.lambda_runtime_client import LambdaInvocationRequest, LambdaPayload

        self.log_execution(ticket_id, 'lambda_execution_starting', runtime='lambda')

        # Construir request
        command = parameters.get('command', 'echo')
        if isinstance(command, list):
            command = ' '.join(command)

        args = parameters.get('args', [])

        request = LambdaInvocationRequest(
            function_name=parameters.get('function_name', getattr(self.config, 'lambda_function_name', 'neural-hive-executor')),
            payload=LambdaPayload(
                command=command,
                args=args,
                env_vars=parameters.get('env_vars'),
                working_dir=parameters.get('working_dir'),
                timeout_seconds=parameters.get('timeout_seconds'),
            ),
        )

        result = await self.lambda_client.invoke_lambda(request, metrics=self.metrics)

        success = result.function_error is None and result.response.exit_code == 0

        self.log_execution(
            ticket_id,
            'lambda_execution_completed',
            request_id=result.request_id,
            status_code=result.status_code,
            exit_code=result.response.exit_code,
            duration_ms=result.duration_ms
        )

        span.set_attribute('neural.hive.runtime', 'lambda')
        span.set_attribute('neural.hive.request_id', result.request_id)

        return {
            'success': success,
            'output': {
                'exit_code': result.response.exit_code,
                'stdout': result.response.stdout,
                'stderr': result.response.stderr,
                'request_id': result.request_id,
            },
            'metadata': {
                'executor': 'ExecuteExecutor',
                'runtime': 'lambda',
                'simulated': False,
                'duration_seconds': result.duration_ms / 1000,
                'billed_duration_ms': result.billed_duration_ms,
                'memory_used_mb': result.memory_used_mb
            },
            'logs': [
                'Execution started via AWS Lambda',
                f'Request ID: {result.request_id}',
                f'Function: {request.function_name}',
                f'Exit code: {result.response.exit_code}',
                'Execution completed'
            ]
        }

    async def _execute_local(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Executa localmente via subprocess."""
        from ..clients.local_runtime_client import LocalExecutionRequest

        self.log_execution(ticket_id, 'local_execution_starting', runtime='local')

        # Construir request
        command = parameters.get('command', 'echo')
        if isinstance(command, list):
            # Manter lista original, extrair base_cmd e cmd_args
            base_cmd = command[0]
            cmd_args = list(command[1:])
        else:
            base_cmd = command
            cmd_args = []

        # Converter args extras para lista se fornecido
        extra_args = parameters.get('args', [])
        if isinstance(extra_args, str):
            extra_args = extra_args.split()
        elif not isinstance(extra_args, list):
            extra_args = []

        # Concatenar como listas para evitar TypeError str+list
        args = cmd_args + extra_args

        request = LocalExecutionRequest(
            command=base_cmd,
            args=args if args else None,
            env_vars=parameters.get('env_vars'),
            working_dir=parameters.get('working_dir'),
            timeout_seconds=parameters.get('timeout_seconds', getattr(self.config, 'local_runtime_timeout_seconds', 300)),
            shell=parameters.get('shell', False),
        )

        result = await self.local_client.execute_local(request, metrics=self.metrics)

        success = result.exit_code == 0

        self.log_execution(
            ticket_id,
            'local_execution_completed',
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            pid=result.pid
        )

        span.set_attribute('neural.hive.runtime', 'local')
        span.set_attribute('neural.hive.pid', result.pid or 0)

        return {
            'success': success,
            'output': {
                'exit_code': result.exit_code,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': result.command_executed,
            },
            'metadata': {
                'executor': 'ExecuteExecutor',
                'runtime': 'local',
                'simulated': False,
                'duration_seconds': result.duration_ms / 1000
            },
            'logs': [
                'Execution started locally',
                f'Command: {result.command_executed}',
                f'PID: {result.pid}',
                f'Exit code: {result.exit_code}',
                'Execution completed'
            ]
        }

    async def _execute_simulation(self, ticket_id: str, parameters: Dict[str, Any], span) -> Dict[str, Any]:
        """Fallback para execução simulada."""
        self.log_execution(ticket_id, 'simulation_execution_starting', runtime='simulation')

        delay = random.uniform(2, 4)
        await asyncio.sleep(delay)

        cmd = parameters.get('command', 'unknown')
        if isinstance(cmd, list):
            cmd = ' '.join(cmd)

        span.set_attribute('neural.hive.runtime', 'simulation')

        return {
            'success': True,
            'output': {
                'exit_code': 0,
                'stdout': f'[SIMULAÇÃO] Output para comando: {cmd}',
                'stderr': '',
                'command': cmd
            },
            'metadata': {
                'executor': 'ExecuteExecutor',
                'runtime': 'simulation',
                'simulated': True,
                'duration_seconds': delay
            },
            'logs': [
                'Execution started (SIMULATION MODE)',
                f'Command: {cmd}',
                f'Simulated execution for {delay:.2f}s',
                'Execution completed (simulated)'
            ]
        }

    async def _execute_code_forge(self, ticket_id: str, parameters: Dict[str, Any], span) -> Optional[Dict[str, Any]]:
        """Tenta execução via Code Forge para geração de código."""
        if not self.code_forge_client:
            return None

        template_id = parameters.get('template_id') or parameters.get('template')
        if not template_id:
            return None

        try:
            request_id = await self.code_forge_client.submit_generation_request(
                ticket_id,
                template_id,
                parameters
            )

            poll_interval = 5
            timeout_seconds = 1800
            start_time = asyncio.get_event_loop().time()

            while True:
                status = await self.code_forge_client.get_generation_status(request_id)

                if status.status in ['completed', 'failed']:
                    break

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    raise asyncio.TimeoutError(f'Generation timeout after {timeout_seconds}s')

                await asyncio.sleep(poll_interval)

            duration_seconds = asyncio.get_event_loop().time() - start_time

            if status.status == 'completed':
                span.set_attribute('neural.hive.runtime', 'code_forge')
                return {
                    'success': True,
                    'output': {
                        'request_id': request_id,
                        'artifacts': status.artifacts,
                        'pipeline_id': status.pipeline_id
                    },
                    'metadata': {
                        'executor': 'ExecuteExecutor',
                        'runtime': 'code_forge',
                        'simulated': False,
                        'duration_seconds': duration_seconds
                    },
                    'logs': [
                        'Execution started via Code Forge',
                        f'Request: {request_id}',
                        f'Template: {template_id}',
                        f'Artifacts: {len(status.artifacts)}',
                        'Execution completed'
                    ]
                }
            else:
                return {
                    'success': False,
                    'output': {
                        'request_id': request_id,
                        'artifacts': status.artifacts,
                        'pipeline_id': status.pipeline_id
                    },
                    'metadata': {
                        'executor': 'ExecuteExecutor',
                        'runtime': 'code_forge',
                        'simulated': False,
                        'duration_seconds': duration_seconds
                    },
                    'logs': [
                        'Execution started via Code Forge',
                        f'Request: {request_id}',
                        f'Status: {status.status}',
                        status.error or 'Unknown error'
                    ]
                }

        except Exception as e:
            self.log_execution(
                ticket_id,
                'code_forge_execution_failed',
                level='warning',
                error=str(e)
            )
            return None

    async def execute(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executar tarefa EXECUTE com seleção de runtime.

        Args:
            ticket: Ticket de execução com parâmetros

        Returns:
            Resultado da execução
        """
        self.validate_ticket(ticket)

        ticket_id = ticket.get('ticket_id')
        parameters = ticket.get('parameters', {})

        tracer = get_tracer()
        with tracer.start_as_current_span('task_execution') as span:
            span.set_attribute('neural.hive.task_id', ticket_id)
            span.set_attribute('neural.hive.task_type', self.get_task_type())
            span.set_attribute('neural.hive.executor', self.__class__.__name__)

            self.log_execution(
                ticket_id,
                'execution_started',
                parameters=parameters
            )

            # Tentar Code Forge primeiro se template fornecido
            code_forge_start = time.monotonic()
            code_forge_result = await self._execute_code_forge(ticket_id, parameters, span)
            if code_forge_result:
                code_forge_elapsed = time.monotonic() - code_forge_start
                # Registrar métrica de duração para code_forge
                if self.metrics and hasattr(self.metrics, 'execute_duration_seconds'):
                    self.metrics.execute_duration_seconds.labels(runtime='code_forge').observe(code_forge_elapsed)
                if self.metrics and hasattr(self.metrics, 'execute_tasks_executed_total'):
                    status = 'success' if code_forge_result['success'] else 'failed'
                    self.metrics.execute_tasks_executed_total.labels(status=status).inc()
                span.set_attribute('neural.hive.execution_status', 'success' if code_forge_result['success'] else 'failed')
                return code_forge_result

            # Selecionar runtime
            requested_runtime = parameters.get('runtime')
            selected_runtime = self._select_runtime(requested_runtime)

            self.log_execution(
                ticket_id,
                'runtime_selected',
                requested=requested_runtime,
                selected=selected_runtime,
                available=self._get_available_runtimes()
            )

            # Registrar fallback se diferente do solicitado
            if requested_runtime and requested_runtime != selected_runtime:
                if self.metrics and hasattr(self.metrics, 'execute_runtime_fallbacks_total'):
                    self.metrics.execute_runtime_fallbacks_total.labels(
                        from_runtime=requested_runtime,
                        to_runtime=selected_runtime
                    ).inc()

            # Executar no runtime selecionado
            try:
                start_time = time.monotonic()
                if selected_runtime == 'k8s':
                    result = await self._execute_k8s(ticket_id, parameters, span)
                elif selected_runtime == 'docker':
                    result = await self._execute_docker(ticket_id, parameters, span)
                elif selected_runtime == 'lambda':
                    result = await self._execute_lambda(ticket_id, parameters, span)
                elif selected_runtime == 'local':
                    result = await self._execute_local(ticket_id, parameters, span)
                else:
                    result = await self._execute_simulation(ticket_id, parameters, span)
                elapsed_seconds = time.monotonic() - start_time

                # Registrar métrica de duração
                if self.metrics and hasattr(self.metrics, 'execute_duration_seconds'):
                    self.metrics.execute_duration_seconds.labels(runtime=selected_runtime).observe(elapsed_seconds)

                # Registrar métricas de sucesso
                if self.metrics and hasattr(self.metrics, 'execute_tasks_executed_total'):
                    status = 'success' if result.get('success') else 'failed'
                    self.metrics.execute_tasks_executed_total.labels(status=status).inc()

                span.set_attribute('neural.hive.execution_status', 'success' if result.get('success') else 'failed')
                return result

            except Exception as e:
                self.log_execution(
                    ticket_id,
                    'execution_failed',
                    level='error',
                    runtime=selected_runtime,
                    error=str(e)
                )

                # Tentar fallback para próximo runtime
                fallback_chain = getattr(self.config, 'runtime_fallback_chain', ['k8s', 'docker', 'local', 'simulation'])
                current_index = fallback_chain.index(selected_runtime) if selected_runtime in fallback_chain else -1

                for next_runtime in fallback_chain[current_index + 1:]:
                    if next_runtime in self._get_available_runtimes():
                        self.log_execution(
                            ticket_id,
                            'fallback_to_runtime',
                            from_runtime=selected_runtime,
                            to_runtime=next_runtime,
                            reason=str(e)
                        )

                        if self.metrics and hasattr(self.metrics, 'execute_runtime_fallbacks_total'):
                            self.metrics.execute_runtime_fallbacks_total.labels(
                                from_runtime=selected_runtime,
                                to_runtime=next_runtime
                            ).inc()

                        try:
                            fallback_start = time.monotonic()
                            if next_runtime == 'docker':
                                fallback_result = await self._execute_docker(ticket_id, parameters, span)
                            elif next_runtime == 'local':
                                fallback_result = await self._execute_local(ticket_id, parameters, span)
                            elif next_runtime == 'simulation':
                                fallback_result = await self._execute_simulation(ticket_id, parameters, span)
                            else:
                                continue
                            fallback_elapsed = time.monotonic() - fallback_start

                            # Registrar métrica de duração para fallback
                            if self.metrics and hasattr(self.metrics, 'execute_duration_seconds'):
                                self.metrics.execute_duration_seconds.labels(runtime=next_runtime).observe(fallback_elapsed)

                            return fallback_result
                        except Exception:
                            continue

                # Fallback final para simulação
                if self.metrics and hasattr(self.metrics, 'execute_tasks_executed_total'):
                    self.metrics.execute_tasks_executed_total.labels(status='failed').inc()

                final_start = time.monotonic()
                final_result = await self._execute_simulation(ticket_id, parameters, span)
                final_elapsed = time.monotonic() - final_start

                # Registrar métrica de duração para fallback final
                if self.metrics and hasattr(self.metrics, 'execute_duration_seconds'):
                    self.metrics.execute_duration_seconds.labels(runtime='simulation').observe(final_elapsed)

                return final_result
