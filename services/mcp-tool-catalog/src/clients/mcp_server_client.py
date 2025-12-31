"""Cliente para comunicação com servidores MCP via JSON-RPC 2.0.

Este cliente implementa o protocolo Anthropic Model Context Protocol (MCP)
para integração com servidores MCP externos. Suporta retry com exponential
backoff, circuit breaker para resiliência e connection pooling.
"""
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import structlog
from pydantic import ValidationError

from ..models.mcp_messages import (
    MCPContentItem,
    MCPPrompt,
    MCPResourceContent,
    MCPToolCallResponse,
    MCPToolDescriptor,
    MCPToolsListResponse,
)
from .mcp_exceptions import (
    MCPError,
    MCPProtocolError,
    MCPServerError,
    MCPTransportError,
    create_exception_from_error,
)


class MCPServerClient:
    """Cliente para comunicação com servidores MCP via JSON-RPC 2.0."""

    SUPPORTED_TRANSPORTS = ("http", "stdio")

    def __init__(
        self,
        server_url: str,
        transport: str = "http",
        timeout_seconds: int = 30,
        max_retries: int = 3,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 60,
    ) -> None:
        """
        Inicializa o cliente MCP.

        Args:
            server_url: URL do servidor MCP (ex: http://trivy-mcp-server:3000)
            transport: Tipo de transporte ('http' ou 'stdio')
            timeout_seconds: Timeout para requisições HTTP
            max_retries: Número máximo de tentativas com exponential backoff
            circuit_breaker_threshold: Número de falhas para abrir circuit breaker
            circuit_breaker_timeout: Segundos até circuit breaker fechar

        Raises:
            ValueError: Se transport não for 'http' ou 'stdio'.
        """
        if transport not in self.SUPPORTED_TRANSPORTS:
            raise ValueError(
                f"Transport '{transport}' não suportado. "
                f"Use um de: {self.SUPPORTED_TRANSPORTS}"
            )

        self.server_url = server_url.rstrip("/")
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_timeout = circuit_breaker_timeout

        self._request_id: int = 0
        self._session: Optional[aiohttp.ClientSession] = None
        self._circuit_breaker_failures: int = 0
        self._circuit_breaker_open_until: Optional[datetime] = None

        self._logger = structlog.get_logger(__name__).bind(
            server_url=server_url,
            transport=transport,
        )

    async def start(self) -> None:
        """Inicializa sessão HTTP com connection pooling."""
        if self._session is not None:
            return

        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )

        self._logger.info("mcp_client_started")

    async def stop(self) -> None:
        """Fecha sessão HTTP gracefully."""
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._logger.info("mcp_client_stopped")

    async def list_tools(self) -> List[MCPToolDescriptor]:
        """
        Lista ferramentas disponíveis no servidor MCP.

        Returns:
            Lista de descritores de ferramentas.

        Raises:
            MCPTransportError: Erro de transporte ou circuit breaker aberto.
            MCPProtocolError: Resposta inválida do servidor.
            MCPServerError: Erro retornado pelo servidor MCP.
        """
        start_time = time.monotonic()

        result = await self._send_request("tools/list", {})

        try:
            response = MCPToolsListResponse.model_validate(result)
        except ValidationError as e:
            raise MCPProtocolError(
                message="Invalid tools/list response schema",
                data=str(e),
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000
        tool_names = [t.name for t in response.tools]

        self._logger.info(
            "mcp_tools_listed",
            count=len(response.tools),
            tool_names=tool_names,
            elapsed_ms=round(elapsed_ms, 2),
        )

        return response.tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> MCPToolCallResponse:
        """
        Executa ferramenta no servidor MCP.

        Args:
            tool_name: Nome da ferramenta a executar.
            arguments: Argumentos para a ferramenta.

        Returns:
            Resposta da execução da ferramenta.

        Raises:
            ValueError: Se tool_name for vazio.
            MCPTransportError: Erro de transporte ou circuit breaker aberto.
            MCPProtocolError: Resposta inválida do servidor.
            MCPServerError: Erro retornado pelo servidor MCP.
        """
        if not tool_name:
            raise ValueError("tool_name não pode ser vazio")

        start_time = time.monotonic()

        params = {
            "name": tool_name,
            "arguments": arguments,
        }

        result = await self._send_request("tools/call", params)

        try:
            # Parse content items
            content_data = result.get("content", [])
            content = [MCPContentItem.model_validate(item) for item in content_data]

            response = MCPToolCallResponse(
                content=content,
                structuredContent=result.get("structuredContent"),
                isError=result.get("isError", False),
            )
        except ValidationError as e:
            raise MCPProtocolError(
                message="Invalid tools/call response schema",
                data=str(e),
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        if response.isError:
            self._logger.warning(
                "mcp_tool_call_error",
                tool_name=tool_name,
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise MCPServerError(
                message=f"Tool execution failed: {tool_name}",
                code=-32603,
                data=result,
            )

        self._logger.info(
            "mcp_tool_called",
            tool_name=tool_name,
            execution_time_ms=round(elapsed_ms, 2),
            success=True,
        )

        return response

    async def get_resource(self, uri: str) -> MCPResourceContent:
        """
        Obtém recurso contextual do servidor MCP.

        Args:
            uri: URI do recurso a obter.

        Returns:
            Conteúdo do recurso.

        Raises:
            MCPTransportError: Erro de transporte ou circuit breaker aberto.
            MCPProtocolError: Resposta inválida do servidor.
            MCPServerError: Erro retornado pelo servidor MCP.
        """
        start_time = time.monotonic()

        result = await self._send_request("resources/read", {"uri": uri})

        try:
            # O resultado pode vir em 'contents' como array
            contents = result.get("contents", [])
            if contents and isinstance(contents, list) and len(contents) > 0:
                resource_data = contents[0]
            else:
                resource_data = result

            response = MCPResourceContent.model_validate(resource_data)
        except ValidationError as e:
            raise MCPProtocolError(
                message="Invalid resources/read response schema",
                data=str(e),
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000
        size_bytes = len(response.text.encode()) if response.text else 0

        self._logger.info(
            "mcp_resource_read",
            uri=uri,
            mime_type=response.mimeType,
            size_bytes=size_bytes,
            elapsed_ms=round(elapsed_ms, 2),
        )

        return response

    async def list_prompts(self) -> List[MCPPrompt]:
        """
        Lista prompts reutilizáveis disponíveis.

        Returns:
            Lista de prompts disponíveis.

        Raises:
            MCPTransportError: Erro de transporte ou circuit breaker aberto.
            MCPProtocolError: Resposta inválida do servidor.
            MCPServerError: Erro retornado pelo servidor MCP.
        """
        start_time = time.monotonic()

        result = await self._send_request("prompts/list", {})

        try:
            prompts_data = result.get("prompts", [])
            prompts = [MCPPrompt.model_validate(p) for p in prompts_data]
        except ValidationError as e:
            raise MCPProtocolError(
                message="Invalid prompts/list response schema",
                data=str(e),
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        self._logger.info(
            "mcp_prompts_listed",
            count=len(prompts),
            elapsed_ms=round(elapsed_ms, 2),
        )

        return prompts

    async def _send_request(
        self,
        method: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Envia requisição JSON-RPC 2.0 com retry e circuit breaker.

        Args:
            method: Nome do método JSON-RPC.
            params: Parâmetros da requisição.

        Returns:
            Campo 'result' da resposta JSON-RPC.

        Raises:
            MCPTransportError: Erro de transporte ou circuit breaker aberto.
            MCPProtocolError: Resposta JSON inválida.
            MCPServerError: Erro retornado pelo servidor.
        """
        if self.transport == "stdio":
            return await self._send_request_stdio(method, params)
        return await self._send_request_http(method, params)

    async def _send_request_stdio(
        self,
        method: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Envia requisição via transporte stdio.

        Raises:
            NotImplementedError: Transporte stdio ainda não implementado.
        """
        raise NotImplementedError(
            "Transporte stdio ainda não implementado. "
            "Use transport='http' ou contribua com a implementação stdio."
        )

    async def _send_request_http(
        self,
        method: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Envia requisição JSON-RPC 2.0 via HTTP com retry e circuit breaker.

        Args:
            method: Nome do método JSON-RPC.
            params: Parâmetros da requisição.

        Returns:
            Campo 'result' da resposta JSON-RPC.

        Raises:
            MCPTransportError: Erro de transporte ou circuit breaker aberto.
            MCPProtocolError: Resposta JSON inválida.
            MCPServerError: Erro retornado pelo servidor.
        """
        # Verificar circuit breaker
        if self._circuit_breaker_open_until is not None:
            if datetime.now() < self._circuit_breaker_open_until:
                raise MCPTransportError(
                    message="Circuit breaker open",
                    data={
                        "open_until": self._circuit_breaker_open_until.isoformat(),
                        "failures": self._circuit_breaker_failures,
                    },
                )
            # Circuit breaker expirou, resetar
            self._circuit_breaker_open_until = None
            self._circuit_breaker_failures = 0

        if self._session is None:
            await self.start()

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            self._request_id += 1
            current_request_id = self._request_id

            payload = {
                "jsonrpc": "2.0",
                "id": current_request_id,
                "method": method,
                "params": params,
            }

            try:
                async with self._session.post(
                    self.server_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 200:
                        # Resetar circuit breaker em sucesso
                        self._circuit_breaker_failures = 0

                        try:
                            data = await response.json()
                        except json.JSONDecodeError as e:
                            raise MCPProtocolError(
                                message="Invalid JSON response",
                                data=str(e),
                            )

                        # Validar versão JSON-RPC
                        if data.get("jsonrpc") != "2.0":
                            raise MCPProtocolError(
                                message="Invalid or missing 'jsonrpc' version in response",
                                data=data,
                            )

                        # Validar correspondência de ID
                        if data.get("id") != current_request_id:
                            raise MCPProtocolError(
                                message=f"Response ID mismatch: expected {current_request_id}, got {data.get('id')}",
                                data=data,
                            )

                        # Verificar erro JSON-RPC
                        if "error" in data and data["error"] is not None:
                            error = data["error"]
                            raise create_exception_from_error(
                                code=error.get("code", -32603),
                                message=error.get("message", "Unknown error"),
                                data=error.get("data"),
                            )

                        # Verificar campo result
                        if "result" not in data:
                            raise MCPProtocolError(
                                message="Missing 'result' field in response",
                                data=data,
                            )

                        return data["result"]

                    # Status não-200: tratar como erro de servidor
                    self._circuit_breaker_failures += 1
                    last_error = MCPTransportError(
                        message=f"HTTP {response.status}",
                        data=await response.text(),
                    )

            except asyncio.TimeoutError:
                self._circuit_breaker_failures += 1
                last_error = MCPTransportError(message="Request timeout")

            except aiohttp.ClientConnectionError as e:
                self._circuit_breaker_failures += 1
                last_error = MCPTransportError(
                    message="Connection refused",
                    data=str(e),
                )

            except MCPError:
                # Re-raise MCP errors sem retry
                raise

            except Exception as e:
                self._circuit_breaker_failures += 1
                last_error = MCPTransportError(
                    message=f"Unexpected error: {type(e).__name__}",
                    data=str(e),
                )

            # Verificar se deve abrir circuit breaker
            if self._circuit_breaker_failures >= self.circuit_breaker_threshold:
                self._circuit_breaker_open_until = datetime.now() + timedelta(
                    seconds=self.circuit_breaker_timeout
                )
                self._logger.warning(
                    "mcp_circuit_breaker_opened",
                    failures=self._circuit_breaker_failures,
                    open_until=self._circuit_breaker_open_until.isoformat(),
                )

            # Retry com exponential backoff
            if attempt < self.max_retries:
                backoff = 2 ** attempt
                self._logger.warning(
                    "mcp_request_retry",
                    attempt=attempt,
                    method=method,
                    error=str(last_error),
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)

        # Todas tentativas falharam
        if last_error:
            raise last_error

        raise MCPTransportError(message="All retry attempts failed")

    async def __aenter__(self) -> "MCPServerClient":
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.stop()
