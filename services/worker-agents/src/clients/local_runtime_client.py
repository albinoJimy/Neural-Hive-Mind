"""
Cliente Local Runtime para execução de comandos via subprocess.

Este cliente implementa execução local de comandos com sandbox básico,
whitelist de comandos permitidos e isolamento via working directory.
"""

import asyncio
import os
import signal
import structlog
from typing import Dict, Any, Optional, List
from opentelemetry import trace
from pydantic import BaseModel, Field


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class LocalExecutionError(Exception):
    """Erro de execução local."""
    def __init__(self, message: str, exit_code: Optional[int] = None):
        super().__init__(message)
        self.exit_code = exit_code


class LocalTimeoutError(Exception):
    """Timeout aguardando execução local."""
    pass


class CommandNotAllowedError(Exception):
    """Comando não permitido para execução."""
    def __init__(self, command: str, allowed_commands: List[str]):
        super().__init__(f"Comando '{command}' não permitido. Permitidos: {allowed_commands}")
        self.command = command
        self.allowed_commands = allowed_commands


class LocalExecutionRequest(BaseModel):
    """Request para execução local de comando."""
    command: str = Field(..., description='Comando a executar')
    args: Optional[List[str]] = Field(default=None, description='Argumentos do comando')
    env_vars: Optional[Dict[str, str]] = Field(default=None, description='Variáveis de ambiente')
    working_dir: Optional[str] = Field(default=None, description='Diretório de trabalho')
    timeout_seconds: int = Field(default=300, description='Timeout em segundos')
    shell: bool = Field(default=False, description='Executar via shell')
    stdin_data: Optional[str] = Field(default=None, description='Dados para stdin')
    capture_output: bool = Field(default=True, description='Capturar stdout/stderr')


