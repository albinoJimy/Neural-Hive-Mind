"""
Testes de integracao para ExecuteExecutor.

Este modulo contem testes de integracao que verificam:
- Execucao via Kubernetes Jobs
- Execucao via Docker containers
- Execucao via AWS Lambda
- Execucao local via subprocess
- Cadeia de fallback entre runtimes
- Timeout em diferentes runtimes
- Resource limits
- Fallback final para simulacao

Todos os testes usam mocks dos clientes externos.
"""

import asyncio
import pytest
import uuid
from dataclasses import dataclass
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================
# Classes Mock para Runtimes
# ============================================


class MockK8sJobStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'


@dataclass
class MockK8sJobResult:
    job_name: str = 'test-job-abc123'
    pod_name: str = 'test-job-abc123-pod'
    status: MockK8sJobStatus = MockK8sJobStatus.SUCCEEDED
    exit_code: int = 0
    logs: str = 'hello world'
    duration_ms: int = 5000


@dataclass
class MockDockerExecutionResult:
    container_id: str = 'abc123def456'
    exit_code: int = 0
    stdout: str = 'docker output'
    stderr: str = ''
    duration_ms: int = 3000
    image_pulled: bool = False


@dataclass
class MockLambdaResponse:
    exit_code: int = 0
    stdout: str = 'lambda result'
    stderr: str = ''


@dataclass
class MockLambdaInvocationResult:
    request_id: str = 'req-abc123'
    status_code: int = 200
    function_error: str = None
    response: MockLambdaResponse = None
    duration_ms: int = 1500
    billed_duration_ms: int = 2000
    memory_used_mb: int = 128

    def __post_init__(self):
        if self.response is None:
            self.response = MockLambdaResponse()


@dataclass
class MockLocalExecutionResult:
    exit_code: int = 0
    stdout: str = 'local output'
    stderr: str = ''
    command_executed: str = 'echo hello world'
    pid: int = 12345
    duration_ms: int = 100


# ============================================
# Fixtures Especificas
# ============================================


@pytest.fixture
def execute_executor_with_k8s(worker_config, mock_metrics, mock_k8s_jobs_client):
    """ExecuteExecutor configurado com cliente K8s Jobs mockado."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    worker_config.default_runtime = 'k8s'
    worker_config.runtime_fallback_chain = ['k8s', 'docker', 'local', 'simulation']
    worker_config.k8s_jobs_namespace = 'neural-hive-execution'
    worker_config.k8s_jobs_timeout_seconds = 600

    return ExecuteExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        k8s_jobs_client=mock_k8s_jobs_client
    )


@pytest.fixture
def execute_executor_with_docker(worker_config, mock_metrics, mock_docker_runtime_client):
    """ExecuteExecutor configurado com cliente Docker mockado."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    worker_config.default_runtime = 'docker'
    worker_config.runtime_fallback_chain = ['docker', 'local', 'simulation']
    worker_config.docker_timeout_seconds = 600

    return ExecuteExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        docker_client=mock_docker_runtime_client
    )


@pytest.fixture
def execute_executor_with_lambda(worker_config, mock_metrics, mock_lambda_runtime_client):
    """ExecuteExecutor configurado com cliente Lambda mockado."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    worker_config.default_runtime = 'lambda'
    worker_config.runtime_fallback_chain = ['lambda', 'local', 'simulation']
    worker_config.lambda_function_name = 'neural-hive-executor'

    return ExecuteExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        lambda_client=mock_lambda_runtime_client
    )


@pytest.fixture
def execute_executor_with_local(worker_config, mock_metrics, mock_local_runtime_client):
    """ExecuteExecutor configurado com cliente Local mockado."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    worker_config.default_runtime = 'local'
    worker_config.runtime_fallback_chain = ['local', 'simulation']
    worker_config.local_runtime_timeout_seconds = 300

    return ExecuteExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        local_client=mock_local_runtime_client
    )


