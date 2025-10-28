"""
Adapter para ferramentas executadas via containers Docker.
"""

import time
import json
from typing import Dict, Any, List, Optional
import structlog

from .base_adapter import BaseToolAdapter, ExecutionResult, AdapterError

logger = structlog.get_logger(__name__)


class ContainerAdapter(BaseToolAdapter):
    """Adapter para execução de ferramentas via Docker containers."""

    def __init__(
        self,
        docker_host: str = "unix:///var/run/docker.sock",
        timeout_seconds: int = 600
    ):
        super().__init__()
        self.docker_host = docker_host
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        tool_id: str,
        tool_name: str,
        command: str,  # Docker image
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Executa ferramenta via Docker container.

        Args:
            tool_id: ID da ferramenta
            tool_name: Nome da ferramenta
            command: Imagem Docker (ex: 'aquasec/trivy:latest')
            parameters: Parâmetros do container (args, env, volumes)
            context: Configuração adicional

        Returns:
            ExecutionResult
        """
        start_time = time.time()

        try:
            # Construir comando docker run
            docker_command = self._build_docker_command(
                command,
                parameters,
                context
            )

            self.logger.info(
                "executing_container_tool",
                tool_name=tool_name,
                image=command
            )

            # Executar via docker CLI (simplificação - em produção usar docker-py)
            import asyncio

            process = await asyncio.create_subprocess_shell(
                docker_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                # Tentar matar container órfão
                container_name = f"mcp-{tool_id[:8]}"
                await asyncio.create_subprocess_shell(
                    f"docker kill {container_name}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                raise AdapterError(
                    f"Container {tool_name} timed out after {self.timeout_seconds}s"
                )

            execution_time_ms = (time.time() - start_time) * 1000

            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace') if stderr else None

            result = ExecutionResult(
                success=(process.returncode == 0),
                output=output,
                error=error,
                execution_time_ms=execution_time_ms,
                exit_code=process.returncode,
                metadata={
                    "image": command,
                    "docker_command": docker_command
                }
            )

            await self._log_execution(tool_name, command, result)
            return result

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "container_tool_execution_failed",
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
        Valida se Docker está disponível e pode puxar imagem.

        Args:
            tool_name: Nome da imagem Docker

        Returns:
            True se Docker disponível
        """
        try:
            import asyncio

            # Verificar se docker está disponível
            process = await asyncio.create_subprocess_shell(
                "docker version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            return process.returncode == 0

        except Exception as e:
            self.logger.warning(
                "docker_validation_failed",
                error=str(e)
            )
            return False

    def _build_docker_command(
        self,
        image: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """
        Constrói comando 'docker run' completo.

        Args:
            image: Imagem Docker
            parameters: Parâmetros (args, env, volumes)
            context: Contexto adicional

        Returns:
            Comando docker run completo
        """
        parts = ["docker", "run", "--rm"]

        # Nome do container (para facilitar kill)
        container_id = context.get("tool_id", "unknown")[:8]
        parts.extend(["--name", f"mcp-{container_id}"])

        # Network mode
        network = context.get("network", "bridge")
        parts.extend(["--network", network])

        # Environment variables
        env_vars = parameters.get("env", {})
        for key, value in env_vars.items():
            parts.extend(["-e", f"{key}={value}"])

        # Volume mounts
        volumes = parameters.get("volumes", [])
        for volume in volumes:
            parts.extend(["-v", volume])

        # Working directory
        if "workdir" in parameters:
            parts.extend(["-w", parameters["workdir"]])

        # Imagem
        parts.append(image)

        # Argumentos para o container
        if "args" in parameters:
            if isinstance(parameters["args"], list):
                parts.extend(parameters["args"])
            else:
                parts.append(str(parameters["args"]))

        return " ".join(parts)
