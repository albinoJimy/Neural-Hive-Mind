"""
Testes unitários para DockerRuntimeClient.

Cobertura:
- Inicialização do cliente
- Pull de imagens
- Execução de comandos em containers
- Resource limits
- Timeout de execução
- Cleanup de containers
- Tratamento de erros
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def docker_client():
    """Fixture para DockerRuntimeClient."""
    from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeClient
    return DockerRuntimeClient(
        base_url='unix:///var/run/docker.sock',
        timeout=60,
        verify_ssl=True,
        default_cpu_limit=1.0,
        default_memory_limit='512m',
        cleanup_containers=True,
    )


@pytest.fixture
def execution_request():
    """Fixture para DockerExecutionRequest."""
    from services.worker_agents.src.clients.docker_runtime_client import (
        DockerExecutionRequest,
        ResourceLimits,
    )
    return DockerExecutionRequest(
        image='python:3.11-slim',
        command=['python', '-c', 'print("hello")'],
        timeout_seconds=30,
        resource_limits=ResourceLimits(
            cpu_limit=0.5,
            memory_limit='256m',
        ),
    )


class TestDockerClientInit:
    """Testes de inicialização do cliente."""

    def test_init_with_defaults(self):
        """Deve inicializar com valores padrão."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeClient
        client = DockerRuntimeClient()
        assert client.base_url == 'unix:///var/run/docker.sock'
        assert client.timeout == 600
        assert client.cleanup_containers is True

    def test_init_with_custom_url(self):
        """Deve inicializar com URL customizada."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeClient
        client = DockerRuntimeClient(base_url='tcp://localhost:2375')
        assert client.base_url == 'tcp://localhost:2375'

    def test_init_with_custom_limits(self):
        """Deve inicializar com limites customizados."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeClient
        client = DockerRuntimeClient(
            default_cpu_limit=2.0,
            default_memory_limit='1g',
        )
        assert client.default_cpu_limit == 2.0
        assert client.default_memory_limit == '1g'


class TestMemoryParsing:
    """Testes de parsing de memória."""

    def test_parse_memory_bytes(self, docker_client):
        """Deve parsear bytes."""
        assert docker_client._parse_memory_limit('1024b') == 1024
        assert docker_client._parse_memory_limit('1024') == 1024

    def test_parse_memory_kilobytes(self, docker_client):
        """Deve parsear kilobytes."""
        assert docker_client._parse_memory_limit('1k') == 1024
        assert docker_client._parse_memory_limit('1kb') == 1024

    def test_parse_memory_megabytes(self, docker_client):
        """Deve parsear megabytes."""
        assert docker_client._parse_memory_limit('1m') == 1024 * 1024
        assert docker_client._parse_memory_limit('512m') == 512 * 1024 * 1024
        assert docker_client._parse_memory_limit('512mb') == 512 * 1024 * 1024

    def test_parse_memory_gigabytes(self, docker_client):
        """Deve parsear gigabytes."""
        assert docker_client._parse_memory_limit('1g') == 1024 * 1024 * 1024
        assert docker_client._parse_memory_limit('2gb') == 2 * 1024 * 1024 * 1024


class TestDockerInitialization:
    """Testes de inicialização da conexão Docker."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, docker_client):
        """Deve inicializar conexão com sucesso."""
        mock_docker = MagicMock()
        mock_docker.version = AsyncMock(return_value={'Version': '24.0.0'})

        with patch('aiodocker.Docker', return_value=mock_docker):
            await docker_client.initialize()

            assert docker_client._initialized is True
            mock_docker.version.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_import_error(self, docker_client):
        """Deve tratar erro de import."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeError

        with patch.dict('sys.modules', {'aiodocker': None}):
            with patch('builtins.__import__', side_effect=ImportError('No module')):
                with pytest.raises(DockerRuntimeError) as exc_info:
                    await docker_client.initialize()

                assert 'aiodocker' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_initialize_connection_error(self, docker_client):
        """Deve tratar erro de conexão."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeError

        with patch('aiodocker.Docker', side_effect=Exception('Connection refused')):
            with pytest.raises(DockerRuntimeError) as exc_info:
                await docker_client.initialize()

                assert 'Falha ao conectar' in str(exc_info.value)


class TestImagePull:
    """Testes de pull de imagens."""

    @pytest.mark.asyncio
    async def test_pull_image_already_exists(self, docker_client):
        """Deve retornar False se imagem já existe."""
        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc123'})

        mock_docker = MagicMock()
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        result = await docker_client._pull_image('python:3.11-slim')

        assert result is False
        mock_images.inspect.assert_called_once_with('python:3.11-slim')

    @pytest.mark.asyncio
    async def test_pull_image_not_exists(self, docker_client):
        """Deve fazer pull se imagem não existe."""
        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(side_effect=Exception('Not found'))
        mock_images.pull = AsyncMock()

        mock_docker = MagicMock()
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        result = await docker_client._pull_image('python:3.11-slim')

        assert result is True
        mock_images.pull.assert_called_once_with('python:3.11-slim')


class TestCommandExecution:
    """Testes de execução de comandos."""

    @pytest.mark.asyncio
    async def test_execute_success(self, docker_client, execution_request):
        """Deve executar comando com sucesso."""
        mock_container = MagicMock()
        mock_container.id = 'abc123def456'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(return_value={'StatusCode': 0})
        mock_container.log = AsyncMock(side_effect=[['hello\n'], []])
        mock_container.stats = AsyncMock(return_value={})
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        result = await docker_client.execute_command(execution_request)

        assert result.exit_code == 0
        assert 'hello' in result.stdout
        assert result.container_id == 'abc123def456'[:12]
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_execute_with_env_vars(self, docker_client):
        """Deve passar variáveis de ambiente."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerExecutionRequest

        request = DockerExecutionRequest(
            image='python:3.11-slim',
            command=['python', '-c', 'import os; print(os.environ.get("TEST_VAR"))'],
            env_vars={'TEST_VAR': 'test_value'},
            timeout_seconds=30,
        )

        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(return_value={'StatusCode': 0})
        mock_container.log = AsyncMock(side_effect=[['test_value\n'], []])
        mock_container.stats = AsyncMock(return_value={})
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        await docker_client.execute_command(request)

        # Verificar que env vars foram passadas na configuração
        create_call = mock_containers.create.call_args
        config = create_call[0][0]
        assert 'TEST_VAR=test_value' in config['Env']

    @pytest.mark.asyncio
    async def test_execute_nonzero_exit(self, docker_client, execution_request):
        """Deve capturar exit code diferente de zero."""
        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(return_value={'StatusCode': 1})
        mock_container.log = AsyncMock(side_effect=[[''], ['Error: something failed\n']])
        mock_container.stats = AsyncMock(return_value={})
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        result = await docker_client.execute_command(execution_request)

        assert result.exit_code == 1
        assert 'Error' in result.stderr


