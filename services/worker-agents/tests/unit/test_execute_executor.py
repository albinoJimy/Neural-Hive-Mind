"""
Testes unitários para ExecuteExecutor com suporte multi-runtime.

Cobertura:
- Seleção de runtime
- Execução via Docker
- Execução via K8s Jobs
- Execução via Lambda
- Execução local
- Fallback entre runtimes
- Execução via Code Forge
- Simulação
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_config():
    """Fixture para configurações."""
    config = MagicMock()
    config.default_runtime = 'local'
    config.runtime_fallback_chain = ['k8s', 'docker', 'local', 'simulation']
    config.docker_timeout_seconds = 600
    config.docker_default_cpu_limit = 1.0
    config.docker_default_memory_limit = '512m'
    config.docker_network_mode = 'bridge'
    config.k8s_jobs_namespace = 'neural-hive-execution'
    config.k8s_jobs_timeout_seconds = 600
    config.k8s_jobs_default_cpu_request = '100m'
    config.k8s_jobs_default_cpu_limit = '1000m'
    config.k8s_jobs_default_memory_request = '128Mi'
    config.k8s_jobs_default_memory_limit = '512Mi'
    config.k8s_jobs_service_account = 'worker-agent-executor'
    config.lambda_function_name = 'neural-hive-executor'
    config.local_runtime_timeout_seconds = 300
    return config


@pytest.fixture
def mock_local_client():
    """Fixture para LocalRuntimeClient mockado."""
    client = MagicMock()
    result = MagicMock()
    result.exit_code = 0
    result.stdout = 'test output'
    result.stderr = ''
    result.duration_ms = 100
    result.pid = 12345
    result.command_executed = 'echo test'
    client.execute_local = AsyncMock(return_value=result)
    return client


@pytest.fixture
def mock_docker_client():
    """Fixture para DockerRuntimeClient mockado."""
    client = MagicMock()
    result = MagicMock()
    result.exit_code = 0
    result.stdout = 'docker output'
    result.stderr = ''
    result.duration_ms = 200
    result.container_id = 'abc123'
    result.image_pulled = False
    client.execute_command = AsyncMock(return_value=result)
    return client


@pytest.fixture
def mock_k8s_client():
    """Fixture para KubernetesJobsClient mockado."""
    from services.worker_agents.src.clients.k8s_jobs_client import K8sJobStatus

    client = MagicMock()
    result = MagicMock()
    result.status = K8sJobStatus.SUCCEEDED
    result.exit_code = 0
    result.logs = 'k8s output'
    result.duration_ms = 300
    result.job_name = 'exec-abc123'
    result.pod_name = 'exec-abc123-pod'
    client.execute_job = AsyncMock(return_value=result)
    return client


@pytest.fixture
def mock_lambda_client():
    """Fixture para LambdaRuntimeClient mockado."""
    client = MagicMock()
    result = MagicMock()
    result.request_id = 'req-123'
    result.status_code = 200
    result.function_error = None
    result.duration_ms = 150
    result.billed_duration_ms = 200
    result.memory_used_mb = 128
    result.response = MagicMock()
    result.response.exit_code = 0
    result.response.stdout = 'lambda output'
    result.response.stderr = ''
    client.invoke_lambda = AsyncMock(return_value=result)
    return client


@pytest.fixture
def execute_executor(mock_config, mock_local_client):
    """Fixture para ExecuteExecutor com local client."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor
    return ExecuteExecutor(
        config=mock_config,
        local_client=mock_local_client,
    )


@pytest.fixture
def execute_executor_all_runtimes(mock_config, mock_local_client, mock_docker_client, mock_k8s_client, mock_lambda_client):
    """Fixture para ExecuteExecutor com todos os runtimes."""
    from services.worker_agents.src.executors.execute_executor import ExecuteExecutor
    return ExecuteExecutor(
        config=mock_config,
        local_client=mock_local_client,
        docker_client=mock_docker_client,
        k8s_jobs_client=mock_k8s_client,
        lambda_client=mock_lambda_client,
    )


