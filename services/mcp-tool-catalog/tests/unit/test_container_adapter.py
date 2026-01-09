"""
Testes unitarios para ContainerAdapter.

Cobertura:
- Execucao de containers Docker (sucesso, erro, timeout)
- Construcao de comando docker run
- Environment variables e volumes
- Working directory
- Timeout e kill de containers orfaos
- Network mode
- Validacao de disponibilidade Docker
- Metricas
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestContainerAdapterExecution:
    """Testes de execucao de containers."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Deve executar container com sucesso."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter(timeout_seconds=600)

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'{"vulnerabilities": []}', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='trivy-001',
                tool_name='trivy',
                command='aquasec/trivy:latest',
                parameters={'args': ['image', 'nginx:latest']},
                context={'tool_id': 'trivy-001'}
            )

            assert result.success is True
            assert result.exit_code == 0
            assert '{"vulnerabilities": []}' in result.output

            # Validar chamada do subprocess
            mock_proc.assert_called_once()
            call_cmd = mock_proc.call_args[0][0]
            assert 'docker' in call_cmd
            assert 'run' in call_cmd
            assert 'aquasec/trivy:latest' in call_cmd

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """Deve retornar erro quando container falha."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b'Error: image not found'))
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='broken-001',
                tool_name='broken',
                command='nonexistent/image:latest',
                parameters={},
                context={'tool_id': 'broken-001'}
            )

            assert result.success is False
            assert result.exit_code == 1
            assert 'Error: image not found' in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout_kills_container(self):
        """Deve matar container quando ocorre timeout."""
        from src.adapters.container_adapter import ContainerAdapter
        from src.adapters.base_adapter import AdapterError

        adapter = ContainerAdapter(timeout_seconds=1)

        kill_called = False

        async def mock_communicate():
            raise asyncio.TimeoutError()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = mock_communicate
            mock_process.kill = MagicMock()
            mock_proc.return_value = mock_process

            # O adapter deve tentar matar o container orfao
            with pytest.raises(AdapterError) as exc_info:
                await adapter.execute(
                    tool_id='slow-container',
                    tool_name='slow',
                    command='slow/image:latest',
                    parameters={},
                    context={'tool_id': 'slow-container'}
                )

            assert 'timed out' in str(exc_info.value).lower()
            mock_process.kill.assert_called_once()


class TestContainerAdapterCommandBuilding:
    """Testes de construcao de comando docker run."""

    def test_build_docker_command_basic(self):
        """Deve construir comando docker run basico."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='aquasec/trivy:latest',
            parameters={},
            context={'tool_id': 'trivy-001'}
        )

        assert 'docker' in cmd
        assert 'run' in cmd
        assert '--rm' in cmd
        assert 'aquasec/trivy:latest' in cmd
        assert '--name' in cmd
        assert 'mcp-trivy-00' in cmd

    def test_build_docker_command_with_env_vars(self):
        """Deve incluir environment variables."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='myimage:latest',
            parameters={
                'env': {
                    'API_KEY': 'secret123',
                    'DEBUG': 'true'
                }
            },
            context={'tool_id': 'test-001'}
        )

        assert '-e' in cmd
        assert 'API_KEY=secret123' in cmd
        assert 'DEBUG=true' in cmd

    def test_build_docker_command_with_volumes(self):
        """Deve incluir volume mounts."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='scanner:latest',
            parameters={
                'volumes': [
                    '/host/path:/container/path',
                    '/data:/data:ro'
                ]
            },
            context={'tool_id': 'scanner-001'}
        )

        assert '-v' in cmd
        assert '/host/path:/container/path' in cmd
        assert '/data:/data:ro' in cmd

    def test_build_docker_command_with_workdir(self):
        """Deve incluir working directory."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='builder:latest',
            parameters={'workdir': '/app'},
            context={'tool_id': 'builder-001'}
        )

        assert '-w' in cmd
        assert '/app' in cmd

    def test_build_docker_command_with_network(self):
        """Deve configurar network mode."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='nettest:latest',
            parameters={},
            context={'tool_id': 'net-001', 'network': 'host'}
        )

        assert '--network' in cmd
        assert 'host' in cmd

    def test_build_docker_command_with_args_list(self):
        """Deve incluir argumentos do container como lista."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='trivy:latest',
            parameters={
                'args': ['image', '--severity', 'HIGH', 'nginx:latest']
            },
            context={'tool_id': 'trivy-001'}
        )

        assert 'image' in cmd
        assert '--severity' in cmd
        assert 'HIGH' in cmd
        assert 'nginx:latest' in cmd

    def test_build_docker_command_with_args_string(self):
        """Deve incluir argumentos do container como string."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        cmd = adapter._build_docker_command(
            image='echo:latest',
            parameters={'args': 'hello world'},
            context={'tool_id': 'echo-001'}
        )

        assert 'hello world' in cmd