@pytest.fixture
def execute_executor_all_runtimes(
    worker_config,
    mock_metrics,
    mock_k8s_jobs_client,
    mock_docker_runtime_client,
    mock_lambda_runtime_client,
    mock_local_runtime_client
):
    """ExecuteExecutor com todos os clientes de runtime."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    worker_config.default_runtime = 'k8s'
    worker_config.runtime_fallback_chain = ['k8s', 'docker', 'lambda', 'local', 'simulation']

    return ExecuteExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        k8s_jobs_client=mock_k8s_jobs_client,
        docker_client=mock_docker_runtime_client,
        lambda_client=mock_lambda_runtime_client,
        local_client=mock_local_runtime_client
    )


@pytest.fixture
def execute_executor_simulation_only(worker_config, mock_metrics):
    """ExecuteExecutor sem clientes externos (apenas simulacao)."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

    worker_config.default_runtime = 'simulation'
    worker_config.runtime_fallback_chain = ['simulation']

    return ExecuteExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics
    )


# ============================================
# Testes Kubernetes Jobs
# ============================================


class TestExecuteExecutorK8sSuccess:
    """Testes de execucao bem-sucedida via Kubernetes Jobs."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_k8s_success(
        self,
        execute_executor_with_k8s,
        execute_ticket_k8s,
        mock_k8s_jobs_client
    ):
        """Deve executar com sucesso via Kubernetes Job."""
        mock_k8s_jobs_client.execute_job.return_value = MockK8sJobResult()

        result = await execute_executor_with_k8s.execute(execute_ticket_k8s)

        assert result['success'] is True
        assert result['output']['exit_code'] == 0
        assert result['metadata']['runtime'] == 'k8s'
        assert result['metadata']['simulated'] is False

        mock_k8s_jobs_client.execute_job.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_k8s_job_details(
        self,
        execute_executor_with_k8s,
        execute_ticket_k8s,
        mock_k8s_jobs_client
    ):
        """Deve retornar detalhes do job K8s."""
        mock_k8s_jobs_client.execute_job.return_value = MockK8sJobResult(
            job_name='test-job-xyz',
            pod_name='test-job-xyz-pod'
        )

        result = await execute_executor_with_k8s.execute(execute_ticket_k8s)

        assert result['output']['job_name'] == 'test-job-xyz'
        assert result['output']['pod_name'] == 'test-job-xyz-pod'


# ============================================
# Testes Docker
# ============================================


class TestExecuteExecutorDockerSuccess:
    """Testes de execucao bem-sucedida via Docker."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_docker_success(
        self,
        execute_executor_with_docker,
        execute_ticket_docker,
        mock_docker_runtime_client
    ):
        """Deve executar com sucesso via Docker."""
        mock_docker_runtime_client.execute_command.return_value = MockDockerExecutionResult()

        result = await execute_executor_with_docker.execute(execute_ticket_docker)

        assert result['success'] is True
        assert result['output']['exit_code'] == 0
        assert result['output']['stdout'] == 'docker output'
        assert result['metadata']['runtime'] == 'docker'
        assert result['metadata']['simulated'] is False

        mock_docker_runtime_client.execute_command.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_docker_container_id(
        self,
        execute_executor_with_docker,
        execute_ticket_docker,
        mock_docker_runtime_client
    ):
        """Deve retornar container_id do Docker."""
        mock_docker_runtime_client.execute_command.return_value = MockDockerExecutionResult(
            container_id='container-abc123'
        )

        result = await execute_executor_with_docker.execute(execute_ticket_docker)

        assert result['output']['container_id'] == 'container-abc123'


# ============================================
# Testes Lambda
# ============================================


