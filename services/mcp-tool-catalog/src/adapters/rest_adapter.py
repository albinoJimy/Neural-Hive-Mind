"""
Adapter para ferramentas acessadas via REST API.
"""

import asyncio
import time
from typing import Dict, Any, Optional
import aiohttp
import structlog

from .base_adapter import BaseToolAdapter, ExecutionResult, AdapterError

logger = structlog.get_logger(__name__)


class RESTAdapter(BaseToolAdapter):
    """Adapter para execução de ferramentas via REST API."""

    def __init__(
        self,
        timeout_seconds: int = 60,
        max_retries: int = 3
    ):
        super().__init__()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def execute(
        self,
        tool_id: str,
        tool_name: str,
        command: str,  # URL endpoint
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Executa ferramenta REST API.

        Args:
            tool_id: ID da ferramenta
            tool_name: Nome da ferramenta (ex: 'sonarqube', 'snyk')
            command: URL endpoint (ex: 'https://api.snyk.io/v1/test')
            parameters: Parâmetros da requisição (body, query params)
            context: Headers, auth, método HTTP

        Returns:
            ExecutionResult
        """
        start_time = time.time()

        # Extrair configurações do contexto
        method = context.get("http_method", "POST").upper()
        headers = context.get("headers", {})
        auth_token = context.get("auth_token")

        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        # Separar query params do body
        query_params = parameters.get("query", {})
        body = parameters.get("body", {})

        self.logger.info(
            "executing_rest_tool",
            tool_name=tool_name,
            method=method,
            endpoint=command
        )

        for attempt in range(1, self.max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

                    async with session.request(
                        method=method,
                        url=command,
                        params=query_params,
                        json=body if body else None,
                        headers=headers,
                        timeout=timeout
                    ) as response:
                        execution_time_ms = (time.time() - start_time) * 1000

                        response_text = await response.text()

                        success = 200 <= response.status < 300
                        result = ExecutionResult(
                            success=success,
                            output=response_text,
                            error=None if success else f"HTTP {response.status}",
                            execution_time_ms=execution_time_ms,
                            exit_code=response.status,
                            metadata={
                                "endpoint": command,
                                "method": method,
                                "status_code": response.status,
                                "attempt": attempt
                            }
                        )

                        await self._log_execution(tool_name, command, result)
                        return result

            except asyncio.TimeoutError:
                execution_time_ms = (time.time() - start_time) * 1000
                if attempt == self.max_retries:
                    self.logger.error(
                        "rest_tool_timeout",
                        tool_name=tool_name,
                        endpoint=command,
                        attempts=attempt
                    )
                    return ExecutionResult(
                        success=False,
                        output="",
                        error=f"Timeout after {self.timeout_seconds}s",
                        execution_time_ms=execution_time_ms,
                        metadata={"timeout": True, "attempts": attempt}
                    )
                else:
                    self.logger.warning(
                        "rest_tool_retry",
                        tool_name=tool_name,
                        attempt=attempt
                    )
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                if attempt == self.max_retries:
                    self.logger.error(
                        "rest_tool_execution_failed",
                        tool_name=tool_name,
                        error=str(e),
                        attempts=attempt
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
        Valida se REST API está acessível via health check.

        Args:
            tool_name: Nome da ferramenta

        Returns:
            True se acessível
        """
        # Nota: URLs de health check devem estar configuradas no tool descriptor
        # Por simplicidade, retorna True (validação real seria via registry)
        return True
