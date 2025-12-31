"""
Testes unitarios para ToolExecutor com arquitetura hibrida (MCP + adapters).

Cobertura:
- Roteamento hibrido (MCP Server vs Adapter Local)
- Fallback MCP -> Adapter
- Lifecycle (start/stop MCP clients)
- Metricas Prometheus
- Execucao em batch
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.services.tool_executor import ToolExecutor
from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType
from src.adapters.base_adapter import ExecutionResult, AdapterError


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock de configuracoes completas para ToolExecutor."""
    settings = MagicMock()
    settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
    settings.TOOL_RETRY_MAX_ATTEMPTS = 3
    settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
    settings.MCP_SERVER_TIMEOUT_SECONDS = 30
    settings.MCP_SERVER_MAX_RETRIES = 3
    settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
    settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
    settings.MCP_SERVERS = {}  # Sem MCP servers por padrao
    return settings


@pytest.fixture
def mock_settings_with_mcp():
    """Mock de configuracoes com MCP servers configurados."""
    settings = MagicMock()
    settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
    settings.TOOL_RETRY_MAX_ATTEMPTS = 3
    settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
    settings.MCP_SERVER_TIMEOUT_SECONDS = 30
    settings.MCP_SERVER_MAX_RETRIES = 3
    settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
    settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
    settings.MCP_SERVERS = {
        "trivy-001": "http://trivy-mcp-server:3000",
        "sonarqube-001": "http://sonarqube-mcp-server:3000"
    }
    return settings


@pytest.fixture
def mock_metrics():
    """Mock de MCPToolCatalogMetrics."""
    metrics = MagicMock()
    metrics.record_tool_execution = MagicMock()
    metrics.record_mcp_fallback = MagicMock()
    metrics.record_feedback = MagicMock()
    return metrics


@pytest.fixture
def mock_tool_registry():
    """Mock de ToolRegistry."""
    registry = MagicMock()
    registry.update_tool_metrics = AsyncMock()
    return registry


@pytest.fixture
def mock_mcp_client():
    """Mock de MCPServerClient."""
    client = MagicMock()
    client.server_url = "http://test-mcp:3000"
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.list_tools = AsyncMock(return_value=[
        MagicMock(name="trivy-scan", description="Security scan"),
    ])
    client.call_tool = AsyncMock()
    return client


@pytest.fixture
def tool_executor(mock_settings):
    """ToolExecutor basico sem MCP servers."""
    with patch("src.services.tool_executor.get_settings", return_value=mock_settings):
        executor = ToolExecutor(settings=mock_settings)
        return executor


@pytest.fixture
def tool_executor_with_mcp(mock_settings_with_mcp, mock_metrics, mock_tool_registry):
    """ToolExecutor com MCP servers configurados."""
    with patch("src.services.tool_executor.get_settings", return_value=mock_settings_with_mcp):
        executor = ToolExecutor(
            settings=mock_settings_with_mcp,
            metrics=mock_metrics,
            tool_registry=mock_tool_registry
        )
        return executor


@pytest.fixture
def cli_tool():
    """Fixture de ferramenta CLI."""
    return ToolDescriptor(
        tool_id="pytest-001",
        tool_name="pytest",
        category=ToolCategory.VALIDATION,
        version="7.4.0",
        capabilities=["unit_testing", "python"],
        reputation_score=0.9,
        cost_score=0.1,
        average_execution_time_ms=5000,
        integration_type=IntegrationType.CLI,
        authentication_method="NONE",
        is_healthy=True,
        metadata={
            "cli_command": "pytest",
            "homepage": "https://pytest.org"
        }
    )


@pytest.fixture
def rest_tool():
    """Fixture de ferramenta REST API."""
    return ToolDescriptor(
        tool_id="sonarqube-001",
        tool_name="sonarqube",
        category=ToolCategory.ANALYSIS,
        version="9.9.0",
        capabilities=["static_analysis", "code_quality"],
        reputation_score=0.95,
        cost_score=0.2,
        average_execution_time_ms=30000,
        integration_type=IntegrationType.REST_API,
        authentication_method="API_KEY",
        is_healthy=True,
        endpoint_url="http://sonarqube:9000/api/analysis",
        metadata={"homepage": "https://sonarqube.org"}
    )


