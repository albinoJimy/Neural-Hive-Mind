"""
Testes unitarios para CLIAdapter.

Cobertura:
- Execucao de comando CLI (sucesso, erro, timeout)
- Construcao de comando com parametros
- Parsing de stdout/stderr
- Working directory e environment variables
- Timeout configuravel (300s)
- Exit code handling
- Metricas
"""

import asyncio
import os
import shlex
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCLIAdapterExecution:
    """Testes de execucao de comandos."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Deve executar comando com sucesso e validar chamada subprocess."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'Success output', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='pytest',
                command='pytest',
                parameters={'verbose': True},
                context={'working_dir': '/tmp/project'}
            )

            # Validar resultado
            assert result.success is True
            assert result.exit_code == 0
            assert 'Success output' in result.output

            # Validar chamada do subprocess
            mock_proc.assert_called_once()
            call_args = mock_proc.call_args
            assert 'pytest' in call_args[0][0]
            assert call_args.kwargs['cwd'] == '/tmp/project'
            assert call_args.kwargs['stdout'] == asyncio.subprocess.PIPE
            assert call_args.kwargs['stderr'] == asyncio.subprocess.PIPE

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """Deve retornar erro quando comando falha."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b'Error: test failed'))
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='pytest',
                command='pytest',
                parameters={},
                context={}
            )

            assert result.success is False
            assert result.exit_code == 1
            assert 'Error: test failed' in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Deve tratar timeout e matar processo."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter(timeout_seconds=1)

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_process.kill = MagicMock()
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='slow-tool',
                command='slow-tool',
                parameters={},
                context={}
            )

            assert result.success is False
            assert 'timeout' in result.error.lower()
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_output_parsing(self):
        """Deve fazer parsing correto de stdout/stderr."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        stdout_content = b'{"result": "success", "count": 10}'
        stderr_content = b'Warning: deprecated option'

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(stdout_content, stderr_content))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='json-tool',
                command='json-tool',
                parameters={},
                context={}
            )

            assert result.output == stdout_content.decode('utf-8')
            assert result.error == stderr_content.decode('utf-8')


class TestCLIAdapterCommandBuilding:
    """Testes de construcao de comandos."""

    def test_build_command_with_string_args(self):
        """Deve construir comando com argumentos string."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        params = {
            'severity': 'HIGH',
            'output': 'json'
        }

        cmd = adapter._build_command('trivy image', params)

        assert 'trivy image' in cmd
        assert '--severity' in cmd
        assert "'HIGH'" in cmd or 'HIGH' in cmd
        assert '--output' in cmd

    def test_build_command_with_boolean_flag(self):
        """Deve incluir flag boolean quando True."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        params = {
            'verbose': True,
            'quiet': False
        }

        cmd = adapter._build_command('pytest', params)

        assert '--verbose' in cmd
        assert '--quiet' not in cmd

    def test_build_command_with_list_args(self):
        """Deve construir comando com argumentos lista."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        params = {
            'ignore': ['CVE-2021-1234', 'CVE-2022-5678']
        }

        cmd = adapter._build_command('trivy', params)

        assert '--ignore' in cmd
        assert 'CVE-2021-1234' in cmd
        assert 'CVE-2022-5678' in cmd

    def test_build_command_with_target(self):
        """Deve adicionar _target ao final do comando."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        params = {
            'severity': 'HIGH',
            '_target': 'nginx:latest'
        }

        cmd = adapter._build_command('trivy image', params)

        # Target deve estar no final e quotado
        assert cmd.endswith("'nginx:latest'")
        # _target nao deve aparecer como flag
        assert '--_target' not in cmd

    @pytest.mark.parametrize('params,expected_parts', [
        ({'verbose': True}, ['--verbose']),
        ({'output': 'json'}, ['--output', 'json']),
        ({'count': 5}, ['--count', '5']),
        ({'_target': 'myimage'}, ["'myimage'"]),
    ])
    def test_build_command_parametrized(self, params, expected_parts):
        """Testes parametrizados de construcao de comando."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()
        cmd = adapter._build_command('tool', params)

        for part in expected_parts:
            assert part in cmd


class TestCLIAdapterEnvironment:
    """Testes de environment variables."""

    @pytest.mark.asyncio
    async def test_execute_with_env_vars(self):
        """Deve passar environment variables para subprocess."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        env_vars = {
            'MY_VAR': 'my_value',
            'API_KEY': 'secret123'
        }

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            await adapter.execute(
                tool_id='test-tool-001',
                tool_name='env-tool',
                command='env-tool',
                parameters={},
                context={'env_vars': env_vars}
            )

            # Validar que env foi passado corretamente
            mock_proc.assert_called_once()
            call_kwargs = mock_proc.call_args.kwargs
            assert call_kwargs['env'] == env_vars

    @pytest.mark.asyncio
    async def test_execute_without_env_vars(self):
        """Deve usar None quando nao ha env_vars."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            await adapter.execute(
                tool_id='test-tool-001',
                tool_name='simple-tool',
                command='simple-tool',
                parameters={},
                context={}
            )

            call_kwargs = mock_proc.call_args.kwargs
            assert call_kwargs.get('env') is None


class TestCLIAdapterWorkingDirectory:
    """Testes de working directory."""

    @pytest.mark.asyncio
    async def test_execute_with_working_dir(self):
        """Deve usar working directory especificado."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            await adapter.execute(
                tool_id='test-tool-001',
                tool_name='dir-tool',
                command='dir-tool',
                parameters={},
                context={'working_dir': '/tmp/test/project'}
            )

            # Validar cwd passado
            mock_proc.assert_called_once()
            call_kwargs = mock_proc.call_args.kwargs
            assert call_kwargs['cwd'] == '/tmp/test/project'

    @pytest.mark.asyncio
    async def test_execute_with_default_working_dir(self):
        """Deve usar diretorio padrao quando nao especificado."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            await adapter.execute(
                tool_id='test-tool-001',
                tool_name='simple-tool',
                command='simple-tool',
                parameters={},
                context={}
            )

            call_kwargs = mock_proc.call_args.kwargs
            assert call_kwargs['cwd'] == '.'