class TestRuntimeSelection:
    """Testes de seleção de runtime."""

    def test_get_available_runtimes_local_only(self, execute_executor):
        """Deve listar apenas local e simulation."""
        available = execute_executor._get_available_runtimes()
        assert 'local' in available
        assert 'simulation' in available
        assert 'docker' not in available
        assert 'k8s' not in available

    def test_get_available_runtimes_all(self, execute_executor_all_runtimes):
        """Deve listar todos os runtimes disponíveis."""
        available = execute_executor_all_runtimes._get_available_runtimes()
        assert 'local' in available
        assert 'docker' in available
        assert 'k8s' in available
        assert 'lambda' in available
        assert 'simulation' in available

    def test_select_runtime_requested_available(self, execute_executor_all_runtimes):
        """Deve selecionar runtime solicitado se disponível."""
        selected = execute_executor_all_runtimes._select_runtime('docker')
        assert selected == 'docker'

    def test_select_runtime_requested_unavailable(self, execute_executor):
        """Deve usar fallback se runtime solicitado não disponível."""
        selected = execute_executor._select_runtime('docker')
        assert selected == 'local'  # Fallback para local

    def test_select_runtime_default(self, execute_executor):
        """Deve usar runtime padrão quando nenhum especificado."""
        selected = execute_executor._select_runtime(None)
        assert selected == 'local'

    def test_select_runtime_fallback_chain(self, mock_config, mock_docker_client):
        """Deve seguir cadeia de fallback."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        mock_config.default_runtime = 'k8s'  # K8s não disponível

        executor = ExecuteExecutor(
            config=mock_config,
            docker_client=mock_docker_client,
        )

        selected = executor._select_runtime(None)
        assert selected == 'docker'  # Primeiro disponível na cadeia


class TestLocalExecution:
    """Testes de execução local."""

    @pytest.mark.asyncio
    async def test_execute_local_success(self, execute_executor, mock_local_client):
        """Deve executar localmente com sucesso."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'echo',
                'args': ['hello'],
                'runtime': 'local',
            }
        }

        result = await execute_executor.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'local'
        assert result['metadata']['simulated'] is False
        mock_local_client.execute_local.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_local_with_env_vars(self, execute_executor, mock_local_client):
        """Deve passar variáveis de ambiente."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'printenv',
                'env_vars': {'TEST_VAR': 'test_value'},
                'runtime': 'local',
            }
        }

        await execute_executor.execute(ticket)

        call_args = mock_local_client.execute_local.call_args
        request = call_args[0][0]
        assert request.env_vars == {'TEST_VAR': 'test_value'}


class TestDockerExecution:
    """Testes de execução via Docker."""

    @pytest.mark.asyncio
    async def test_execute_docker_success(self, execute_executor_all_runtimes, mock_docker_client):
        """Deve executar via Docker com sucesso."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': ['python', '-c', 'print("hello")'],
                'image': 'python:3.11-slim',
                'runtime': 'docker',
            }
        }

        result = await execute_executor_all_runtimes.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'docker'
        assert 'container_id' in result['output']
        mock_docker_client.execute_command.assert_called_once()


class TestK8sExecution:
    """Testes de execução via Kubernetes Jobs."""

    @pytest.mark.asyncio
    async def test_execute_k8s_success(self, execute_executor_all_runtimes, mock_k8s_client):
        """Deve executar via K8s Jobs com sucesso."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'python',
                'args': ['-c', 'print("hello")'],
                'image': 'python:3.11-slim',
                'runtime': 'k8s',
            }
        }

        result = await execute_executor_all_runtimes.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'k8s'
        assert 'job_name' in result['output']
        mock_k8s_client.execute_job.assert_called_once()


class TestLambdaExecution:
    """Testes de execução via Lambda."""

    @pytest.mark.asyncio
    async def test_execute_lambda_success(self, execute_executor_all_runtimes, mock_lambda_client):
        """Deve executar via Lambda com sucesso."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'echo',
                'args': ['hello'],
                'runtime': 'lambda',
            }
        }

        result = await execute_executor_all_runtimes.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'lambda'
        assert 'request_id' in result['output']
        mock_lambda_client.invoke_lambda.assert_called_once()