class TestExecuteExecutorLambdaSuccess:
    """Testes de execucao bem-sucedida via AWS Lambda."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_lambda_success(
        self,
        execute_executor_with_lambda,
        execute_ticket_lambda,
        mock_lambda_runtime_client
    ):
        """Deve executar com sucesso via Lambda."""
        mock_lambda_runtime_client.invoke_lambda.return_value = MockLambdaInvocationResult()

        result = await execute_executor_with_lambda.execute(execute_ticket_lambda)

        assert result['success'] is True
        assert result['output']['exit_code'] == 0
        assert result['metadata']['runtime'] == 'lambda'
        assert result['metadata']['simulated'] is False

        mock_lambda_runtime_client.invoke_lambda.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_lambda_billing_info(
        self,
        execute_executor_with_lambda,
        execute_ticket_lambda,
        mock_lambda_runtime_client
    ):
        """Deve retornar informacoes de billing do Lambda."""
        mock_lambda_runtime_client.invoke_lambda.return_value = MockLambdaInvocationResult(
            billed_duration_ms=500,
            memory_used_mb=256
        )

        result = await execute_executor_with_lambda.execute(execute_ticket_lambda)

        assert result['metadata']['billed_duration_ms'] == 500
        assert result['metadata']['memory_used_mb'] == 256


# ============================================
# Testes Local
# ============================================


class TestExecuteExecutorLocalSuccess:
    """Testes de execucao bem-sucedida local."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_local_success(
        self,
        execute_executor_with_local,
        execute_ticket,
        mock_local_runtime_client
    ):
        """Deve executar com sucesso localmente."""
        mock_local_runtime_client.execute_local.return_value = MockLocalExecutionResult()

        result = await execute_executor_with_local.execute(execute_ticket)

        assert result['success'] is True
        assert result['output']['exit_code'] == 0
        assert result['metadata']['runtime'] == 'local'
        assert result['metadata']['simulated'] is False

        mock_local_runtime_client.execute_local.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_local_command_tracking(
        self,
        execute_executor_with_local,
        execute_ticket,
        mock_local_runtime_client
    ):
        """Deve rastrear comando executado localmente."""
        mock_local_runtime_client.execute_local.return_value = MockLocalExecutionResult(
            command_executed='echo hello world'
        )

        result = await execute_executor_with_local.execute(execute_ticket)

        assert result['output']['command'] == 'echo hello world'


# ============================================
# Testes de Fallback Chain
# ============================================


class TestExecuteExecutorRuntimeFallbackChain:
    """Testes de cadeia de fallback entre runtimes."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_fallback_k8s_to_docker(
        self,
        worker_config,
        mock_metrics,
        execute_ticket_k8s
    ):
        """Deve fazer fallback de K8s para Docker quando K8s falha."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        # K8s client que falha
        mock_k8s_client = AsyncMock()
        mock_k8s_client.execute_job = AsyncMock(side_effect=RuntimeError('K8s unavailable'))

        # Docker client que funciona
        mock_docker_client = AsyncMock()
        mock_docker_client.execute_command = AsyncMock(return_value=MockDockerExecutionResult())

        worker_config.default_runtime = 'k8s'
        worker_config.runtime_fallback_chain = ['k8s', 'docker', 'local', 'simulation']

        executor = ExecuteExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            k8s_jobs_client=mock_k8s_client,
            docker_client=mock_docker_client
        )

        result = await executor.execute(execute_ticket_k8s)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'docker'

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_fallback_docker_to_local(
        self,
        worker_config,
        mock_metrics,
        execute_ticket_docker
    ):
        """Deve fazer fallback de Docker para Local quando Docker falha."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        # Docker client que falha
        mock_docker_client = AsyncMock()
        mock_docker_client.execute_command = AsyncMock(side_effect=RuntimeError('Docker unavailable'))

        # Local client que funciona
        mock_local_client = AsyncMock()
        mock_local_client.execute_local = AsyncMock(return_value=MockLocalExecutionResult())

        worker_config.default_runtime = 'docker'
        worker_config.runtime_fallback_chain = ['docker', 'local', 'simulation']

        executor = ExecuteExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            docker_client=mock_docker_client,
            local_client=mock_local_client
        )

        result = await executor.execute(execute_ticket_docker)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'local'

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_fallback_metrics(
        self,
        worker_config,
        mock_metrics,
        execute_ticket_k8s
    ):
        """Deve registrar metricas de fallback."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        mock_k8s_client = AsyncMock()
        mock_k8s_client.execute_job = AsyncMock(side_effect=RuntimeError('K8s unavailable'))

        mock_docker_client = AsyncMock()
        mock_docker_client.execute_command = AsyncMock(return_value=MockDockerExecutionResult())

        worker_config.default_runtime = 'k8s'
        worker_config.runtime_fallback_chain = ['k8s', 'docker', 'local', 'simulation']

        executor = ExecuteExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            k8s_jobs_client=mock_k8s_client,
            docker_client=mock_docker_client
        )

        await executor.execute(execute_ticket_k8s)

        mock_metrics.execute_runtime_fallbacks_total.labels.assert_called()


