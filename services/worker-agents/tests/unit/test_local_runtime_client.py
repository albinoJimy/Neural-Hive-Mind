"""
Testes unitários para LocalRuntimeClient.

Cobertura:
- Execução de comandos permitidos
- Validação de whitelist de comandos
- Timeout de execução
- Coleta de stdout/stderr
- Tratamento de erros
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def local_client():
    """Fixture para LocalRuntimeClient."""
    from services.worker_agents.src.clients.local_runtime_client import LocalRuntimeClient
    return LocalRuntimeClient(
        allowed_commands=['echo', 'python', 'python3', 'ls', 'cat'],
        timeout=30,
        enable_sandbox=True,
        working_dir='/tmp/test-execution',
    )


@pytest.fixture
def local_client_no_sandbox():
    """Fixture para LocalRuntimeClient sem sandbox."""
    from services.worker_agents.src.clients.local_runtime_client import LocalRuntimeClient
    return LocalRuntimeClient(
        allowed_commands=['echo'],
        timeout=30,
        enable_sandbox=False,
        working_dir='/tmp/test-execution',
    )


@pytest.fixture
def execution_request():
    """Fixture para LocalExecutionRequest."""
    from services.worker_agents.src.clients.local_runtime_client import LocalExecutionRequest
    return LocalExecutionRequest(
        command='echo',
        args=['hello', 'world'],
        timeout_seconds=10,
    )


class TestLocalRuntimeClientInit:
    """Testes de inicialização do cliente."""

    def test_init_with_defaults(self):
        """Deve inicializar com valores padrão."""
        from services.worker_agents.src.clients.local_runtime_client import LocalRuntimeClient
        client = LocalRuntimeClient()
        assert client.enable_sandbox is True
        assert client.timeout == 300
        assert 'python' in client.allowed_commands
        assert 'bash' in client.allowed_commands

    def test_init_with_custom_allowed_commands(self):
        """Deve inicializar com comandos customizados."""
        from services.worker_agents.src.clients.local_runtime_client import LocalRuntimeClient
        client = LocalRuntimeClient(allowed_commands=['custom-cmd', 'another-cmd'])
        assert 'custom-cmd' in client.allowed_commands
        assert 'another-cmd' in client.allowed_commands

    def test_init_sandbox_disabled(self):
        """Deve inicializar com sandbox desabilitado."""
        from services.worker_agents.src.clients.local_runtime_client import LocalRuntimeClient
        client = LocalRuntimeClient(enable_sandbox=False)
        assert client.enable_sandbox is False


class TestCommandValidation:
    """Testes de validação de comandos."""

    def test_validate_allowed_command(self, local_client):
        """Deve validar comando permitido sem erro."""
        # Não deve levantar exceção
        local_client._validate_command('echo')
        local_client._validate_command('python')

    def test_validate_disallowed_command(self, local_client):
        """Deve rejeitar comando não permitido."""
        from services.worker_agents.src.clients.local_runtime_client import CommandNotAllowedError

        with pytest.raises(CommandNotAllowedError) as exc_info:
            local_client._validate_command('rm')

        assert 'rm' in str(exc_info.value)
        assert exc_info.value.command == 'rm'

    def test_validate_command_with_path(self, local_client):
        """Deve validar comando com path."""
        # Deve extrair apenas o nome do comando
        local_client._validate_command('/usr/bin/echo')

    def test_validate_command_sandbox_disabled(self, local_client_no_sandbox):
        """Deve permitir qualquer comando quando sandbox desabilitado."""
        # Não deve levantar exceção mesmo para comandos não listados
        local_client_no_sandbox._validate_command('rm')
        local_client_no_sandbox._validate_command('any-command')


class TestCommandExecution:
    """Testes de execução de comandos."""

    @pytest.mark.asyncio
    async def test_execute_echo_success(self, local_client, execution_request):
        """Deve executar echo com sucesso."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'hello world\n', b''))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            result = await local_client.execute_local(execution_request)

            assert result.exit_code == 0
            assert 'hello world' in result.stdout
            assert result.stderr == ''
            assert result.pid == 12345
            assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_execute_with_env_vars(self, local_client):
        """Deve passar variáveis de ambiente."""
        from services.worker_agents.src.clients.local_runtime_client import LocalExecutionRequest

        request = LocalExecutionRequest(
            command='echo',
            args=['$TEST_VAR'],
            env_vars={'TEST_VAR': 'test_value'},
            timeout_seconds=10,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'test_value\n', b''))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            result = await local_client.execute_local(request)

            # Verificar que env foi passado
            call_kwargs = mock_exec.call_args[1]
            assert 'env' in call_kwargs
            assert 'TEST_VAR' in call_kwargs['env']

    @pytest.mark.asyncio
    async def test_execute_with_working_dir(self, local_client):
        """Deve usar diretório de trabalho especificado."""
        from services.worker_agents.src.clients.local_runtime_client import LocalExecutionRequest

        request = LocalExecutionRequest(
            command='ls',
            working_dir='/tmp/custom-dir',
            timeout_seconds=10,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'file1\nfile2\n', b''))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            with patch('os.path.exists', return_value=True):
                mock_exec.return_value = mock_process

                await local_client.execute_local(request)

                call_kwargs = mock_exec.call_args[1]
                assert call_kwargs['cwd'] == '/tmp/custom-dir'

    @pytest.mark.asyncio
    async def test_execute_nonzero_exit_code(self, local_client):
        """Deve capturar exit code diferente de zero."""
        from services.worker_agents.src.clients.local_runtime_client import LocalExecutionRequest

        request = LocalExecutionRequest(
            command='python',
            args=['-c', 'exit(1)'],
            timeout_seconds=10,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b'', b'Error\n'))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            result = await local_client.execute_local(request)

            assert result.exit_code == 1
            assert 'Error' in result.stderr


