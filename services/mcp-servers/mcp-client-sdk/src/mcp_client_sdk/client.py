# MCP Client SDK

import asyncio
from typing import Any

import httpx

from .config import get_config
from .exceptions import MCPConnectionError, MCPResponseError, MCPTimeoutError


class MCPClient:
    """
    Cliente para comunicação com servidores MCP.

    Permite que agentes especializados executem ferramentas
    remotamente via HTTP.
    """

    def __init__(
        self,
        server_url: str,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Inicializa cliente MCP.

        Args:
            server_url: URL base do servidor MCP
            timeout: Timeout em segundos para requisições
            headers: Headers HTTP adicionais
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self._config = get_config()

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        Lista ferramentas disponíveis no servidor.

        Returns:
            Lista de ferramentas com nome e descrição

        Raises:
            MCPConnectionError: Erro de conexão
            MCPTimeoutError: Timeout na requisição
            MCPResponseError: Resposta inválida
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.server_url}/tools", headers=self.headers
                )
                response.raise_for_status()
                data = response.json()
                return data.get("tools", [])

        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Connection error: {e}") from e
        except httpx.TimeoutException as e:
            raise MCPTimeoutError(f"Request timeout: {e}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise MCPResponseError(f"Response error: {e}") from e

    async def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Executa uma ferramenta no servidor MCP.

        Args:
            tool_name: Nome da ferramenta
            params: Parâmetros da ferramenta

        Returns:
            Resultado da execução

        Raises:
            MCPConnectionError: Erro de conexão
            MCPTimeoutError: Timeout na requisição
            MCPResponseError: Resposta inválida
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.server_url}/tools/{tool_name}",
                    json=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()

        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Connection error: {e}") from e
        except httpx.TimeoutException as e:
            raise MCPTimeoutError(f"Request timeout: {e}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise MCPResponseError(f"Response error: {e}") from e

    async def execute_batch(
        self,
        requests: list[dict[str, Any]],
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Executa múltiplas ferramentas em paralelo.

        Args:
            requests: Lista de requisições {tool_name, params}
            max_concurrency: Máximo de execuções paralelas

        Returns:
            Lista de resultados na mesma ordem das requisições

        Raises:
            MCPConnectionError: Erro de conexão
            MCPTimeoutError: Timeout na requisição
            MCPResponseError: Resposta inválida
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def execute_with_limit(req: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self.execute_tool(
                    tool_name=req["tool_name"], params=req.get("params", {})
                )

        try:
            results = await asyncio.gather(
                *[execute_with_limit(req) for req in requests], return_exceptions=True
            )

            # Check for exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    raise result

            return results

        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Connection error: {e}") from e
        except httpx.TimeoutException as e:
            raise MCPTimeoutError(f"Request timeout: {e}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise MCPResponseError(f"Response error: {e}") from e
