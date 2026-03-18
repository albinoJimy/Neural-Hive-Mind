"""
Cliente MCP (Model Context Protocol) para comunicação com MCP Servers.

Implementa cliente JSON-RPC 2.0 para comunicação com servidores MCP
que seguem o protocolo da Anthropic.
"""
import json
import asyncio
from typing import Any, Optional
from dataclasses import dataclass

import httpx
from structlog import get_logger

from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker

logger = get_logger(__name__)


@dataclass
class MCPTool:
    """Representa uma ferramenta MCP disponível."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPServerInfo:
    """Informações sobre um servidor MCP."""

    name: str
    version: str
    protocol_version: str


class MCPClientError(Exception):
    """Erro base do cliente MCP."""

    pass


class MCPConnectionError(MCPClientError):
    """Erro de conexão com servidor MCP."""

    pass


class MCPToolExecutionError(MCPClientError):
    """Erro na execução de ferramenta MCP."""

    pass


class MCPClient:
    """
    Cliente JSON-RPC 2.0 para servidores MCP.

    Implementa o protocolo Model Context Protocol para comunicação
    com servidores que expõem ferramentas via JSON-RPC.
    """

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        circuit_breaker: Optional[MonitoredCircuitBreaker] = None,
    ):
        """
        Inicializa o cliente MCP.

        Args:
            server_url: URL do servidor MCP (ex: "http://localhost:3000")
            timeout: Timeout em segundos para requisições
            circuit_breaker: Circuit breaker para resiliência (opcional)
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_breaker = circuit_breaker
        self._server_info: Optional[MCPServerInfo] = None
        self._tools: dict[str, MCPTool] = {}
        self._request_id = 0

    async def connect(self) -> None:
        """
        Conecta ao servidor MCP e inicializa.

        Raises:
            MCPConnectionError: Se a conexão falhar
        """
        self._client = httpx.AsyncClient(timeout=self.timeout)

        try:
            # Handshake initialize
            await self._initialize()
            logger.info(
                "mcp_client_connected",
                server=self.server_url,
                server_info=self._server_info,
            )
        except Exception as e:
            await self.close()
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def _initialize(self) -> None:
        """Executa handshake de inicialização MCP."""
        response = await self._send_request(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "queen-agent", "version": "1.0.0"},
            },
        )

        # Parse server info
        server_info = response.get("result", {}).get("serverInfo", {})
        self._server_info = MCPServerInfo(
            name=server_info.get("name", "unknown"),
            version=server_info.get("version", "0.0.0"),
            protocol_version=response.get("result", {}).get(
                "protocolVersion", "2024-11-05"
            ),
        )

        # Carregar ferramentas disponíveis
        await self._load_tools()

    async def _load_tools(self) -> None:
        """Carrega lista de ferramentas disponíveis."""
        response = await self._send_request(method="tools/list", params={})
        tools_data = response.get("result", {}).get("tools", [])

        self._tools = {}
        for tool_data in tools_data:
            tool = MCPTool(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
            )
            self._tools[tool.name] = tool

        logger.debug("mcp_tools_loaded", count=len(self._tools))

    async def close(self) -> None:
        """Fecha a conexão com o servidor MCP."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            logger.info("mcp_client_closed", server=self.server_url)

    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._client is not None

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        Lista todas as ferramentas disponíveis.

        Returns:
            Lista de dicionários com informações das ferramentas
        """
        if not self._tools:
            await self._load_tools()

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Executa uma ferramenta MCP.

        Args:
            tool_name: Nome da ferramenta
            arguments: Argumentos para a ferramenta

        Returns:
            Resultado da execução da ferramenta

        Raises:
            MCPToolExecutionError: Se a execução falhar
            ValueError: Se a ferramenta não existir
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        if self._circuit_breaker:
            async with self._circuit_breaker:
                return await self._execute_tool_internal(tool_name, arguments)
        else:
            return await self._execute_tool_internal(tool_name, arguments)

    async def _execute_tool_internal(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Executa ferramenta sem circuit breaker."""
        try:
            response = await self._send_request(
                method="tools/call",
                params={"name": tool_name, "arguments": arguments},
            )

            result = response.get("result")
            if result is None:
                raise MCPToolExecutionError(
                    f"Tool execution returned no result: {response}"
                )

            # Verificar se há erro no resultado
            if isinstance(result, dict) and result.get("__error"):
                raise MCPToolExecutionError(result.get("__error"))

            logger.debug(
                "mcp_tool_executed",
                tool=tool_name,
                success=True,
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "mcp_tool_http_error",
                tool=tool_name,
                status_code=e.response.status_code,
            )
            raise MCPToolExecutionError(f"HTTP error: {e.response.status_code}") from e
        except Exception as e:
            logger.error(
                "mcp_tool_execution_failed",
                tool=tool_name,
                error=str(e),
            )
            raise MCPToolExecutionError(f"Tool execution failed: {e}") from e

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Envia requisição JSON-RPC 2.0.

        Args:
            method: Método JSON-RPC
            params: Parâmetros da requisição

        Returns:
            Resposta JSON-RPC parseada

        Raises:
            MCPConnectionError: Se a requisição falhar
        """
        if not self._client:
            raise MCPConnectionError("Client not connected")

        self._request_id += 1

        request_payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            response = await self._client.post(
                f"{self.server_url}/mcp/v1",
                json=request_payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result = response.json()

            # Verificar erro JSON-RPC
            if "error" in result:
                raise MCPConnectionError(f"JSON-RPC error: {result['error']}")

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "mcp_http_error",
                method=method,
                status_code=e.response.status_code,
                body=e.response.text,
            )
            raise MCPConnectionError(f"HTTP error: {e.response.status_code}") from e
        except Exception as e:
            logger.error(
                "mcp_request_failed",
                method=method,
                error=str(e),
            )
            raise MCPConnectionError(f"Request failed: {e}") from e

    @property
    def server_info(self) -> Optional[MCPServerInfo]:
        """Informações do servidor conectado."""
        return self._server_info

    @property
    def tools_count(self) -> int:
        """Número de ferramentas disponíveis."""
        return len(self._tools)

    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        Obtém informações de uma ferramenta específica.

        Args:
            tool_name: Nome da ferramenta

        Returns:
            MCPTool ou None se não existir
        """
        return self._tools.get(tool_name)


class MCPClientFactory:
    """
    Factory para criar clientes MCP com configurações padrão.
    """

    @staticmethod
    async def create_client(
        server_url: str,
        timeout: float = 30.0,
        with_circuit_breaker: bool = True,
        use_rest_api: bool = False,
    ) -> "MCPClient | HTTPMCPClient":
        """
        Cria e conecta um cliente MCP.

        Args:
            server_url: URL do servidor MCP
            timeout: Timeout para requisições
            with_circuit_breaker: Se True, cria circuit breaker
            use_rest_api: Se True, usa HTTPMCPClient (REST) em vez de MCPClient (JSON-RPC)

        Returns:
            MCPClient ou HTTPMCPClient conectado e pronto
        """
        circuit_breaker = None
        if with_circuit_breaker:
            from neural_hive_resilience.circuit_breaker import CircuitBreakerConfig

            config = CircuitBreakerConfig(
                failure_threshold=5,
                timeout_seconds=60,
                half_open_attempts=1,
            )
            circuit_breaker = MonitoredCircuitBreaker(
                name=f"mcp-{server_url}",
                config=config,
            )

        if use_rest_api:
            client = HTTPMCPClient(
                server_url=server_url,
                timeout=timeout,
                circuit_breaker=circuit_breaker,
            )
        else:
            client = MCPClient(
                server_url=server_url,
                timeout=timeout,
                circuit_breaker=circuit_breaker,
            )
        await client.connect()
        return client


class HTTPMCPClient:
    """
    Cliente REST para servidores MCP HTTP.

    Implementa comunicação via REST API para servidores MCP
    que não usam o protocolo JSON-RPC stdio.
    """

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        circuit_breaker: Optional[MonitoredCircuitBreaker] = None,
    ):
        """
        Inicializa o cliente HTTP MCP.

        Args:
            server_url: URL do servidor HTTP (ex: "http://scout-mcp-server:8080")
            timeout: Timeout em segundos para requisições
            circuit_breaker: Circuit breaker para resiliência (opcional)
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_breaker = circuit_breaker
        self._server_info: Optional[MCPServerInfo] = None
        self._tools: dict[str, MCPTool] = {}

    async def connect(self) -> None:
        """
        Conecta ao servidor HTTP MCP e inicializa.

        Raises:
            MCPConnectionError: Se a conexão falhar
        """
        self._client = httpx.AsyncClient(timeout=self.timeout)

        try:
            # Health check
            response = await self._client.get(f"{self.server_url}/health")
            response.raise_for_status()

            data = response.json()
            self._server_info = MCPServerInfo(
                name=data.get("server", "unknown"),
                version=data.get("version", "0.0.0"),
                protocol_version="rest-1.0",
            )

            # Carregar ferramentas disponíveis
            await self._load_tools()

            logger.info(
                "http_mcp_client_connected",
                server=self.server_url,
                server_info=self._server_info,
            )
        except Exception as e:
            await self.close()
            raise MCPConnectionError(f"Failed to connect to HTTP MCP server: {e}") from e

    async def _load_tools(self) -> None:
        """Carrega lista de ferramentas disponíveis via REST."""
        response = await self._client.get(f"{self.server_url}/tools")
        response.raise_for_status()

        data = response.json()
        tools_data = data.get("tools", [])

        self._tools = {}
        for tool_data in tools_data:
            tool = MCPTool(
                name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                input_schema={},  # REST API não expõe schema
            )
            self._tools[tool.name] = tool

        logger.debug("http_mcp_tools_loaded", count=len(self._tools))

    async def close(self) -> None:
        """Fecha a conexão com o servidor HTTP."""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            logger.info("http_mcp_client_closed", server=self.server_url)

    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._client is not None

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        Lista todas as ferramentas disponíveis.

        Returns:
            Lista de dicionários com informações das ferramentas
        """
        if not self._tools:
            await self._load_tools()

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Executa uma ferramenta MCP via REST.

        Args:
            tool_name: Nome da ferramenta
            arguments: Argumentos para a ferramenta

        Returns:
            Resultado da execução da ferramenta

        Raises:
            MCPToolExecutionError: Se a execução falhar
            ValueError: Se a ferramenta não existir
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        if self._circuit_breaker:
            async with self._circuit_breaker:
                return await self._execute_tool_internal(tool_name, arguments)
        else:
            return await self._execute_tool_internal(tool_name, arguments)

    async def _execute_tool_internal(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Executa ferramenta via POST /execute."""
        try:
            payload = {"tool": tool_name, "params": arguments}

            response = await self._client.post(
                f"{self.server_url}/execute",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result = response.json()

            # Verificar erro no resultado
            if isinstance(result, dict) and result.get("error"):
                raise MCPToolExecutionError(result.get("error"))

            logger.debug(
                "http_mcp_tool_executed",
                tool=tool_name,
                success=True,
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "http_mcp_tool_http_error",
                tool=tool_name,
                status_code=e.response.status_code,
            )
            raise MCPToolExecutionError(f"HTTP error: {e.response.status_code}") from e
        except Exception as e:
            logger.error(
                "http_mcp_tool_execution_failed",
                tool=tool_name,
                error=str(e),
            )
            raise MCPToolExecutionError(f"Tool execution failed: {e}") from e

    @property
    def server_info(self) -> Optional[MCPServerInfo]:
        """Informações do servidor conectado."""
        return self._server_info

    @property
    def tools_count(self) -> int:
        """Número de ferramentas disponíveis."""
        return len(self._tools)

    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        Obtém informações de uma ferramenta específica.

        Args:
            tool_name: Nome da ferramenta

        Returns:
            MCPTool ou None se não existir
        """
        return self._tools.get(tool_name)