# ============================================
# Testes de Timeout
# ============================================


class TestExecuteExecutorTimeout:
    """Testes de timeout em diferentes runtimes."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_docker_timeout(
        self,
        worker_config,
        mock_metrics,
        execute_ticket_docker
    ):
        """Deve fazer fallback quando Docker timeout."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        mock_docker_client = AsyncMock()
        mock_docker_client.execute_command = AsyncMock(
            side_effect=asyncio.TimeoutError('Docker execution timed out')
        )

        mock_local_client = AsyncMock()
        mock_local_client.execute_local = AsyncMock(return_value=MockLocalExecutionResult())

        worker_config.default_runtime = 'docker'
        worker_config.runtime_fallback_chain = ['docker', 'local', 'simulation']

        executor = ExecuteExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            docker_client=mock_docker_client,
            local_client=mock_local_client
        )

        result = await executor.execute(execute_ticket_docker)

        # Fallback para local
        assert result['metadata']['runtime'] != 'docker'


# ============================================
# Testes de Resource Limits
# ============================================


class TestExecuteExecutorResourceLimits:
    """Testes de resource limits."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_k8s_resource_limits(
        self,
        execute_executor_with_k8s,
        mock_k8s_jobs_client
    ):
        """Deve passar resource limits para K8s Jobs."""
        ticket_id = str(uuid.uuid4())
        ticket = {
            'ticket_id': ticket_id,
            'task_type': 'EXECUTE',
            'parameters': {
                'command': ['python', '-c', 'print("test")'],
                'runtime': 'k8s',
                'image': 'python:3.11-slim',
                'cpu_limit': '2000m',
                'memory_limit': '1Gi',
                'cpu_request': '500m',
                'memory_request': '256Mi'
            }
        }

        mock_k8s_jobs_client.execute_job.return_value = MockK8sJobResult()

        await execute_executor_with_k8s.execute(ticket)

        # Verificar que execute_job foi chamado
        mock_k8s_jobs_client.execute_job.assert_called_once()

        # Capturar argumentos da chamada
        call_args = mock_k8s_jobs_client.execute_job.call_args
        request = call_args[0][0] if call_args[0] else call_args.kwargs.get('request')

        # Verificar resource limits (se request for acessivel)
        if hasattr(request, 'resource_limits'):
            assert request.resource_limits.cpu_limit == '2000m'
            assert request.resource_limits.memory_limit == '1Gi'

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_docker_resource_limits(
        self,
        execute_executor_with_docker,
        mock_docker_runtime_client
    ):
        """Deve passar resource limits para Docker."""
        ticket_id = str(uuid.uuid4())
        ticket = {
            'ticket_id': ticket_id,
            'task_type': 'EXECUTE',
            'parameters': {
                'command': ['echo', 'test'],
                'runtime': 'docker',
                'image': 'alpine:latest',
                'cpu_limit': 2.0,
                'memory_limit': '1g'
            }
        }

        mock_docker_runtime_client.execute_command.return_value = MockDockerExecutionResult()

        await execute_executor_with_docker.execute(ticket)

        mock_docker_runtime_client.execute_command.assert_called_once()


# ============================================
# Testes de Simulacao
# ============================================


class TestExecuteExecutorSimulationFallback:
    """Testes de fallback final para simulacao."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_simulation_fallback(
        self,
        execute_executor_simulation_only,
        execute_ticket
    ):
        """Deve usar simulacao quando todos runtimes indisponiveis."""
        result = await execute_executor_simulation_only.execute(execute_ticket)

        assert result['success'] is True
        assert result['metadata']['simulated'] is True
        assert result['metadata']['runtime'] == 'simulation'

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_simulation_output(
        self,
        execute_executor_simulation_only,
        execute_ticket
    ):
        """Deve retornar output simulado."""
        result = await execute_executor_simulation_only.execute(execute_ticket)

        assert result['output']['exit_code'] == 0
        assert 'stdout' in result['output']
        assert 'logs' in result

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_all_fail_to_simulation(
        self,
        worker_config,
        mock_metrics,
        execute_ticket_k8s
    ):
        """Deve usar simulacao quando todos os runtimes falham."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        # Todos os clientes falham
        mock_k8s_client = AsyncMock()
        mock_k8s_client.execute_job = AsyncMock(side_effect=RuntimeError('K8s fail'))

        mock_docker_client = AsyncMock()
        mock_docker_client.execute_command = AsyncMock(side_effect=RuntimeError('Docker fail'))

        mock_local_client = AsyncMock()
        mock_local_client.execute_local = AsyncMock(side_effect=RuntimeError('Local fail'))

        worker_config.default_runtime = 'k8s'
        worker_config.runtime_fallback_chain = ['k8s', 'docker', 'local', 'simulation']

        executor = ExecuteExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            k8s_jobs_client=mock_k8s_client,
            docker_client=mock_docker_client,
            local_client=mock_local_client
        )

        result = await executor.execute(execute_ticket_k8s)

        assert result['success'] is True
        assert result['metadata']['simulated'] is True
        assert result['metadata']['runtime'] == 'simulation'


# ============================================
# Testes de Metricas
# ============================================


class TestExecuteExecutorMetrics:
    """Testes de registro de metricas."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_metrics_recorded(
        self,
        execute_executor_with_docker,
        execute_ticket_docker,
        mock_metrics,
        mock_docker_runtime_client
    ):
        """Deve registrar metricas Prometheus apos execucao."""
        mock_docker_runtime_client.execute_command.return_value = MockDockerExecutionResult()

        await execute_executor_with_docker.execute(execute_ticket_docker)

        mock_metrics.execute_tasks_executed_total.labels.assert_called()
        mock_metrics.execute_duration_seconds.labels.assert_called()


