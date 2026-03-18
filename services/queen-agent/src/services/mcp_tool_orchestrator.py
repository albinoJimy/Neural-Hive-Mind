# MCP Tool Orchestrator

import asyncio
from collections import defaultdict
from typing import Any

from neural_hive_observability import get_logger

logger = get_logger(__name__)


class MCPToolOrchestrator:
    """
    Orquestra execução de ferramentas MCP em múltiplos servidores.

    Permite execução paralela e sequencial de ferramentas,
    com agregação de resultados.
    """

    def __init__(
        self,
        scout_client: Any | None = None,
        optimizer_client: Any | None = None,
    ) -> None:
        """
        Inicializa o orquestrador.

        Args:
            scout_client: Cliente MCP para Scout Server
            optimizer_client: Cliente MCP para Optimizer Server
        """
        self._clients: dict[str, Any] = {}

        if scout_client is not None:
            self._clients["scout"] = scout_client
        if optimizer_client is not None:
            self._clients["optimizer"] = optimizer_client

    def register_client(self, server_name: str, client: Any) -> None:
        """
        Registra um cliente MCP.

        Args:
            server_name: Nome do servidor (ex: "scout", "optimizer")
            client: Instância do MCPClient
        """
        self._clients[server_name] = client

    async def get_available_tools(self) -> dict[str, list[dict[str, Any]]]:
        """
        Lista ferramentas disponíveis em todos os servidores.

        Returns:
            Dicionário {server_name: [tools]}
        """
        all_tools: dict[str, list[dict[str, Any]]] = {}

        for server_name, client in self._clients.items():
            try:
                tools = await client.list_tools()
                all_tools[server_name] = tools
            except Exception as e:
                logger.warning("failed_to_list_tools", server=server_name, error=str(e))
                all_tools[server_name] = []

        return all_tools

    async def execute_tools_parallel(
        self,
        requests: list[dict[str, Any]],
        continue_on_error: bool = False,
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Executa múltiplas ferramentas em paralelo.

        Args:
            requests: Lista de {server, tool_name, params}
            continue_on_error: Continuar execução mesmo com erros
            max_concurrency: Máximo de execuções paralelas

        Returns:
            Lista de resultados {server, tool_name, status, result/error}

        Raises:
            ValueError: Servidor desconhecido
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def execute_one(req: dict[str, Any]) -> dict[str, Any]:
            server = req["server"]
            tool_name = req["tool_name"]
            params = req.get("params", {})

            if server not in self._clients:
                raise ValueError(f"Unknown MCP server: {server}")

            async with semaphore:
                try:
                    client = self._clients[server]
                    result = await client.execute_tool(tool_name, params)
                    return {
                        "server": server,
                        "tool_name": tool_name,
                        "status": "success",
                        "result": result,
                    }
                except Exception as e:
                    if not continue_on_error:
                        raise
                    logger.warning(
                        "tool_execution_failed",
                        server=server,
                        tool=tool_name,
                        error=str(e),
                    )
                    return {
                        "server": server,
                        "tool_name": tool_name,
                        "status": "error",
                        "error": str(e),
                    }

        results = await asyncio.gather(
            *[execute_one(req) for req in requests], return_exceptions=True
        )

        # Process exceptions
        processed_results: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                if continue_on_error:
                    processed_results.append(
                        {
                            "server": requests[i]["server"],
                            "tool_name": requests[i]["tool_name"],
                            "status": "error",
                            "error": str(result),
                        }
                    )
                else:
                    raise result
            else:
                processed_results.append(result)

        return processed_results

    async def execute_tools_sequence(
        self,
        requests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Executa múltiplas ferramentas sequencialmente.

        Args:
            requests: Lista de {server, tool_name, params}

        Returns:
            Lista de resultados {server, tool_name, status, result/error}
        """
        results: list[dict[str, Any]] = []

        for req in requests:
            server = req["server"]
            tool_name = req["tool_name"]
            params = req.get("params", {})

            if server not in self._clients:
                raise ValueError(f"Unknown MCP server: {server}")

            try:
                client = self._clients[server]
                result = await client.execute_tool(tool_name, params)
                results.append(
                    {
                        "server": server,
                        "tool_name": tool_name,
                        "status": "success",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.warning(
                    "tool_execution_failed",
                    server=server,
                    tool=tool_name,
                    error=str(e),
                )
                results.append(
                    {
                        "server": server,
                        "tool_name": tool_name,
                        "status": "error",
                        "error": str(e),
                    }
                )

        return results

    async def aggregate_results(
        self,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Agrega resultados de múltiplas execuções.

        Args:
            results: Lista de resultados de execute_tools_*

        Returns:
            Dicionário com agregações:
            - total_count: número total de execuções
            - success_count: execuções bem-sucedidas
            - error_count: execuções com erro
            - by_server: contagem por servidor
            - by_tool: contagem por ferramenta
        """
        by_server: dict[str, int] = defaultdict(int)
        by_tool: dict[str, int] = defaultdict(int)

        success_count = 0
        error_count = 0

        for result in results:
            server = result["server"]
            tool_name = result["tool_name"]
            status = result["status"]

            by_server[server] += 1
            by_tool[tool_name] += 1

            if status == "success":
                success_count += 1
            else:
                error_count += 1

        return {
            "total_count": len(results),
            "success_count": success_count,
            "error_count": error_count,
            "by_server": dict(by_server),
            "by_tool": dict(by_tool),
        }