class TestCLIAdapterExitCodes:
    """Testes de tratamento de exit codes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('exit_code,expected_success', [
        (0, True),
        (1, False),
        (2, False),
        (127, False),  # Command not found
        (137, False),  # Killed by SIGKILL
        (143, False),  # Killed by SIGTERM
    ])
    async def test_exit_code_handling(self, exit_code, expected_success):
        """Deve tratar diferentes exit codes corretamente."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'output', b''))
            mock_process.returncode = exit_code
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='exit-tool',
                command='exit-tool',
                parameters={},
                context={}
            )

            assert result.success is expected_success
            assert result.exit_code == exit_code

            # Validar que comando foi executado
            mock_proc.assert_called_once()


class TestCLIAdapterValidation:
    """Testes de validacao de ferramentas."""

    @pytest.mark.asyncio
    async def test_validate_tool_availability_via_which(self):
        """Deve validar disponibilidade via 'which'."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'/usr/bin/pytest', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            is_available = await adapter.validate_tool_availability('pytest')

            assert is_available is True
            mock_proc.assert_called_once()
            # Verificar que 'which' foi usado
            call_cmd = mock_proc.call_args[0][0]
            assert 'which' in call_cmd
            assert 'pytest' in call_cmd

    @pytest.mark.asyncio
    async def test_validate_tool_availability_fallback_to_version(self):
        """Deve tentar --version quando 'which' falha."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        call_count = 0

        async def mock_communicate():
            nonlocal call_count
            call_count += 1
            return (b'', b'')

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = mock_communicate

            # Primeira chamada (which) falha, segunda (--version) sucede
            returncodes = [1, 0]
            mock_process.returncode = property(lambda self: returncodes.pop(0) if returncodes else 0)

            # Simular diferentes returncodes
            processes = []
            for rc in [1, 0]:
                p = AsyncMock()
                p.communicate = AsyncMock(return_value=(b'', b''))
                p.returncode = rc
                processes.append(p)

            mock_proc.side_effect = processes

            is_available = await adapter.validate_tool_availability('custom-tool')

            assert is_available is True
            assert mock_proc.call_count == 2

    @pytest.mark.asyncio
    async def test_validate_tool_not_available(self):
        """Deve retornar False quando ferramenta nao existe."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b'not found'))
            mock_process.returncode = 1
            mock_proc.return_value = mock_process

            is_available = await adapter.validate_tool_availability('nonexistent-tool')

            assert is_available is False

    @pytest.mark.asyncio
    async def test_validate_tool_handles_exception(self):
        """Deve retornar False quando ocorre excecao."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_proc.side_effect = OSError('Permission denied')

            is_available = await adapter.validate_tool_availability('restricted-tool')

            assert is_available is False


class TestCLIAdapterMetrics:
    """Testes de metricas."""

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self):
        """Deve registrar tempo de execucao positivo."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='metrics-tool',
                command='metrics-tool',
                parameters={},
                context={}
            )

            assert result.execution_time_ms > 0
            assert isinstance(result.execution_time_ms, float)

    @pytest.mark.asyncio
    async def test_metadata_includes_command_info(self):
        """Deve incluir informacoes do comando no metadata."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter()

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='test-tool-001',
                tool_name='metadata-tool',
                command='metadata-tool --check',
                parameters={'verbose': True},
                context={'working_dir': '/app'}
            )

            assert result.metadata is not None
            assert 'command' in result.metadata
            assert 'working_dir' in result.metadata
            assert result.metadata['working_dir'] == '/app'


class TestCLIAdapterIntegration:
    """Testes de integracao entre componentes do adapter."""

    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """Deve executar fluxo completo: build command -> execute -> parse result."""
        from src.adapters.cli_adapter import CLIAdapter

        adapter = CLIAdapter(timeout_seconds=60)

        params = {
            'severity': 'CRITICAL',
            'format': 'json',
            '_target': 'myapp:latest'
        }

        context = {
            'working_dir': '/home/user/project',
            'env_vars': {'TRIVY_NO_PROGRESS': 'true'}
        }

        expected_stdout = b'{"vulnerabilities": []}'

        with patch('asyncio.create_subprocess_shell', new_callable=AsyncMock) as mock_proc:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(expected_stdout, b''))
            mock_process.returncode = 0
            mock_proc.return_value = mock_process

            result = await adapter.execute(
                tool_id='trivy-001',
                tool_name='trivy',
                command='trivy image',
                parameters=params,
                context=context
            )

            # Validar resultado
            assert result.success is True
            assert result.output == '{"vulnerabilities": []}'

            # Validar chamada do subprocess
            mock_proc.assert_called_once()
            call_args = mock_proc.call_args

            # Validar comando construido
            executed_cmd = call_args[0][0]
            assert 'trivy image' in executed_cmd
            assert '--severity' in executed_cmd
            assert 'CRITICAL' in executed_cmd
            assert '--format' in executed_cmd
            assert 'json' in executed_cmd
            assert "'myapp:latest'" in executed_cmd

            # Validar kwargs
            assert call_args.kwargs['cwd'] == '/home/user/project'
            assert call_args.kwargs['env'] == {'TRIVY_NO_PROGRESS': 'true'}
