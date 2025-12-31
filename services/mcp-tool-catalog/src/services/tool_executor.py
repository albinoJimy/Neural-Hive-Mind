"""Tool Executor Service - Arquitetura híbrida com MCP Servers e adapters locais."""
import asyncio
import json
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.models.tool_descriptor import ToolDescriptor
    from src.services.tool_registry import ToolRegistry
    from src.observability.metrics import MCPToolCatalogMetrics
    from src.config.settings import Settings
    from src.adapters.base_adapter import ExecutionResult, BaseToolAdapter
    from src.clients.mcp_server_client import MCPServerClient

logger = structlog.get_logger()


class ToolExecutor:
    """
    Executor de ferramentas MCP com arquitetura híbrida.

    Prioridades de execução:
    1. MCP Server (se configurado e disponível)
    2. Adapter Local (CLI/REST/Container)
    3. Fallback (erro se nenhum disponível)

    Graceful degradation: Se MCP Server falhar, usa adapter local automaticamente.
    """

    def __init__(
        self,
        tool_registry: Optional['ToolRegistry'] = None,
        metrics: Optional['MCPToolCatalogMetrics'] = None,
        settings: Optional['Settings'] = None
    ):
        """
        Inicializa o executor com adapters.

        Args:
            tool_registry: Registry para buscar ToolDescriptor e feedback
            metrics: Metrics collector para Prometheus
            settings: Settings para timeouts e configurações
        """
        from src.config import get_settings

        self.tool_registry = tool_registry
        self.metrics = metrics
        self.settings = settings or get_settings()
        self.logger = structlog.get_logger()

        # Inicializar adapters com configurações do settings
        from src.adapters.cli_adapter import CLIAdapter
        from src.adapters.rest_adapter import RESTAdapter
        from src.adapters.container_adapter import ContainerAdapter
        from src.models.tool_descriptor import IntegrationType

        self.cli_adapter = CLIAdapter(
            timeout_seconds=self.settings.TOOL_EXECUTION_TIMEOUT_SECONDS
        )
        self.rest_adapter = RESTAdapter(
            timeout_seconds=60,  # REST APIs geralmente mais rápidas
            max_retries=self.settings.TOOL_RETRY_MAX_ATTEMPTS
        )
        self.container_adapter = ContainerAdapter(
            timeout_seconds=self.settings.TOOL_EXECUTION_TIMEOUT_SECONDS
        )

        # Mapeamento de integration_type → adapter
        self.adapter_map = {
            IntegrationType.CLI: self.cli_adapter,
            IntegrationType.REST_API: self.rest_adapter,
            IntegrationType.CONTAINER: self.container_adapter,
        }

        # Mapeamento tool_id → MCP Server URL (do settings)
        self.mcp_servers_config: Dict[str, str] = self.settings.MCP_SERVERS or {}

        # Dicionário de clientes MCP inicializados (tool_id → MCPServerClient)
        self.mcp_clients: Dict[str, 'MCPServerClient'] = {}

        self.logger.info(
            "tool_executor_initialized",
            adapters=[k.value for k in self.adapter_map.keys()],
            mcp_servers_configured=len(self.mcp_servers_config),
            timeout_seconds=self.settings.TOOL_EXECUTION_TIMEOUT_SECONDS
        )

    async def start(self) -> None:
        """
        Inicializa clientes MCP para ferramentas configuradas.

        Para cada tool_id em MCP_SERVERS, cria e inicia um MCPServerClient.
        Falhas de conexão são logadas mas não bloqueiam o startup (graceful degradation).
        """
        from src.clients.mcp_server_client import MCPServerClient
        from src.clients.mcp_exceptions import MCPTransportError

        if not self.mcp_servers_config:
            self.logger.info("no_mcp_servers_configured", message="Usando apenas adapters locais")
            return

        self.logger.info("initializing_mcp_clients", count=len(self.mcp_servers_config))

        for tool_id, server_url in self.mcp_servers_config.items():
            try:
                client = MCPServerClient(
                    server_url=server_url,
                    transport="http",
                    timeout_seconds=self.settings.MCP_SERVER_TIMEOUT_SECONDS,
                    max_retries=self.settings.MCP_SERVER_MAX_RETRIES,
                    circuit_breaker_threshold=self.settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD,
                    circuit_breaker_timeout=self.settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS
                )

                # Iniciar sessão HTTP
                await client.start()

                # Validar conectividade listando ferramentas
                tools = await client.list_tools()

                self.mcp_clients[tool_id] = client
                self.logger.info(
                    "mcp_client_connected",
                    tool_id=tool_id,
                    server_url=server_url,
                    available_tools=len(tools)
                )

            except MCPTransportError as e:
                self.logger.warning(
                    "mcp_client_connection_failed",
                    tool_id=tool_id,
                    server_url=server_url,
                    error=str(e),
                    message="Ferramenta usará adapter local como fallback"
                )
            except Exception as e:
                self.logger.error(
                    "mcp_client_initialization_error",
                    tool_id=tool_id,
                    server_url=server_url,
                    error=str(e),
                    exception_type=type(e).__name__
                )

        self.logger.info(
            "mcp_clients_initialized",
            configured=len(self.mcp_servers_config),
            connected=len(self.mcp_clients)
        )

    async def stop(self) -> None:
        """
        Fecha gracefully todos os clientes MCP.

        Chamado durante shutdown do serviço para liberar recursos.
        """
        if not self.mcp_clients:
            return

        self.logger.info("stopping_mcp_clients", count=len(self.mcp_clients))

        for tool_id, client in self.mcp_clients.items():
            try:
                await client.stop()
                self.logger.info("mcp_client_stopped", tool_id=tool_id)
            except Exception as e:
                self.logger.warning(
                    "mcp_client_stop_error",
                    tool_id=tool_id,
                    error=str(e)
                )

        self.mcp_clients.clear()
        self.logger.info("mcp_clients_stopped")

    async def execute_tool(
        self,
        tool: 'ToolDescriptor',
        execution_params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> 'ExecutionResult':
        """
        Executa ferramenta usando roteamento híbrido:
        1. MCP Server (se configurado e disponível)
        2. Adapter Local (CLI/REST/Container)
        3. Fallback (erro se nenhum disponível)

        Args:
            tool: ToolDescriptor da ferramenta
            execution_params: Parâmetros de execução
            context: Contexto (working_dir, env_vars, headers, auth_token)

        Returns:
            ExecutionResult com output, error, execution_time_ms
        """
        from src.adapters.base_adapter import ExecutionResult

        start_time = time.time()

        self.logger.info(
            "executing_tool",
            tool_id=tool.tool_id,
            tool_name=tool.tool_name,
            integration_type=tool.integration_type.value,
            category=tool.category.value,
            has_mcp_client=tool.tool_id in self.mcp_clients
        )

        # Prioridade 1: MCP Server (se configurado)
        if tool.tool_id in self.mcp_clients:
            try:
                result = await self._execute_via_mcp(tool, execution_params, context)

                # Registrar métricas e feedback
                await self._record_execution_metrics(tool, result, execution_route="mcp")

                return result

            except Exception as e:
                mcp_failure_time_ms = (time.time() - start_time) * 1000
                mcp_server_url = self.mcp_clients[tool.tool_id].server_url if tool.tool_id in self.mcp_clients else None

                self.logger.warning(
                    "mcp_execution_failed_fallback_to_adapter",
                    tool_id=tool.tool_id,
                    error=str(e),
                    exception_type=type(e).__name__
                )

                # Registrar métricas de falha MCP antes do fallback
                mcp_failure_result = ExecutionResult(
                    success=False,
                    output="",
                    error=str(e),
                    execution_time_ms=mcp_failure_time_ms,
                    metadata={
                        "tool_id": tool.tool_id,
                        "execution_route": "mcp",
                        "mcp_server": mcp_server_url,
                        "exception": type(e).__name__
                    }
                )
                await self._record_execution_metrics(tool, mcp_failure_result, execution_route="mcp")

                # Incrementar contador de fallback MCP → adapter
                if self.metrics:
                    reason = f"mcp_error:{type(e).__name__}"
                    self.metrics.record_mcp_fallback(tool.tool_id, reason)

                # Continuar para adapter local (graceful degradation)

        # Prioridade 2: Adapter Local
        adapter = self.adapter_map.get(tool.integration_type)

        if adapter:
            try:
                result = await self._execute_via_adapter(tool, execution_params, context, adapter)

                # Registrar métricas e feedback
                await self._record_execution_metrics(tool, result, execution_route="adapter")

                return result

            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                self.logger.error(
                    "adapter_execution_failed",
                    tool_id=tool.tool_id,
                    error=str(e),
                    exception_type=type(e).__name__,
                    adapter_type=tool.integration_type.value
                )

                # Registrar falha com adapter_type para métricas híbridas
                error_result = ExecutionResult(
                    success=False,
                    output="",
                    error=str(e),
                    execution_time_ms=execution_time_ms,
                    metadata={
                        "tool_id": tool.tool_id,
                        "adapter_type": tool.integration_type.value,
                        "execution_route": "adapter",
                        "exception": type(e).__name__
                    }
                )
                await self._record_execution_metrics(tool, error_result, execution_route="adapter")

                return error_result

        # Prioridade 3: Fallback (nenhum executor disponível)
        execution_time_ms = (time.time() - start_time) * 1000
        self.logger.error(
            "no_executor_available",
            tool_id=tool.tool_id,
            integration_type=tool.integration_type.value,
            has_mcp_client=tool.tool_id in self.mcp_clients,
            available_adapters=[k.value for k in self.adapter_map.keys()]
        )

        fallback_result = ExecutionResult(
            success=False,
            output="",
            error=f"No executor available for {tool.tool_name} (integration_type: {tool.integration_type.value})",
            execution_time_ms=execution_time_ms,
            metadata={"tool_id": tool.tool_id, "execution_route": "fallback"}
        )

        # Registrar métricas e feedback para rota de fallback
        await self._record_execution_metrics(tool, fallback_result, execution_route="fallback")

        return fallback_result

    async def _execute_via_mcp(
        self,
        tool: 'ToolDescriptor',
        execution_params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> 'ExecutionResult':
        """
        Executa ferramenta via MCP Server externo.

        Args:
            tool: ToolDescriptor
            execution_params: Parâmetros para tools/call
            context: Contexto (não usado em MCP, mas mantido para consistência)

        Returns:
            ExecutionResult convertido de MCPToolCallResponse

        Raises:
            MCPError: Erros de transporte, protocolo ou servidor
        """
        from src.adapters.base_adapter import ExecutionResult
        from src.clients.mcp_exceptions import MCPError

        client = self.mcp_clients[tool.tool_id]
        start_time = time.time()

        try:
            # Chamar ferramenta via MCP
            mcp_response = await client.call_tool(
                tool_name=tool.tool_name,
                arguments=execution_params
            )

            execution_time_ms = (time.time() - start_time) * 1000

            # Converter MCPToolCallResponse para ExecutionResult
            # Concatenar todos os content items em output
            output_parts = []
            for content_item in mcp_response.content:
                if content_item.text:
                    output_parts.append(content_item.text)
                elif content_item.data:
                    output_parts.append(json.dumps(content_item.data))

            output = "\n".join(output_parts)

            # Adicionar structuredContent ao metadata se presente
            metadata = {
                "tool_id": tool.tool_id,
                "execution_route": "mcp",
                "mcp_server": client.server_url
            }
            if mcp_response.structuredContent:
                metadata["structured_content"] = mcp_response.structuredContent

            result = ExecutionResult(
                success=not mcp_response.isError,
                output=output,
                error=None if not mcp_response.isError else output,
                execution_time_ms=execution_time_ms,
                exit_code=0 if not mcp_response.isError else 1,
                metadata=metadata
            )

            self.logger.info(
                "mcp_tool_executed",
                tool_id=tool.tool_id,
                tool_name=tool.tool_name,
                success=result.success,
                execution_time_ms=execution_time_ms,
                mcp_server=client.server_url
            )

            return result

        except MCPError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "mcp_tool_execution_error",
                tool_id=tool.tool_id,
                error=str(e),
                error_code=e.code,
                mcp_server=client.server_url
            )

            # Re-raise para permitir fallback para adapter local
            raise

    async def _execute_via_adapter(
        self,
        tool: 'ToolDescriptor',
        execution_params: Dict[str, Any],
        context: Dict[str, Any],
        adapter: 'BaseToolAdapter'
    ) -> 'ExecutionResult':
        """
        Executa ferramenta via adapter local (CLI/REST/Container).

        Args:
            tool: ToolDescriptor
            execution_params: Parâmetros de execução
            context: Contexto (working_dir, env_vars, headers, auth_token)
            adapter: Adapter selecionado (CLI/REST/Container)

        Returns:
            ExecutionResult
        """
        from src.adapters.base_adapter import ExecutionResult

        # Construir comando baseado em integration_type
        command = self._build_command(tool, execution_params)

        # Validar disponibilidade usando o comando efetivo
        try:
            is_available = await adapter.validate_tool_availability(command)
            if not is_available:
                self.logger.warning(
                    "tool_not_available",
                    tool_name=tool.tool_name,
                    effective_command=command,
                    integration_type=tool.integration_type.value
                )
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Tool {tool.tool_name} not available (command: {command})",
                    execution_time_ms=0,
                    metadata={
                        "tool_id": tool.tool_id,
                        "validation_failed": True,
                        "effective_command": command,
                        "execution_route": "adapter"
                    }
                )
        except Exception as e:
            self.logger.warning(
                "tool_availability_check_failed",
                tool_name=tool.tool_name,
                effective_command=command,
                error=str(e)
            )
            # Continuar mesmo se validação falhar (pode ser falso negativo)

        # Executar ferramenta via adapter
        result = await adapter.execute(
            tool_id=tool.tool_id,
            tool_name=tool.tool_name,
            command=command,
            parameters=execution_params,
            context=context
        )

        # Adicionar execution_route ao metadata
        if result.metadata is None:
            result.metadata = {}
        result.metadata["execution_route"] = "adapter"
        result.metadata["adapter_type"] = tool.integration_type.value

        self.logger.info(
            "adapter_tool_executed",
            tool_id=tool.tool_id,
            tool_name=tool.tool_name,
            success=result.success,
            execution_time_ms=result.execution_time_ms,
            exit_code=result.exit_code,
            adapter_type=tool.integration_type.value
        )

        return result

    async def _record_execution_metrics(
        self,
        tool: 'ToolDescriptor',
        result: 'ExecutionResult',
        execution_route: str
    ) -> None:
        """
        Registra métricas Prometheus e atualiza reputação da ferramenta.

        Args:
            tool: ToolDescriptor
            result: ExecutionResult
            execution_route: 'mcp', 'adapter', ou 'fallback'
        """
        # Registrar métricas Prometheus (se disponível)
        if self.metrics:
            status = "success" if result.success else "failure"

            # Extrair informações do metadata
            adapter_type = result.metadata.get("adapter_type") if result.metadata else None
            mcp_server = result.metadata.get("mcp_server") if result.metadata else None

            self.metrics.record_tool_execution(
                tool_id=tool.tool_id,
                category=tool.category.value,
                status=status,
                duration=result.execution_time_ms / 1000.0,
                execution_route=execution_route,
                adapter_type=adapter_type,
                mcp_server=mcp_server
            )

        # Atualizar reputação da ferramenta via feedback loop
        if self.tool_registry:
            metadata = result.metadata or {}
            metadata["execution_route"] = execution_route

            await self.tool_registry.update_tool_metrics(
                tool_id=tool.tool_id,
                category=tool.category.value,
                success=result.success,
                execution_time_ms=int(result.execution_time_ms),
                metadata=metadata
            )

    def _build_command(
        self,
        tool: 'ToolDescriptor',
        execution_params: Dict[str, Any]
    ) -> str:
        """
        Constrói comando/URL baseado em integration_type.

        Args:
            tool: ToolDescriptor
            execution_params: Parâmetros de execução

        Returns:
            Comando CLI, URL REST, ou Docker image
        """
        from src.models.tool_descriptor import IntegrationType

        if tool.integration_type == IntegrationType.CLI:
            # Para CLI, usar cli_command do metadata ou tool_name
            base_cmd = tool.metadata.get("cli_command", tool.tool_name.lower())
            return base_cmd

        elif tool.integration_type == IntegrationType.REST_API:
            # Para REST, usar endpoint_url do descriptor
            if tool.endpoint_url:
                return tool.endpoint_url
            else:
                self.logger.warning(
                    "missing_endpoint_url",
                    tool_id=tool.tool_id,
                    tool_name=tool.tool_name
                )
                return "http://localhost"  # Fallback

        elif tool.integration_type == IntegrationType.CONTAINER:
            # Para Container, usar docker_image do metadata
            docker_image = tool.metadata.get("docker_image")
            if docker_image:
                return docker_image
            else:
                # Fallback: inferir do tool_name
                return f"{tool.tool_name.lower()}:latest"

        else:
            return tool.tool_name.lower()

    async def execute_tools_batch(
        self,
        tools: List['ToolDescriptor'],
        execution_params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, 'ExecutionResult']:
        """
        Executa múltiplas ferramentas em paralelo com controle de concorrência.

        Args:
            tools: Lista de ToolDescriptor
            execution_params: Parâmetros de execução compartilhados
            context: Contexto compartilhado

        Returns:
            Dict mapeando tool_id → ExecutionResult
        """
        from src.adapters.base_adapter import ExecutionResult

        self.logger.info("executing_tools_batch", count=len(tools))

        # Criar semáforo para limitar concorrência
        semaphore = asyncio.Semaphore(self.settings.MAX_CONCURRENT_TOOL_EXECUTIONS)

        async def execute_with_semaphore(tool: 'ToolDescriptor'):
            """Wrapper para executar com semáforo."""
            async with semaphore:
                return await self.execute_tool(tool, execution_params, context)

        # Executar em paralelo com limite de concorrência
        tasks = [execute_with_semaphore(tool) for tool in tools]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Mapear resultados por tool_id
        results_map = {}
        for tool, result in zip(tools, results):
            if isinstance(result, Exception):
                self.logger.error(
                    "batch_execution_exception",
                    tool_id=tool.tool_id,
                    error=str(result)
                )
                results_map[tool.tool_id] = ExecutionResult(
                    success=False,
                    output="",
                    error=str(result),
                    execution_time_ms=0,
                    metadata={"exception": type(result).__name__}
                )
            else:
                results_map[tool.tool_id] = result

        successful = sum(1 for r in results_map.values() if r.success)
        self.logger.info(
            "tools_batch_completed",
            total=len(tools),
            successful=successful,
            failed=len(tools) - successful
        )

        return results_map
