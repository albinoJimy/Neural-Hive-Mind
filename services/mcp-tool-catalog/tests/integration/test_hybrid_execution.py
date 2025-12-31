"""
Testes de integracao para execucao hibrida (MCP Server + Adapter).

Cenarios:
- MCP Server disponivel -> usa MCP
- MCP Server indisponivel -> fallback para adapter
- Graceful degradation com multiplos MCP servers
- Metricas hibridas
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from src.services.tool_executor import ToolExecutor
from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType
from src.adapters.base_adapter import ExecutionResult


# ============================================================================
# Fixtures de Mock MCP Server
# ============================================================================

@pytest.fixture
def mcp_server_app():
    """
    Aplicacao aiohttp.web simulando MCP Server (JSON-RPC 2.0).
    """
    app = web.Application()

    async def jsonrpc_handler(request):
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            })

        method = data.get("method")
        params = data.get("params", {})
        request_id = data.get("id", 1)

        if method == "tools/list":
            return web.json_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "trivy-scan",
                            "description": "Security scanner",
                            "inputSchema": {"type": "object"}
                        }
                    ]
                }
            })

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            return web.json_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"MCP executed {tool_name}: success"
                        }
                    ],
                    "structuredContent": {"via": "mcp"},
                    "isError": False
                }
            })

        return web.json_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"}
        })

    app.router.add_post("/", jsonrpc_handler)
    return app


@pytest.fixture
def failing_mcp_server_app():
    """MCP Server que sempre falha."""
    app = web.Application()

    async def error_handler(request):
        return web.json_response(
            {"error": "Service Unavailable"},
            status=503
        )

    app.router.add_post("/", error_handler)
    return app


@pytest.fixture
def slow_mcp_server_app():
    """MCP Server que responde lentamente."""
    app = web.Application()

    async def slow_handler(request):
        await asyncio.sleep(10)  # Muito lento
        return web.json_response({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"slow": True}
        })

    app.router.add_post("/", slow_handler)
    return app


@pytest.fixture
async def mcp_server(mcp_server_app, aiohttp_server):
    """Mock MCP Server rodando."""
    return await aiohttp_server(mcp_server_app)


@pytest.fixture
async def failing_mcp_server(failing_mcp_server_app, aiohttp_server):
    """Mock MCP Server que falha."""
    return await aiohttp_server(failing_mcp_server_app)


@pytest.fixture
async def slow_mcp_server(slow_mcp_server_app, aiohttp_server):
    """Mock MCP Server lento."""
    return await aiohttp_server(slow_mcp_server_app)


# ============================================================================
# Fixtures de ToolDescriptor
# ============================================================================

@pytest.fixture
def trivy_tool():
    """Ferramenta Trivy para testes."""
    return ToolDescriptor(
        tool_id="trivy-001",
        tool_name="trivy",
        category=ToolCategory.SECURITY,
        version="0.45.0",
        capabilities=["vulnerability_scan"],
        reputation_score=0.92,
        cost_score=0.15,
        average_execution_time_ms=60000,
        integration_type=IntegrationType.CONTAINER,
        authentication_method="NONE",
        is_healthy=True,
        metadata={"docker_image": "aquasec/trivy:latest"}
    )


@pytest.fixture
def cli_tool():
    """Ferramenta CLI para testes."""
    return ToolDescriptor(
        tool_id="pytest-001",
        tool_name="pytest",
        category=ToolCategory.VALIDATION,
        version="7.4.0",
        capabilities=["unit_testing"],
        reputation_score=0.9,
        cost_score=0.1,
        average_execution_time_ms=5000,
        integration_type=IntegrationType.CLI,
        authentication_method="NONE",
        is_healthy=True,
        metadata={"cli_command": "pytest"}
    )


# ============================================================================
# Fixtures de ToolExecutor
# ============================================================================

@pytest.fixture
def mock_metrics():
    """Mock de metricas."""
    metrics = MagicMock()
    metrics.record_tool_execution = MagicMock()
    metrics.record_mcp_fallback = MagicMock()
    return metrics


@pytest.fixture
def mock_registry():
    """Mock de registry."""
    registry = MagicMock()
    registry.update_tool_metrics = AsyncMock()
    return registry


# ============================================================================
# Testes de Fallback MCP -> Adapter
# ============================================================================

class TestMCPFallback:
    """Testes de fallback de MCP para adapter."""

    @pytest.mark.asyncio
    async def test_mcp_server_down_fallback_to_cli_adapter(
        self, failing_mcp_server, cli_tool, mock_metrics, mock_registry
    ):
        """Testa fallback quando MCP server esta down."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 5
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "pytest-001": f"http://{failing_mcp_server.host}:{failing_mcp_server.port}"
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            # Iniciar executor (vai falhar ao conectar MCP)
            await executor.start()

            # Mockar adapter CLI para sucesso
            mock_result = ExecutionResult(
                success=True,
                output="CLI adapter executed successfully",
                execution_time_ms=1000.0,
                exit_code=0
            )

            with patch.object(
                executor.cli_adapter,
                "execute",
                return_value=mock_result
            ):
                with patch.object(
                    executor.cli_adapter,
                    "validate_tool_availability",
                    return_value=True
                ):
                    result = await executor.execute_tool(
                        tool=cli_tool,
                        execution_params={},
                        context={}
                    )

                    # Deve usar adapter como fallback
                    assert result.success is True
                    assert "CLI adapter" in result.output
                    assert result.metadata.get("execution_route") == "adapter"

            await executor.stop()

    @pytest.mark.asyncio
    async def test_mcp_server_timeout_fallback_to_container_adapter(
        self, slow_mcp_server, trivy_tool, mock_metrics, mock_registry
    ):
        """Testa fallback quando MCP server timeout."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 1  # Timeout rapido
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "trivy-001": f"http://{slow_mcp_server.host}:{slow_mcp_server.port}"
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            # Mockar adapter Container para sucesso
            mock_result = ExecutionResult(
                success=True,
                output="Container adapter: scan completed",
                execution_time_ms=5000.0,
                exit_code=0
            )

            with patch.object(
                executor.container_adapter,
                "execute",
                return_value=mock_result
            ):
                with patch.object(
                    executor.container_adapter,
                    "validate_tool_availability",
                    return_value=True
                ):
                    result = await executor.execute_tool(
                        tool=trivy_tool,
                        execution_params={"image": "nginx:latest"},
                        context={}
                    )

                    # Deve usar adapter como fallback
                    assert result.success is True
                    assert "Container adapter" in result.output

            await executor.stop()


# ============================================================================
# Testes de Graceful Degradation
# ============================================================================

class TestGracefulDegradation:
    """Testes de degradacao graceful."""

    @pytest.mark.asyncio
    async def test_partial_mcp_servers_available(
        self, mcp_server, failing_mcp_server, mock_metrics, mock_registry
    ):
        """Testa com alguns MCP servers down, outros funcionando."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 5
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "trivy-001": f"http://{mcp_server.host}:{mcp_server.port}",
            "sonarqube-001": f"http://{failing_mcp_server.host}:{failing_mcp_server.port}"
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            await executor.start()

            # Apenas trivy-001 deve estar conectado
            assert "trivy-001" in executor.mcp_clients
            # sonarqube-001 falhou na conexao, mas nao bloqueou startup

            await executor.stop()

    @pytest.mark.asyncio
    async def test_all_mcp_servers_down_use_adapters(
        self, failing_mcp_server, trivy_tool, mock_metrics, mock_registry
    ):
        """Testa com todos MCP servers down -> usa adapters."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 1
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "trivy-001": f"http://{failing_mcp_server.host}:{failing_mcp_server.port}",
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            await executor.start()

            # Nenhum MCP client conectado
            assert len(executor.mcp_clients) == 0

            # Mas execucao ainda funciona via adapter
            mock_result = ExecutionResult(
                success=True,
                output="Adapter fallback success",
                execution_time_ms=1000.0
            )

            with patch.object(
                executor.container_adapter,
                "execute",
                return_value=mock_result
            ):
                with patch.object(
                    executor.container_adapter,
                    "validate_tool_availability",
                    return_value=True
                ):
                    result = await executor.execute_tool(
                        tool=trivy_tool,
                        execution_params={},
                        context={}
                    )

                    assert result.success is True

            await executor.stop()


# ============================================================================
# Testes de Metricas Hibridas
# ============================================================================

class TestHybridMetrics:
    """Testes de metricas para execucao hibrida."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_mcp_execution(
        self, mcp_server, trivy_tool, mock_metrics, mock_registry
    ):
        """Testa metricas registradas para execucao MCP."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 30
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "trivy-001": f"http://{mcp_server.host}:{mcp_server.port}"
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            await executor.start()

            result = await executor.execute_tool(
                tool=trivy_tool,
                execution_params={"image": "nginx:latest"},
                context={}
            )

            # Verificar que metricas foram chamadas
            mock_metrics.record_tool_execution.assert_called()

            # Verificar argumentos da chamada
            call_args = mock_metrics.record_tool_execution.call_args
            assert call_args.kwargs["execution_route"] == "mcp"
            assert call_args.kwargs["tool_id"] == "trivy-001"

            await executor.stop()

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_adapter_execution(
        self, cli_tool, mock_metrics, mock_registry
    ):
        """Testa metricas registradas para execucao via adapter."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 30
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {}  # Sem MCP servers

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            mock_result = ExecutionResult(
                success=True,
                output="Adapter success",
                execution_time_ms=1000.0
            )

            with patch.object(
                executor.cli_adapter,
                "execute",
                return_value=mock_result
            ):
                with patch.object(
                    executor.cli_adapter,
                    "validate_tool_availability",
                    return_value=True
                ):
                    await executor.execute_tool(
                        tool=cli_tool,
                        execution_params={},
                        context={}
                    )

                    # Verificar metricas
                    call_args = mock_metrics.record_tool_execution.call_args
                    assert call_args.kwargs["execution_route"] == "adapter"
                    assert call_args.kwargs["adapter_type"] == "CLI"

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_fallback(
        self, failing_mcp_server, trivy_tool, mock_metrics, mock_registry
    ):
        """Testa contador de fallback incrementado."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 1
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "trivy-001": f"http://{failing_mcp_server.host}:{failing_mcp_server.port}"
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            # Mockar MCP client que falha
            from src.clients.mcp_server_client import MCPServerClient
            mock_client = MagicMock(spec=MCPServerClient)
            mock_client.server_url = f"http://{failing_mcp_server.host}:{failing_mcp_server.port}"

            from src.clients.mcp_exceptions import MCPTransportError
            mock_client.call_tool = AsyncMock(
                side_effect=MCPTransportError("Connection failed")
            )
            executor.mcp_clients = {"trivy-001": mock_client}

            mock_result = ExecutionResult(
                success=True,
                output="Fallback success",
                execution_time_ms=1000.0
            )

            with patch.object(
                executor.container_adapter,
                "execute",
                return_value=mock_result
            ):
                with patch.object(
                    executor.container_adapter,
                    "validate_tool_availability",
                    return_value=True
                ):
                    await executor.execute_tool(
                        tool=trivy_tool,
                        execution_params={},
                        context={}
                    )

                    # Verificar que fallback foi registrado
                    mock_metrics.record_mcp_fallback.assert_called()
                    fallback_args = mock_metrics.record_mcp_fallback.call_args
                    assert fallback_args[0][0] == "trivy-001"

            await executor.stop()


# ============================================================================
# Testes de Execucao via MCP Server Real
# ============================================================================

class TestMCPServerExecution:
    """Testes de execucao com MCP server real (mock)."""

    @pytest.mark.asyncio
    async def test_mcp_execution_success(
        self, mcp_server, trivy_tool, mock_metrics, mock_registry
    ):
        """Testa execucao bem-sucedida via MCP server."""
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 1
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 30
        settings.MCP_SERVER_MAX_RETRIES = 1
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {
            "trivy-001": f"http://{mcp_server.host}:{mcp_server.port}"
        }

        with patch("src.services.tool_executor.get_settings", return_value=settings):
            executor = ToolExecutor(
                settings=settings,
                metrics=mock_metrics,
                tool_registry=mock_registry
            )

            await executor.start()

            # Verificar que MCP client foi conectado
            assert "trivy-001" in executor.mcp_clients

            result = await executor.execute_tool(
                tool=trivy_tool,
                execution_params={"image": "nginx:latest"},
                context={}
            )

            assert result.success is True
            assert "MCP executed" in result.output
            assert result.metadata.get("execution_route") == "mcp"

            await executor.stop()