class TestContainerAdapterValidation:
    """Testes de validacao de disponibilidade Docker."""

    @pytest.mark.asyncio
    async def test_validate_tool_availability_docker_available(self):
        """Deve retornar True quando Docker esta disponivel."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'Docker version 24.0.0', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            is_available = await adapter.validate_tool_availability('any-image')

            assert is_available is True
            mock_proc.assert_called_once()
            call_cmd = mock_proc.call_args[0][0]
            assert 'docker version' in call_cmd

    @pytest.mark.asyncio
    async def test_validate_tool_availability_docker_not_available(self):
        """Deve retornar False quando Docker nao esta disponivel."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b'docker: command not found'))
            mock_process.returncode = 127
            mock_proc.return_value = mock_process

            is_available = await adapter.validate_tool_availability('any-image')

            assert is_available is False

    @pytest.mark.asyncio
    async def test_validate_tool_availability_handles_exception(self):
        """Deve retornar False quando ocorre excecao."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_proc.side_effect = OSError('Permission denied')

            is_available = await adapter.validate_tool_availability('any-image')

            assert is_available is False


class TestContainerAdapterMetrics:
    """Testes de metricas."""

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self):
        """Deve registrar tempo de execucao."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'output', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='metrics-001',
                tool_name='metrics',
                command='metrics:latest',
                parameters={},
                context={'tool_id': 'metrics-001'}
            )

            assert result.execution_time_ms > 0
            assert isinstance(result.execution_time_ms, float)

    @pytest.mark.asyncio
    async def test_metadata_includes_docker_info(self):
        """Deve incluir informacoes do Docker no metadata."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'output', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='meta-001',
                tool_name='metadata',
                command='myimage:v1.0',
                parameters={},
                context={'tool_id': 'meta-001'}
            )

            assert result.metadata is not None
            assert result.metadata['image'] == 'myimage:v1.0'
            assert 'docker_command' in result.metadata


class TestContainerAdapterErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_handles_general_exception(self):
        """Deve tratar excecoes gerais graciosamente."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_proc.side_effect = Exception('Unexpected error')

            result = await adapter.execute(
                tool_id='error-001',
                tool_name='error',
                command='error:latest',
                parameters={},
                context={'tool_id': 'error-001'}
            )

            assert result.success is False
            assert 'Unexpected error' in result.error
            assert result.metadata.get('exception') == 'Exception'

    @pytest.mark.asyncio
    async def test_unicode_output_handling(self):
        """Deve tratar output com caracteres unicode."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter()

        # Simular output com caracteres unicode
        unicode_output = '{"message": "Sucesso! ✓"}'.encode('utf-8')

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(unicode_output, b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='unicode-001',
                tool_name='unicode',
                command='unicode:latest',
                parameters={},
                context={'tool_id': 'unicode-001'}
            )

            assert result.success is True
            assert '✓' in result.output


class TestContainerAdapterIntegration:
    """Testes de integracao do adapter."""

    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """Deve executar fluxo completo de container."""
        from src.adapters.container_adapter import ContainerAdapter

        adapter = ContainerAdapter(timeout_seconds=300)

        parameters = {
            'env': {'TRIVY_NO_PROGRESS': 'true'},
            'volumes': ['/var/run/docker.sock:/var/run/docker.sock'],
            'args': ['image', '--severity', 'CRITICAL', 'nginx:1.21']
        }

        context = {
            'tool_id': 'trivy-scan-001',
            'network': 'none'
        }

        expected_output = b'{"Results": [], "SchemaVersion": 2}'

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(expected_output, b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='trivy-scan-001',
                tool_name='trivy',
                command='aquasec/trivy:0.45.0',
                parameters=parameters,
                context=context
            )

            # Validar resultado
            assert result.success is True
            assert 'SchemaVersion' in result.output

            # Validar comando construido
            mock_proc.assert_called_once()
            call_cmd = mock_proc.call_args[0][0]

            # Validar elementos do comando
            assert 'docker run --rm' in call_cmd
            assert '--name mcp-trivy-sc' in call_cmd
            assert '--network none' in call_cmd
            assert '-e TRIVY_NO_PROGRESS=true' in call_cmd
            assert '-v /var/run/docker.sock:/var/run/docker.sock' in call_cmd
            assert 'aquasec/trivy:0.45.0' in call_cmd
            assert 'image' in call_cmd
            assert '--severity' in call_cmd
            assert 'CRITICAL' in call_cmd
            assert 'nginx:1.21' in call_cmd