@pytest.fixture
def container_tool():
    """Fixture de ferramenta Container."""
    return ToolDescriptor(
        tool_id="trivy-001",
        tool_name="trivy",
        category=ToolCategory.SECURITY,
        version="0.45.0",
        capabilities=["vulnerability_scan", "container_security"],
        reputation_score=0.92,
        cost_score=0.15,
        average_execution_time_ms=60000,
        integration_type=IntegrationType.CONTAINER,
        authentication_method="NONE",
        is_healthy=True,
        metadata={
            "docker_image": "aquasec/trivy:latest",
            "homepage": "https://trivy.dev"
        }
    )


@pytest.fixture
def mcp_tool():
    """Fixture de ferramenta com MCP Server configurado."""
    return ToolDescriptor(
        tool_id="trivy-001",  # Mesmo ID do container tool, mas com MCP
        tool_name="trivy",
        category=ToolCategory.SECURITY,
        version="0.45.0",
        capabilities=["vulnerability_scan", "container_security"],
        reputation_score=0.92,
        cost_score=0.15,
        average_execution_time_ms=60000,
        integration_type=IntegrationType.CONTAINER,
        authentication_method="NONE",
        is_healthy=True,
        metadata={
            "docker_image": "aquasec/trivy:latest",
            "mcp_server": "http://trivy-mcp-server:3000"
        }
    )


@pytest.fixture
def mock_execution_result():
    """ExecutionResult de exemplo bem-sucedido."""
    return ExecutionResult(
        success=True,
        output="All tests passed - 42 tests in 3.5s",
        error=None,
        execution_time_ms=3500.0,
        exit_code=0,
        metadata={"tests_passed": 42}
    )


@pytest.fixture
def mock_mcp_tool_call_response():
    """MCPToolCallResponse de exemplo."""
    response = MagicMock()
    response.isError = False
    response.content = [
        MagicMock(text="Scan completed: 0 vulnerabilities found", data=None),
    ]
    response.structuredContent = {"vulnerabilities": [], "severity": "none"}
    return response


# ============================================================================
# Testes de Inicializacao
# ============================================================================

class TestToolExecutorInitialization:
    """Testes de inicializacao do ToolExecutor."""

    def test_init_creates_adapters(self, tool_executor):
        """Verifica que adapters sao criados na inicializacao."""
        assert tool_executor.cli_adapter is not None
        assert tool_executor.rest_adapter is not None
        assert tool_executor.container_adapter is not None

    def test_init_creates_adapter_map(self, tool_executor):
        """Verifica que adapter_map e populado corretamente."""
        assert IntegrationType.CLI in tool_executor.adapter_map
        assert IntegrationType.REST_API in tool_executor.adapter_map
        assert IntegrationType.CONTAINER in tool_executor.adapter_map

    def test_init_without_mcp_servers(self, tool_executor):
        """Verifica inicializacao sem MCP servers."""
        assert tool_executor.mcp_servers_config == {}
        assert tool_executor.mcp_clients == {}

    def test_init_with_mcp_servers(self, tool_executor_with_mcp):
        """Verifica inicializacao com MCP servers configurados."""
        assert len(tool_executor_with_mcp.mcp_servers_config) == 2
        assert "trivy-001" in tool_executor_with_mcp.mcp_servers_config
        assert "sonarqube-001" in tool_executor_with_mcp.mcp_servers_config


# ============================================================================
# Testes de Lifecycle (start/stop)
# ============================================================================