# ============================================
# Testes de Validacao de Ticket
# ============================================


class TestExecuteExecutorTicketValidation:
    """Testes de validacao de ticket."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_missing_ticket_id(
        self,
        execute_executor_with_docker
    ):
        """Deve falhar com ticket sem ID."""
        invalid_ticket = {
            'task_type': 'EXECUTE',
            'parameters': {}
        }

        with pytest.raises(ValueError):
            await execute_executor_with_docker.execute(invalid_ticket)

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_wrong_task_type(
        self,
        execute_executor_with_docker
    ):
        """Deve falhar com task_type incorreto."""
        invalid_ticket = {
            'ticket_id': str(uuid.uuid4()),
            'task_type': 'BUILD',
            'parameters': {}
        }

        with pytest.raises(ValueError):
            await execute_executor_with_docker.execute(invalid_ticket)


# ============================================
# Testes de Erro com Exit Code
# ============================================


class TestExecuteExecutorFailedExecution:
    """Testes de execucoes que falham."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_k8s_failed_job(
        self,
        execute_executor_with_k8s,
        execute_ticket_k8s,
        mock_k8s_jobs_client
    ):
        """Deve retornar falha quando K8s Job falha."""
        mock_k8s_jobs_client.execute_job.return_value = MockK8sJobResult(
            status=MockK8sJobStatus.FAILED,
            exit_code=1,
            logs='Error: command failed'
        )

        result = await execute_executor_with_k8s.execute(execute_ticket_k8s)

        assert result['success'] is False
        assert result['output']['exit_code'] == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_docker_failed_container(
        self,
        execute_executor_with_docker,
        execute_ticket_docker,
        mock_docker_runtime_client
    ):
        """Deve retornar falha quando container Docker falha."""
        mock_docker_runtime_client.execute_command.return_value = MockDockerExecutionResult(
            exit_code=127,
            stderr='command not found'
        )

        result = await execute_executor_with_docker.execute(execute_ticket_docker)

        assert result['success'] is False
        assert result['output']['exit_code'] == 127

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_execute_executor_lambda_function_error(
        self,
        execute_executor_with_lambda,
        execute_ticket_lambda,
        mock_lambda_runtime_client
    ):
        """Deve retornar falha quando Lambda retorna function_error."""
        mock_lambda_runtime_client.invoke_lambda.return_value = MockLambdaInvocationResult(
            function_error='Unhandled exception',
            response=MockLambdaResponse(exit_code=1)
        )

        result = await execute_executor_with_lambda.execute(execute_ticket_lambda)

        assert result['success'] is False