class TestExecutionTimeout:
    """Testes de timeout de execução."""

    @pytest.mark.asyncio
    async def test_execute_timeout(self, docker_client):
        """Deve levantar timeout quando container demora demais."""
        from services.worker_agents.src.clients.docker_runtime_client import (
            DockerExecutionRequest,
            DockerTimeoutError,
        )

        request = DockerExecutionRequest(
            image='python:3.11-slim',
            command=['sleep', '100'],
            timeout_seconds=1,
        )

        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_container.stop = AsyncMock()
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        with pytest.raises(DockerTimeoutError):
            await docker_client.execute_command(request)


class TestContainerCleanup:
    """Testes de cleanup de containers."""

    @pytest.mark.asyncio
    async def test_cleanup_on_success(self, docker_client, execution_request):
        """Deve remover container após execução bem-sucedida."""
        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(return_value={'StatusCode': 0})
        mock_container.log = AsyncMock(side_effect=[['output\n'], []])
        mock_container.stats = AsyncMock(return_value={})
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        await docker_client.execute_command(execution_request)

        mock_container.delete.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_cleanup_on_failure(self, docker_client, execution_request):
        """Deve remover container mesmo após falha."""
        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(side_effect=Exception('Container failed'))
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeError

        with pytest.raises(DockerRuntimeError):
            await docker_client.execute_command(execution_request)

        mock_container.delete.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_no_cleanup_when_disabled(self, execution_request):
        """Não deve remover container quando cleanup desabilitado."""
        from services.worker_agents.src.clients.docker_runtime_client import DockerRuntimeClient

        client = DockerRuntimeClient(cleanup_containers=False)

        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(return_value={'StatusCode': 0})
        mock_container.log = AsyncMock(side_effect=[['output\n'], []])
        mock_container.stats = AsyncMock(return_value={})
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        client._docker = mock_docker
        client._initialized = True

        await client.execute_command(execution_request)

        mock_container.delete.assert_not_called()


class TestHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, docker_client):
        """Deve retornar True quando Docker daemon está acessível."""
        mock_docker = MagicMock()
        mock_docker.version = AsyncMock(return_value={'Version': '24.0.0'})

        docker_client._docker = mock_docker

        result = await docker_client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, docker_client):
        """Deve retornar False quando Docker daemon não está acessível."""
        mock_docker = MagicMock()
        mock_docker.version = AsyncMock(side_effect=Exception('Connection refused'))

        docker_client._docker = mock_docker

        result = await docker_client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, docker_client):
        """Deve retornar False quando cliente não inicializado."""
        docker_client._docker = None

        result = await docker_client.health_check()

        assert result is False


class TestMetricsRecording:
    """Testes de registro de métricas."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(self, docker_client, execution_request):
        """Deve registrar métricas em execução bem-sucedida."""
        mock_metrics = MagicMock()
        mock_metrics.docker_executions_total = MagicMock()
        mock_metrics.docker_executions_total.labels = MagicMock(return_value=MagicMock())
        mock_metrics.docker_execution_duration_seconds = MagicMock()
        mock_metrics.docker_execution_duration_seconds.labels = MagicMock(return_value=MagicMock())

        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.start = AsyncMock()
        mock_container.wait = AsyncMock(return_value={'StatusCode': 0})
        mock_container.log = AsyncMock(side_effect=[['output\n'], []])
        mock_container.stats = AsyncMock(return_value={})
        mock_container.delete = AsyncMock()

        mock_containers = MagicMock()
        mock_containers.create = AsyncMock(return_value=mock_container)

        mock_images = MagicMock()
        mock_images.inspect = AsyncMock(return_value={'Id': 'sha256:abc'})

        mock_docker = MagicMock()
        mock_docker.containers = mock_containers
        mock_docker.images = mock_images

        docker_client._docker = mock_docker
        docker_client._initialized = True

        await docker_client.execute_command(execution_request, metrics=mock_metrics)

        mock_metrics.docker_executions_total.labels.assert_called_with(status='success')


class TestClientClose:
    """Testes de fechamento do cliente."""

    @pytest.mark.asyncio
    async def test_close_client(self, docker_client):
        """Deve fechar cliente Docker."""
        mock_docker = MagicMock()
        mock_docker.close = AsyncMock()

        docker_client._docker = mock_docker
        docker_client._initialized = True

        await docker_client.close()

        mock_docker.close.assert_called_once()
        assert docker_client._initialized is False