class TestToolExecutorLifecycle:
    """Testes de lifecycle do ToolExecutor."""

    @pytest.mark.asyncio
    async def test_start_without_mcp_servers(self, tool_executor):
        """Verifica que start() funciona sem MCP servers configurados."""
        await tool_executor.start()
        assert tool_executor.mcp_clients == {}

    @pytest.mark.asyncio
    async def test_start_initializes_mcp_clients(self, tool_executor_with_mcp):
        """Verifica que start() cria clientes MCP."""
        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[MagicMock()])

        with patch(
            "src.services.tool_executor.MCPServerClient",
            return_value=mock_client
        ):
            await tool_executor_with_mcp.start()

            # Verifica que clientes foram criados para cada server configurado
            assert mock_client.start.call_count == 2
            assert mock_client.list_tools.call_count == 2

    @pytest.mark.asyncio
    async def test_start_graceful_degradation_on_connection_failure(
        self, tool_executor_with_mcp
    ):
        """Verifica que falha de conexao nao bloqueia startup."""
        from src.clients.mcp_exceptions import MCPTransportError

        # Primeiro cliente conecta, segundo falha
        call_count = 0

        async def mock_list_tools():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise MCPTransportError("Connection refused")
            return [MagicMock()]

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.list_tools = AsyncMock(side_effect=mock_list_tools)

        with patch(
            "src.services.tool_executor.MCPServerClient",
            return_value=mock_client
        ):
            # Nao deve levantar excecao
            await tool_executor_with_mcp.start()

            # Apenas 1 cliente deve estar conectado
            assert len(tool_executor_with_mcp.mcp_clients) == 1

    @pytest.mark.asyncio
    async def test_stop_closes_mcp_clients(self, tool_executor_with_mcp, mock_mcp_client):
        """Verifica que stop() fecha clientes MCP."""
        # Simular clientes conectados
        tool_executor_with_mcp.mcp_clients = {
            "trivy-001": mock_mcp_client,
            "sonarqube-001": mock_mcp_client
        }

        await tool_executor_with_mcp.stop()

        # Verifica que stop foi chamado para cada cliente
        assert mock_mcp_client.stop.call_count == 2
        assert tool_executor_with_mcp.mcp_clients == {}

    @pytest.mark.asyncio
    async def test_stop_without_clients(self, tool_executor):
        """Verifica que stop() funciona sem clientes."""
        await tool_executor.stop()  # Nao deve levantar excecao
        assert tool_executor.mcp_clients == {}


# ============================================================================
# Testes de Roteamento Hibrido
# ============================================================================