class TestSimulationExecution:
    """Testes de execução simulada."""

    @pytest.mark.asyncio
    async def test_execute_simulation(self, mock_config):
        """Deve executar simulação quando nenhum runtime disponível."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        executor = ExecuteExecutor(config=mock_config)  # Sem clients

        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'echo',
                'args': ['hello'],
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'simulation'
        assert result['metadata']['simulated'] is True


class TestRuntimeFallback:
    """Testes de fallback entre runtimes."""

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, mock_config, mock_local_client, mock_docker_client):
        """Deve fazer fallback quando runtime falha."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        # Docker falha, deve fazer fallback para local
        mock_docker_client.execute_command = AsyncMock(side_effect=Exception('Docker failed'))

        executor = ExecuteExecutor(
            config=mock_config,
            docker_client=mock_docker_client,
            local_client=mock_local_client,
        )

        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'echo',
                'runtime': 'docker',
            }
        }

        result = await executor.execute(ticket)

        # Deve ter feito fallback para local
        assert result['success'] is True
        assert result['metadata']['runtime'] == 'local'
        mock_local_client.execute_local.assert_called_once()


class TestCodeForgeExecution:
    """Testes de execução via Code Forge."""

    @pytest.mark.asyncio
    async def test_execute_code_forge_success(self, mock_config, mock_local_client):
        """Deve executar via Code Forge quando template fornecido."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        mock_code_forge = MagicMock()
        mock_code_forge.submit_generation_request = AsyncMock(return_value='req-123')

        mock_status = MagicMock()
        mock_status.status = 'completed'
        mock_status.artifacts = ['artifact1.py', 'artifact2.py']
        mock_status.pipeline_id = 'pipeline-123'
        mock_code_forge.get_generation_status = AsyncMock(return_value=mock_status)

        executor = ExecuteExecutor(
            config=mock_config,
            code_forge_client=mock_code_forge,
            local_client=mock_local_client,
        )

        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'template_id': 'my-template',
                'params': {'key': 'value'},
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        assert result['metadata']['runtime'] == 'code_forge'
        assert len(result['output']['artifacts']) == 2
        mock_code_forge.submit_generation_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_forge_fallback_to_runtime(self, mock_config, mock_local_client):
        """Deve fazer fallback para runtime quando Code Forge falha."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        mock_code_forge = MagicMock()
        mock_code_forge.submit_generation_request = AsyncMock(side_effect=Exception('Code Forge failed'))

        executor = ExecuteExecutor(
            config=mock_config,
            code_forge_client=mock_code_forge,
            local_client=mock_local_client,
        )

        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'template_id': 'my-template',
                'command': 'echo',
                'args': ['fallback'],
            }
        }

        result = await executor.execute(ticket)

        # Deve ter feito fallback para local
        assert result['success'] is True
        assert result['metadata']['runtime'] == 'local'


class TestMetricsRecording:
    """Testes de registro de métricas."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(self, execute_executor, mock_local_client):
        """Deve registrar métricas em execução bem-sucedida."""
        mock_metrics = MagicMock()
        mock_metrics.execute_tasks_executed_total = MagicMock()
        mock_metrics.execute_tasks_executed_total.labels = MagicMock(return_value=MagicMock())

        execute_executor.metrics = mock_metrics

        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'echo',
                'runtime': 'local',
            }
        }

        await execute_executor.execute(ticket)

        mock_metrics.execute_tasks_executed_total.labels.assert_called_with(status='success')

    @pytest.mark.asyncio
    async def test_fallback_metrics_recorded(self, mock_config, mock_docker_client, mock_local_client):
        """Deve registrar métricas de fallback."""
        from services.worker_agents.src.executors.execute_executor import ExecuteExecutor

        mock_docker_client.execute_command = AsyncMock(side_effect=Exception('Docker failed'))

        mock_metrics = MagicMock()
        mock_metrics.execute_tasks_executed_total = MagicMock()
        mock_metrics.execute_tasks_executed_total.labels = MagicMock(return_value=MagicMock())
        mock_metrics.execute_runtime_fallbacks_total = MagicMock()
        mock_metrics.execute_runtime_fallbacks_total.labels = MagicMock(return_value=MagicMock())

        executor = ExecuteExecutor(
            config=mock_config,
            docker_client=mock_docker_client,
            local_client=mock_local_client,
            metrics=mock_metrics,
        )

        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'EXECUTE',
            'parameters': {
                'command': 'echo',
                'runtime': 'docker',
            }
        }

        await executor.execute(ticket)

        # Verificar que fallback foi registrado
        mock_metrics.execute_runtime_fallbacks_total.labels.assert_called()


class TestTaskType:
    """Testes de tipo de tarefa."""

    def test_get_task_type(self, execute_executor):
        """Deve retornar EXECUTE como tipo de tarefa."""
        assert execute_executor.get_task_type() == 'EXECUTE'