class TestCommandTimeout:
    """Testes de timeout de execução."""

    @pytest.mark.asyncio
    async def test_execute_timeout(self, local_client):
        """Deve levantar timeout quando comando demora demais."""
        from services.worker_agents.src.clients.local_runtime_client import (
            LocalExecutionRequest,
            LocalTimeoutError
        )

        request = LocalExecutionRequest(
            command='python',
            args=['-c', 'import time; time.sleep(100)'],
            timeout_seconds=1,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            with pytest.raises(LocalTimeoutError):
                await local_client.execute_local(request)


class TestCommandNotAllowed:
    """Testes de comandos não permitidos."""

    @pytest.mark.asyncio
    async def test_execute_disallowed_command(self, local_client):
        """Deve rejeitar execução de comando não permitido."""
        from services.worker_agents.src.clients.local_runtime_client import (
            LocalExecutionRequest,
            CommandNotAllowedError
        )

        request = LocalExecutionRequest(
            command='rm',
            args=['-rf', '/'],
            timeout_seconds=10,
        )

        with pytest.raises(CommandNotAllowedError) as exc_info:
            await local_client.execute_local(request)

        assert exc_info.value.command == 'rm'


class TestAllowedCommandsManagement:
    """Testes de gerenciamento de comandos permitidos."""

    def test_add_allowed_command(self, local_client):
        """Deve adicionar comando à whitelist."""
        assert 'new-command' not in local_client.allowed_commands
        local_client.add_allowed_command('new-command')
        assert 'new-command' in local_client.allowed_commands

    def test_add_duplicate_command(self, local_client):
        """Não deve duplicar comando já existente."""
        initial_count = len(local_client.allowed_commands)
        local_client.add_allowed_command('echo')
        assert len(local_client.allowed_commands) == initial_count

    def test_remove_allowed_command(self, local_client):
        """Deve remover comando da whitelist."""
        assert 'echo' in local_client.allowed_commands
        local_client.remove_allowed_command('echo')
        assert 'echo' not in local_client.allowed_commands

    def test_remove_nonexistent_command(self, local_client):
        """Não deve falhar ao remover comando inexistente."""
        initial_count = len(local_client.allowed_commands)
        local_client.remove_allowed_command('nonexistent')
        assert len(local_client.allowed_commands) == initial_count


class TestHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, local_client):
        """Deve retornar True quando echo funciona."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'health_check\n', b''))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            result = await local_client.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, local_client):
        """Deve retornar False quando echo falha."""
        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = Exception('Process creation failed')

            result = await local_client.health_check()

            assert result is False


class TestOutputTruncation:
    """Testes de truncamento de output."""

    def test_truncate_large_output(self, local_client):
        """Deve truncar output grande."""
        large_output = 'x' * (local_client.max_output_size + 1000)
        truncated = local_client._truncate_output(large_output, 'stdout')

        assert len(truncated) <= local_client.max_output_size + 100  # Margem para mensagem
        assert 'truncado' in truncated

    def test_no_truncate_small_output(self, local_client):
        """Não deve truncar output pequeno."""
        small_output = 'hello world'
        result = local_client._truncate_output(small_output, 'stdout')

        assert result == small_output


class TestEnvironmentBuild:
    """Testes de construção de ambiente."""

    def test_build_env_minimal(self, local_client):
        """Deve construir ambiente mínimo sem herança."""
        env = local_client._build_env()

        assert 'PATH' in env
        assert 'HOME' in env
        assert 'LANG' in env

    def test_build_env_with_custom_vars(self, local_client):
        """Deve incluir variáveis customizadas."""
        env = local_client._build_env({'CUSTOM_VAR': 'custom_value'})

        assert env['CUSTOM_VAR'] == 'custom_value'

    def test_build_env_inherit(self):
        """Deve herdar ambiente do processo pai quando configurado."""
        from services.worker_agents.src.clients.local_runtime_client import LocalRuntimeClient

        client = LocalRuntimeClient(inherit_env=True)

        with patch.dict('os.environ', {'INHERITED_VAR': 'inherited_value'}):
            env = client._build_env()
            assert 'INHERITED_VAR' in env


class TestMetricsRecording:
    """Testes de registro de métricas."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(self, local_client, execution_request):
        """Deve registrar métricas em execução bem-sucedida."""
        mock_metrics = MagicMock()
        mock_metrics.local_executions_total = MagicMock()
        mock_metrics.local_executions_total.labels = MagicMock(return_value=MagicMock())
        mock_metrics.local_execution_duration_seconds = MagicMock()

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'output\n', b''))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            await local_client.execute_local(execution_request, metrics=mock_metrics)

            mock_metrics.local_executions_total.labels.assert_called_with(status='success')

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_failure(self, local_client):
        """Deve registrar métricas em execução com falha."""
        from services.worker_agents.src.clients.local_runtime_client import LocalExecutionRequest

        request = LocalExecutionRequest(
            command='python',
            args=['-c', 'exit(1)'],
            timeout_seconds=10,
        )

        mock_metrics = MagicMock()
        mock_metrics.local_executions_total = MagicMock()
        mock_metrics.local_executions_total.labels = MagicMock(return_value=MagicMock())
        mock_metrics.local_execution_duration_seconds = MagicMock()

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b'', b'error\n'))

        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            await local_client.execute_local(request, metrics=mock_metrics)

            mock_metrics.local_executions_total.labels.assert_called_with(status='failed')


class TestClientClose:
    """Testes de fechamento do cliente."""

    @pytest.mark.asyncio
    async def test_close_client(self, local_client):
        """Deve fechar cliente sem erro."""
        # Não deve levantar exceção
        await local_client.close()