class TestHybridRouting:
    """Testes de roteamento hibrido (MCP Server vs Adapter)."""

    @pytest.mark.asyncio
    async def test_execute_tool_via_mcp_success(
        self, tool_executor_with_mcp, mcp_tool, mock_mcp_client,
        mock_mcp_tool_call_response
    ):
        """Verifica execucao bem-sucedida via MCP Server."""
        # Configurar cliente MCP mockado
        mock_mcp_client.call_tool = AsyncMock(
            return_value=mock_mcp_tool_call_response
        )
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        result = await tool_executor_with_mcp.execute_tool(
            tool=mcp_tool,
            execution_params={"image": "nginx:latest"},
            context={}
        )

        assert result.success is True
        assert "Scan completed" in result.output
        assert result.metadata.get("execution_route") == "mcp"

        # Verifica que call_tool foi chamado
        mock_mcp_client.call_tool.assert_called_once_with(
            tool_name="trivy",
            arguments={"image": "nginx:latest"}
        )

    @pytest.mark.asyncio
    async def test_execute_tool_via_adapter_success(
        self, tool_executor, cli_tool, mock_execution_result
    ):
        """Verifica execucao bem-sucedida via adapter local."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=mock_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                result = await tool_executor.execute_tool(
                    tool=cli_tool,
                    execution_params={"verbose": True},
                    context={"working_dir": "/app"}
                )

                assert result.success is True
                assert result.output == "All tests passed - 42 tests in 3.5s"
                assert result.metadata.get("execution_route") == "adapter"

    @pytest.mark.asyncio
    async def test_execute_tool_mcp_fallback_to_adapter(
        self, tool_executor_with_mcp, mcp_tool, mock_mcp_client
    ):
        """Verifica fallback MCP -> adapter em caso de falha."""
        from src.clients.mcp_exceptions import MCPTransportError

        # MCP falha
        mock_mcp_client.call_tool = AsyncMock(
            side_effect=MCPTransportError("Connection timeout")
        )
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        # Adapter funciona
        mock_adapter_result = ExecutionResult(
            success=True,
            output="Container scan completed via adapter",
            execution_time_ms=5000.0,
            exit_code=0
        )

        with patch.object(
            tool_executor_with_mcp.container_adapter,
            "execute",
            return_value=mock_adapter_result
        ):
            with patch.object(
                tool_executor_with_mcp.container_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                result = await tool_executor_with_mcp.execute_tool(
                    tool=mcp_tool,
                    execution_params={"image": "nginx:latest"},
                    context={}
                )

                assert result.success is True
                assert "Container scan completed via adapter" in result.output
                assert result.metadata.get("execution_route") == "adapter"

                # Verifica que metricas de fallback foram registradas
                tool_executor_with_mcp.metrics.record_mcp_fallback.assert_called()

    @pytest.mark.asyncio
    async def test_execute_tool_no_executor_available(self, tool_executor):
        """Verifica erro quando nenhum executor disponivel."""
        # Ferramenta com tipo nao implementado
        grpc_tool = ToolDescriptor(
            tool_id="grpc-001",
            tool_name="grpc-tool",
            category=ToolCategory.INTEGRATION,
            version="1.0.0",
            capabilities=["rpc"],
            reputation_score=0.8,
            cost_score=0.3,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.GRPC,  # Nao implementado
            authentication_method="NONE",
            is_healthy=True
        )

        result = await tool_executor.execute_tool(
            tool=grpc_tool,
            execution_params={},
            context={}
        )

        assert result.success is False
        assert "No executor available" in result.error
        assert result.metadata.get("execution_route") == "fallback"


# ============================================================================
# Testes de Execucao via Adapter
# ============================================================================

class TestAdapterExecution:
    """Testes de execucao via adapters locais."""

    @pytest.mark.asyncio
    async def test_execute_cli_tool(self, tool_executor, cli_tool, mock_execution_result):
        """Testa execucao de ferramenta CLI."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=mock_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                result = await tool_executor.execute_tool(
                    tool=cli_tool,
                    execution_params={"verbose": True},
                    context={"working_dir": "/app"}
                )

                assert result.success is True
                assert result.execution_time_ms == 3500.0

    @pytest.mark.asyncio
    async def test_execute_rest_tool(self, tool_executor, rest_tool):
        """Testa execucao de ferramenta REST API."""
        rest_result = ExecutionResult(
            success=True,
            output='{"status": "completed", "issues": 0}',
            execution_time_ms=15000.0,
            exit_code=200,
            metadata={"status_code": 200}
        )

        with patch.object(
            tool_executor.rest_adapter,
            "execute",
            return_value=rest_result
        ):
            with patch.object(
                tool_executor.rest_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                result = await tool_executor.execute_tool(
                    tool=rest_tool,
                    execution_params={"project": "my-project"},
                    context={"auth_token": "secret-token"}
                )

                assert result.success is True
                assert "issues" in result.output

    @pytest.mark.asyncio
    async def test_execute_container_tool(self, tool_executor, container_tool):
        """Testa execucao de ferramenta Container."""
        container_result = ExecutionResult(
            success=True,
            output="Scan completed: 0 vulnerabilities",
            execution_time_ms=45000.0,
            exit_code=0
        )

        with patch.object(
            tool_executor.container_adapter,
            "execute",
            return_value=container_result
        ):
            with patch.object(
                tool_executor.container_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                result = await tool_executor.execute_tool(
                    tool=container_tool,
                    execution_params={"image": "nginx:latest"},
                    context={}
                )

                assert result.success is True
                assert "0 vulnerabilities" in result.output

    @pytest.mark.asyncio
    async def test_execute_tool_adapter_failure(self, tool_executor, cli_tool):
        """Testa tratamento de falha do adapter."""
        with patch.object(
            tool_executor.cli_adapter,
            "validate_tool_availability",
            return_value=True
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "execute",
                side_effect=Exception("Adapter execution failed")
            ):
                result = await tool_executor.execute_tool(
                    tool=cli_tool,
                    execution_params={},
                    context={}
                )

                assert result.success is False
                assert "Adapter execution failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_not_available(self, tool_executor, cli_tool):
        """Testa quando ferramenta nao esta disponivel."""
        with patch.object(
            tool_executor.cli_adapter,
            "validate_tool_availability",
            return_value=False
        ):
            result = await tool_executor.execute_tool(
                tool=cli_tool,
                execution_params={},
                context={}
            )

            assert result.success is False
            assert "not available" in result.error


# ============================================================================
# Testes de Metricas
# ============================================================================

class TestMetricsRecording:
    """Testes de registro de metricas Prometheus."""

    @pytest.mark.asyncio
    async def test_record_execution_metrics_mcp(
        self, tool_executor_with_mcp, mcp_tool, mock_mcp_client,
        mock_mcp_tool_call_response
    ):
        """Verifica metricas registradas para execucao MCP."""
        mock_mcp_client.call_tool = AsyncMock(
            return_value=mock_mcp_tool_call_response
        )
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        await tool_executor_with_mcp.execute_tool(
            tool=mcp_tool,
            execution_params={},
            context={}
        )

        # Verifica que metricas foram registradas
        tool_executor_with_mcp.metrics.record_tool_execution.assert_called()
        call_args = tool_executor_with_mcp.metrics.record_tool_execution.call_args

        assert call_args.kwargs["execution_route"] == "mcp"
        assert call_args.kwargs["tool_id"] == "trivy-001"
        assert call_args.kwargs["mcp_server"] == "http://test-mcp:3000"

    @pytest.mark.asyncio
    async def test_record_execution_metrics_adapter(
        self, tool_executor_with_mcp, cli_tool, mock_execution_result
    ):
        """Verifica metricas registradas para execucao via adapter."""
        with patch.object(
            tool_executor_with_mcp.cli_adapter,
            "execute",
            return_value=mock_execution_result
        ):
            with patch.object(
                tool_executor_with_mcp.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                await tool_executor_with_mcp.execute_tool(
                    tool=cli_tool,
                    execution_params={},
                    context={}
                )

                # Verifica que metricas foram registradas
                tool_executor_with_mcp.metrics.record_tool_execution.assert_called()
                call_args = tool_executor_with_mcp.metrics.record_tool_execution.call_args

                assert call_args.kwargs["execution_route"] == "adapter"
                assert call_args.kwargs["adapter_type"] == "CLI"

    @pytest.mark.asyncio
    async def test_record_execution_metrics_fallback(
        self, tool_executor_with_mcp, mcp_tool, mock_mcp_client
    ):
        """Verifica metricas registradas para fallback."""
        from src.clients.mcp_exceptions import MCPTransportError

        mock_mcp_client.call_tool = AsyncMock(
            side_effect=MCPTransportError("Timeout")
        )
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        adapter_result = ExecutionResult(
            success=True,
            output="Success via adapter",
            execution_time_ms=1000.0
        )

        with patch.object(
            tool_executor_with_mcp.container_adapter,
            "execute",
            return_value=adapter_result
        ):
            with patch.object(
                tool_executor_with_mcp.container_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                await tool_executor_with_mcp.execute_tool(
                    tool=mcp_tool,
                    execution_params={},
                    context={}
                )

                # Verifica que record_mcp_fallback foi chamado
                tool_executor_with_mcp.metrics.record_mcp_fallback.assert_called()
                fallback_args = tool_executor_with_mcp.metrics.record_mcp_fallback.call_args

                assert fallback_args[0][0] == "trivy-001"  # tool_id
                assert "mcp_error" in fallback_args[0][1]  # reason


# ============================================================================
# Testes de Feedback Loop
# ============================================================================

class TestFeedbackLoop:
    """Testes de atualizacao de reputacao via feedback loop."""

    @pytest.mark.asyncio
    async def test_feedback_updates_tool_registry(
        self, tool_executor_with_mcp, cli_tool, mock_execution_result
    ):
        """Verifica que feedback atualiza tool registry."""
        with patch.object(
            tool_executor_with_mcp.cli_adapter,
            "execute",
            return_value=mock_execution_result
        ):
            with patch.object(
                tool_executor_with_mcp.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                await tool_executor_with_mcp.execute_tool(
                    tool=cli_tool,
                    execution_params={},
                    context={}
                )

                # Verifica que update_tool_metrics foi chamado
                tool_executor_with_mcp.tool_registry.update_tool_metrics.assert_called()
                call_args = tool_executor_with_mcp.tool_registry.update_tool_metrics.call_args

                assert call_args.kwargs["tool_id"] == "pytest-001"
                assert call_args.kwargs["success"] is True


# ============================================================================
# Testes de Batch Execution
# ============================================================================

class TestBatchExecution:
    """Testes de execucao em batch."""

    @pytest.mark.asyncio
    async def test_execute_tools_batch_parallel(
        self, tool_executor, cli_tool, mock_execution_result
    ):
        """Testa execucao paralela com semaforo."""
        # Criar multiplas ferramentas
        tools = [cli_tool]
        for i in range(2, 4):
            tools.append(ToolDescriptor(
                tool_id=f"tool-{i:03d}",
                tool_name=f"tool-{i}",
                category=ToolCategory.ANALYSIS,
                version="1.0.0",
                capabilities=["test"],
                reputation_score=0.7,
                cost_score=0.2,
                average_execution_time_ms=2000,
                integration_type=IntegrationType.CLI,
                authentication_method="NONE",
                is_healthy=True
            ))

        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=mock_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                results = await tool_executor.execute_tools_batch(
                    tools=tools,
                    execution_params={},
                    context={}
                )

                assert len(results) == 3
                assert all(r.success for r in results.values())

    @pytest.mark.asyncio
    async def test_execute_tools_batch_mixed_routes(
        self, tool_executor_with_mcp, cli_tool, container_tool,
        mock_mcp_client, mock_mcp_tool_call_response, mock_execution_result
    ):
        """Testa batch com MCP + adapters."""
        # Configurar MCP para container_tool (trivy-001)
        mock_mcp_client.call_tool = AsyncMock(
            return_value=mock_mcp_tool_call_response
        )
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        tools = [cli_tool, container_tool]

        with patch.object(
            tool_executor_with_mcp.cli_adapter,
            "execute",
            return_value=mock_execution_result
        ):
            with patch.object(
                tool_executor_with_mcp.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                results = await tool_executor_with_mcp.execute_tools_batch(
                    tools=tools,
                    execution_params={},
                    context={}
                )

                assert len(results) == 2
                # CLI tool via adapter
                assert results["pytest-001"].metadata.get("execution_route") == "adapter"
                # Container tool via MCP
                assert results["trivy-001"].metadata.get("execution_route") == "mcp"

    @pytest.mark.asyncio
    async def test_execute_tools_batch_exception_handling(
        self, tool_executor, cli_tool
    ):
        """Testa que excecoes nao bloqueiam outras execucoes."""
        tools = [cli_tool]
        tools.append(ToolDescriptor(
            tool_id="failing-tool",
            tool_name="failing",
            category=ToolCategory.ANALYSIS,
            version="1.0.0",
            capabilities=["test"],
            reputation_score=0.5,
            cost_score=0.1,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.CLI,
            authentication_method="NONE",
            is_healthy=True
        ))

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Simulated failure")
            return ExecutionResult(
                success=True,
                output="Success",
                execution_time_ms=100.0
            )

        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            side_effect=mock_execute
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                results = await tool_executor.execute_tools_batch(
                    tools=tools,
                    execution_params={},
                    context={}
                )

                assert len(results) == 2
                # Uma ferramenta deve ter sucesso
                assert results["pytest-001"].success is True
                # Uma deve ter falhado
                assert results["failing-tool"].success is False


# ============================================================================
# Testes de Build Command
# ============================================================================

class TestBuildCommand:
    """Testes de construcao de comando para diferentes integration_types."""

    def test_build_command_cli(self, tool_executor, cli_tool):
        """Testa construcao de comando CLI."""
        command = tool_executor._build_command(cli_tool, {})
        assert command == "pytest"

    def test_build_command_cli_custom(self, tool_executor):
        """Testa comando CLI customizado."""
        tool = ToolDescriptor(
            tool_id="custom-001",
            tool_name="custom",
            category=ToolCategory.ANALYSIS,
            version="1.0.0",
            capabilities=["test"],
            reputation_score=0.8,
            cost_score=0.3,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.CLI,
            authentication_method="NONE",
            is_healthy=True,
            metadata={"cli_command": "custom-cmd --flag"}
        )

        command = tool_executor._build_command(tool, {})
        assert command == "custom-cmd --flag"

    def test_build_command_rest(self, tool_executor, rest_tool):
        """Testa construcao de URL REST."""
        command = tool_executor._build_command(rest_tool, {})
        assert command == "http://sonarqube:9000/api/analysis"

    def test_build_command_container(self, tool_executor, container_tool):
        """Testa construcao de comando Container."""
        command = tool_executor._build_command(container_tool, {})
        assert command == "aquasec/trivy:latest"

    def test_build_command_container_fallback(self, tool_executor):
        """Testa fallback para container sem docker_image."""
        tool = ToolDescriptor(
            tool_id="container-001",
            tool_name="MyContainer",
            category=ToolCategory.ANALYSIS,
            version="1.0.0",
            capabilities=["test"],
            reputation_score=0.8,
            cost_score=0.3,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.CONTAINER,
            authentication_method="NONE",
            is_healthy=True,
            metadata={}
        )

        command = tool_executor._build_command(tool, {})
        assert command == "mycontainer:latest"


# ============================================================================
# Testes de Execucao via MCP
# ============================================================================

class TestMCPExecution:
    """Testes de execucao via MCP Server."""

    @pytest.mark.asyncio
    async def test_execute_via_mcp_converts_response(
        self, tool_executor_with_mcp, mcp_tool, mock_mcp_client
    ):
        """Verifica conversao de MCPToolCallResponse para ExecutionResult."""
        response = MagicMock()
        response.isError = False
        response.content = [
            MagicMock(text="Result 1", data=None),
            MagicMock(text=None, data={"key": "value"}),
        ]
        response.structuredContent = {"extra": "data"}

        mock_mcp_client.call_tool = AsyncMock(return_value=response)
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        result = await tool_executor_with_mcp.execute_tool(
            tool=mcp_tool,
            execution_params={},
            context={}
        )

        assert result.success is True
        # Output concatena text e data
        assert "Result 1" in result.output
        assert "key" in result.output
        # Metadata inclui structured content
        assert result.metadata.get("structured_content") == {"extra": "data"}

    @pytest.mark.asyncio
    async def test_execute_via_mcp_handles_error(
        self, tool_executor_with_mcp, mcp_tool, mock_mcp_client
    ):
        """Verifica tratamento de erro MCP."""
        from src.clients.mcp_exceptions import MCPServerError

        mock_mcp_client.call_tool = AsyncMock(
            side_effect=MCPServerError("Tool execution failed", code=-32603)
        )
        tool_executor_with_mcp.mcp_clients = {"trivy-001": mock_mcp_client}

        # Adapter como fallback
        adapter_result = ExecutionResult(
            success=True,
            output="Fallback success",
            execution_time_ms=1000.0
        )

        with patch.object(
            tool_executor_with_mcp.container_adapter,
            "execute",
            return_value=adapter_result
        ):
            with patch.object(
                tool_executor_with_mcp.container_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                result = await tool_executor_with_mcp.execute_tool(
                    tool=mcp_tool,
                    execution_params={},
                    context={}
                )

                # Deve usar adapter como fallback
                assert result.success is True
                assert "Fallback success" in result.output
