"""
Adapter para ferramentas executadas via CLI (Command Line Interface).
"""

import asyncio
import shlex
import time
from typing import Dict, Any, List, Optional
import structlog

from .base_adapter import BaseToolAdapter, ExecutionResult, AdapterError

logger = structlog.get_logger(__name__)


class CLIAdapter(BaseToolAdapter):
    """Adapter para execução de ferramentas via linha de comando."""

    def __init__(self, timeout_seconds: int = 300):
        super().__init__()
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        tool_id: str,
        tool_name: str,
        command: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Executa ferramenta CLI.

        Args:
            tool_id: ID da ferramenta
            tool_name: Nome da ferramenta (ex: 'trivy', 'black', 'terraform')
            command: Comando base (ex: 'trivy image', 'black --check')
            parameters: Parâmetros adicionais
            context: Contexto com working_dir, env_vars, etc

        Returns:
            ExecutionResult
        """
        start_time = time.time()

        try:
            # Construir comando completo
            full_command = self._build_command(command, parameters)

            # Obter working directory e env vars do contexto
            working_dir = context.get("working_dir", ".")
            env_vars = context.get("env_vars", {})

            self.logger.info(
                "executing_cli_tool",
                tool_name=tool_name,
                command=full_command,
                working_dir=working_dir
            )

            # Executar comando
            process = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=env_vars if env_vars else None
            )

            # Aguardar com timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                raise AdapterError(
                    f"Tool {tool_name} timed out after {self.timeout_seconds}s"
                )

            execution_time_ms = (time.time() - start_time) * 1000

            # Decodificar output
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace') if stderr else None

            result = ExecutionResult(
                success=(process.returncode == 0),
                output=output,
                error=error,
                execution_time_ms=execution_time_ms,
                exit_code=process.returncode,
                metadata={
                    "command": full_command,
                    "working_dir": working_dir
                }
            )

            await self._log_execution(tool_name, full_command, result)
            return result

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "cli_tool_execution_failed",
                tool_name=tool_name,
                error=str(e),
                execution_time_ms=execution_time_ms
            )
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time_ms=execution_time_ms,
                metadata={"exception": type(e).__name__}
            )

    async def validate_tool_availability(self, tool_name: str) -> bool:
        """
        Valida se CLI tool está disponível via 'which' ou '--version'.

        Args:
            tool_name: Nome do executável (ex: 'trivy', 'black')

        Returns:
            True se encontrado
        """
        try:
            # Tentar 'which'
            process = await asyncio.create_subprocess_shell(
                f"which {shlex.quote(tool_name)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if process.returncode == 0:
                return True

            # Fallback: tentar executar com --version
            process = await asyncio.create_subprocess_shell(
                f"{shlex.quote(tool_name)} --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            return process.returncode == 0

        except Exception as e:
            self.logger.warning(
                "cli_tool_validation_failed",
                tool_name=tool_name,
                error=str(e)
            )
            return False

    def _build_command(
        self,
        base_command: str,
        parameters: Dict[str, Any]
    ) -> str:
        """
        Constrói comando CLI completo a partir de parâmetros.

        Args:
            base_command: Comando base (ex: 'trivy image')
            parameters: Dict com flags e valores

        Returns:
            Comando completo (ex: 'trivy image --severity HIGH nginx:latest')
        """
        parts = [base_command]

        for key, value in parameters.items():
            if key.startswith("_"):  # Skip internal parameters
                continue

            if isinstance(value, bool):
                if value:
                    parts.append(f"--{key}")
            elif isinstance(value, list):
                for item in value:
                    parts.append(f"--{key} {shlex.quote(str(item))}")
            else:
                parts.append(f"--{key} {shlex.quote(str(value))}")

        return " ".join(parts)