class LocalExecutionResult(BaseModel):
    """Resultado da execução local."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    pid: Optional[int] = None
    command_executed: str
    timed_out: bool = False
    killed: bool = False


class LocalRuntimeClient:
    """Cliente para execução local de comandos com sandbox básico."""

    # Comandos seguros por padrão
    DEFAULT_ALLOWED_COMMANDS = [
        'python', 'python3',
        'node', 'npm', 'npx',
        'bash', 'sh',
        'terraform',
        'kubectl',
        'helm',
        'docker',
        'git',
        'curl', 'wget',
        'jq', 'yq',
        'make',
        'go',
        'cargo', 'rustc',
        'mvn', 'gradle',
        'pip', 'pip3',
        'poetry',
        'pytest',
        'echo', 'cat', 'ls', 'pwd',
    ]

    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        timeout: int = 300,
        enable_sandbox: bool = True,
        working_dir: str = '/tmp/neural-hive-execution',
        max_output_size: int = 1024 * 1024,  # 1MB
        inherit_env: bool = False,
        graceful_timeout: int = 10,
    ):
        """
        Inicializa cliente Local Runtime.

        Args:
            allowed_commands: Lista de comandos permitidos (None = usar padrão)
            timeout: Timeout padrão em segundos
            enable_sandbox: Habilitar validação de comandos
            working_dir: Diretório de trabalho padrão
            max_output_size: Tamanho máximo de output em bytes
            inherit_env: Herdar variáveis de ambiente do processo pai
            graceful_timeout: Tempo para SIGTERM antes de SIGKILL
        """
        self.allowed_commands = allowed_commands or self.DEFAULT_ALLOWED_COMMANDS
        self.timeout = timeout
        self.enable_sandbox = enable_sandbox
        self.working_dir = working_dir
        self.max_output_size = max_output_size
        self.inherit_env = inherit_env
        self.graceful_timeout = graceful_timeout
        self.logger = logger.bind(service='local_runtime_client')

        # Criar diretório de trabalho se não existir
        if working_dir and not os.path.exists(working_dir):
            try:
                os.makedirs(working_dir, exist_ok=True)
                self.logger.info('working_dir_created', path=working_dir)
            except Exception as e:
                self.logger.warning('working_dir_creation_failed', path=working_dir, error=str(e))

    def _validate_command(self, command: str) -> None:
        """
        Valida se comando é permitido.

        Args:
            command: Comando a validar

        Raises:
            CommandNotAllowedError: Se comando não é permitido
        """
        if not self.enable_sandbox:
            return

        # Extrair nome base do comando (sem path)
        base_command = os.path.basename(command.split()[0]) if command else ''

        if base_command not in self.allowed_commands:
            self.logger.warning(
                'command_not_allowed',
                command=base_command,
                allowed=self.allowed_commands
            )
            raise CommandNotAllowedError(base_command, self.allowed_commands)

    def _build_env(self, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Constrói variáveis de ambiente para execução."""
        if self.inherit_env:
            env = os.environ.copy()
        else:
            # Ambiente mínimo necessário
            env = {
                'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
                'HOME': os.environ.get('HOME', '/tmp'),
                'LANG': 'C.UTF-8',
                'LC_ALL': 'C.UTF-8',
            }

        if env_vars:
            env.update(env_vars)

        return env

    def _truncate_output(self, output: str, label: str = 'output') -> str:
        """Trunca output se exceder tamanho máximo."""
        if len(output) > self.max_output_size:
            truncated_msg = f'\n... [{label} truncado, {len(output)} bytes total] ...'
            return output[:self.max_output_size] + truncated_msg
        return output

    async def _kill_process_tree(self, pid: int) -> None:
        """Tenta matar processo e seus filhos."""
        try:
            import psutil
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            # Enviar SIGTERM para todos
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            parent.terminate()

            # Aguardar término gracioso
            gone, alive = psutil.wait_procs(
                [parent] + children,
                timeout=self.graceful_timeout
            )

            # SIGKILL para os que ainda estão vivos
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

        except ImportError:
            # psutil não disponível, usar apenas os.kill
            try:
                os.kill(pid, signal.SIGTERM)
                await asyncio.sleep(self.graceful_timeout)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except Exception as e:
            self.logger.warning('process_kill_failed', pid=pid, error=str(e))

    async def execute_local(
        self,
        request: LocalExecutionRequest,
        metrics=None
    ) -> LocalExecutionResult:
        """
        Executa comando localmente via subprocess.

        Args:
            request: Parâmetros da execução
            metrics: Objeto de métricas Prometheus (opcional)

        Returns:
            LocalExecutionResult com resultado da execução

        Raises:
            LocalExecutionError: Erro na execução
            LocalTimeoutError: Timeout aguardando execução
            CommandNotAllowedError: Comando não permitido
        """
        with tracer.start_as_current_span('local.execute') as span:
            span.set_attribute('local.command', request.command)
            span.set_attribute('local.timeout', request.timeout_seconds)

            # Validar comando
            self._validate_command(request.command)

            # Construir comando completo
            if request.args:
                cmd_parts = [request.command] + request.args
            else:
                cmd_parts = [request.command]

            command_str = ' '.join(cmd_parts)
            span.set_attribute('local.command_full', command_str)

            # Determinar working directory
            cwd = request.working_dir or self.working_dir
            if cwd and not os.path.exists(cwd):
                os.makedirs(cwd, exist_ok=True)

            # Construir ambiente
            env = self._build_env(request.env_vars)

            self.logger.info(
                'local_execution_starting',
                command=command_str,
                working_dir=cwd,
                timeout=request.timeout_seconds
            )

            start_time = asyncio.get_event_loop().time()
            process = None
            timed_out = False
            killed = False

            try:
                # Criar subprocess
                if request.shell:
                    process = await asyncio.create_subprocess_shell(
                        command_str,
                        stdout=asyncio.subprocess.PIPE if request.capture_output else None,
                        stderr=asyncio.subprocess.PIPE if request.capture_output else None,
                        stdin=asyncio.subprocess.PIPE if request.stdin_data else None,
                        cwd=cwd,
                        env=env,
                    )
                else:
                    process = await asyncio.create_subprocess_exec(
                        *cmd_parts,
                        stdout=asyncio.subprocess.PIPE if request.capture_output else None,
                        stderr=asyncio.subprocess.PIPE if request.capture_output else None,
                        stdin=asyncio.subprocess.PIPE if request.stdin_data else None,
                        cwd=cwd,
                        env=env,
                    )

                pid = process.pid
                span.set_attribute('local.pid', pid)

                # Comunicar com processo
                stdin_bytes = request.stdin_data.encode('utf-8') if request.stdin_data else None

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(input=stdin_bytes),
                        timeout=request.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    timed_out = True
                    self.logger.warning(
                        'local_execution_timeout',
                        pid=pid,
                        command=request.command,
                        timeout=request.timeout_seconds
                    )

                    # Tentar matar processo
                    await self._kill_process_tree(pid)
                    killed = True

                    # Tentar ler output parcial
                    stdout_bytes = b''
                    stderr_bytes = 'Execução cancelada por timeout'.encode('utf-8')

                # Processar output
                stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ''
                stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ''

                # Truncar se necessário
                stdout = self._truncate_output(stdout, 'stdout')
                stderr = self._truncate_output(stderr, 'stderr')

                exit_code = process.returncode if process.returncode is not None else -1
                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                self.logger.info(
                    'local_execution_completed',
                    command=request.command,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    timed_out=timed_out
                )

                # Registrar métricas
                if metrics:
                    if timed_out:
                        status = 'timeout'
                    elif exit_code == 0:
                        status = 'success'
                    else:
                        status = 'failed'

                    if hasattr(metrics, 'local_executions_total'):
                        metrics.local_executions_total.labels(status=status).inc()
                    if hasattr(metrics, 'local_execution_duration_seconds'):
                        metrics.local_execution_duration_seconds.observe(duration_ms / 1000)

                if timed_out:
                    raise LocalTimeoutError(
                        f'Timeout após {request.timeout_seconds}s executando: {request.command}'
                    )

                return LocalExecutionResult(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                    pid=pid,
                    command_executed=command_str,
                    timed_out=timed_out,
                    killed=killed
                )

            except CommandNotAllowedError:
                if metrics and hasattr(metrics, 'local_executions_total'):
                    metrics.local_executions_total.labels(status='not_allowed').inc()
                raise

            except LocalTimeoutError:
                raise

            except Exception as e:
                self.logger.error(
                    'local_execution_failed',
                    command=request.command,
                    error=str(e)
                )
                if metrics and hasattr(metrics, 'local_executions_total'):
                    metrics.local_executions_total.labels(status='failed').inc()
                raise LocalExecutionError(f'Erro na execução local: {e}')

            finally:
                # Garantir que processo foi finalizado
                if process and process.returncode is None:
                    try:
                        process.kill()
                        await process.wait()
                    except Exception:
                        pass

    async def health_check(self) -> bool:
        """Verifica se runtime local está funcional."""
        try:
            result = await self.execute_local(
                LocalExecutionRequest(
                    command='echo',
                    args=['health_check'],
                    timeout_seconds=5
                )
            )
            return result.exit_code == 0 and 'health_check' in result.stdout
        except Exception:
            return False

    def add_allowed_command(self, command: str) -> None:
        """Adiciona comando à whitelist."""
        if command not in self.allowed_commands:
            self.allowed_commands.append(command)
            self.logger.info('allowed_command_added', command=command)

    def remove_allowed_command(self, command: str) -> None:
        """Remove comando da whitelist."""
        if command in self.allowed_commands:
            self.allowed_commands.remove(command)
            self.logger.info('allowed_command_removed', command=command)

    async def close(self) -> None:
        """Cleanup do cliente (no-op para local runtime)."""
        self.logger.info('local_runtime_client_closed')
