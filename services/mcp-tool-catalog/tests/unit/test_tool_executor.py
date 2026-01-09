"""
Testes unitarios para ToolExecutor.

Cobertura:
- Roteamento hibrido MCP/Adapter
- Graceful degradation MCP -> Adapter
- Execucao via adapters (CLI/REST/Container)
- Execucao via MCP Server
- Metricas e feedback loop
- Execucao em batch com controle de concorrencia
- Build command por integration_type
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestToolExecutorRouting:
    """Testes de roteamento hibrido MCP/Adapter."""

    @pytest.mark.asyncio
    async def test_routes_to_adapter_when_no_mcp_configured(
        self,
        cli_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve rotear para adapter quando MCP nao configurado."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_adapter_result = ExecutionResult(
            success=True,
            output='test output',
            execution_time_ms=100.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)

            # Mock adapter
            executor.cli_adapter.execute = AsyncMock(return_value=mock_adapter_result)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            result = await executor.execute_tool(
                tool=cli_tool,
                execution_params={'verbose': True},
                context={'working_dir': '/app'}
            )

            assert result.success is True
            assert result.output == 'test output'
            executor.cli_adapter.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_to_mcp_when_configured(
        self,
        cli_tool,
        mock_settings_with_mcp,
        mock_metrics
    ):
        """Deve rotear para MCP quando configurado."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult
        from src.models.mcp_messages import MCPToolCallResponse, MCPContent

        # Configurar tool_id no mcp_servers
        cli_tool.tool_id = 'trivy-001'

        mock_mcp_response = MCPToolCallResponse(
            content=[MCPContent(type='text', text='MCP result')],
            isError=False
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings_with_mcp):
            executor = ToolExecutor(metrics=mock_metrics)

            # Simular cliente MCP conectado
            mock_mcp_client = AsyncMock()
            mock_mcp_client.server_url = 'http://trivy-mcp:3000'
            mock_mcp_client.call_tool = AsyncMock(return_value=mock_mcp_response)
            executor.mcp_clients['trivy-001'] = mock_mcp_client

            result = await executor.execute_tool(
                tool=cli_tool,
                execution_params={'target': 'nginx:latest'},
                context={}
            )

            assert result.success is True
            assert 'MCP result' in result.output
            mock_mcp_client.call_tool.assert_called_once()


class TestToolExecutorGracefulDegradation:
    """Testes de graceful degradation MCP -> Adapter."""

    @pytest.mark.asyncio
    async def test_fallback_to_adapter_on_mcp_failure(
        self,
        cli_tool,
        mock_settings_with_mcp,
        mock_metrics
    ):
        """Deve fazer fallback para adapter quando MCP falha."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult
        from src.clients.mcp_exceptions import MCPError

        cli_tool.tool_id = 'trivy-001'

        mock_adapter_result = ExecutionResult(
            success=True,
            output='adapter fallback output',
            execution_time_ms=150.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings_with_mcp):
            executor = ToolExecutor(metrics=mock_metrics)

            # Simular cliente MCP que falha
            mock_mcp_client = AsyncMock()
            mock_mcp_client.server_url = 'http://trivy-mcp:3000'
            mock_mcp_client.call_tool = AsyncMock(side_effect=MCPError('Connection failed', code=-1))
            executor.mcp_clients['trivy-001'] = mock_mcp_client

            # Mock adapter
            executor.cli_adapter.execute = AsyncMock(return_value=mock_adapter_result)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            result = await executor.execute_tool(
                tool=cli_tool,
                execution_params={},
                context={}
            )

            # Deve usar resultado do adapter
            assert result.success is True
            assert 'adapter fallback output' in result.output

            # MCP foi tentado primeiro
            mock_mcp_client.call_tool.assert_called_once()
            # Fallback para adapter
            executor.cli_adapter.execute.assert_called_once()

            # Metrica de fallback deve ser registrada
            mock_metrics.record_mcp_fallback.assert_called_once()


class TestToolExecutorAdapterExecution:
    """Testes de execucao via adapters."""

    @pytest.mark.asyncio
    async def test_execute_via_cli_adapter(
        self,
        cli_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve executar ferramenta CLI via CLIAdapter."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_result = ExecutionResult(
            success=True,
            output='pytest results',
            execution_time_ms=5000.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.cli_adapter.execute = AsyncMock(return_value=mock_result)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            result = await executor.execute_tool(
                tool=cli_tool,
                execution_params={'verbose': True},
                context={'working_dir': '/project'}
            )

            assert result.success is True
            assert result.metadata.get('execution_route') == 'adapter'
            assert result.metadata.get('adapter_type') == 'CLI'

    @pytest.mark.asyncio
    async def test_execute_via_rest_adapter(
        self,
        rest_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve executar ferramenta REST via RESTAdapter."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_result = ExecutionResult(
            success=True,
            output='{"analysis": "complete"}',
            execution_time_ms=3000.0,
            exit_code=200
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.rest_adapter.execute = AsyncMock(return_value=mock_result)
            executor.rest_adapter.validate_tool_availability = AsyncMock(return_value=True)

            result = await executor.execute_tool(
                tool=rest_tool,
                execution_params={'body': {'project': 'myapp'}},
                context={'auth_token': 'secret'}
            )

            assert result.success is True
            assert result.metadata.get('adapter_type') == 'REST_API'

    @pytest.mark.asyncio
    async def test_execute_via_container_adapter(
        self,
        container_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve executar ferramenta Container via ContainerAdapter."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_result = ExecutionResult(
            success=True,
            output='{"vulnerabilities": []}',
            execution_time_ms=60000.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.container_adapter.execute = AsyncMock(return_value=mock_result)
            executor.container_adapter.validate_tool_availability = AsyncMock(return_value=True)

            result = await executor.execute_tool(
                tool=container_tool,
                execution_params={'args': ['image', 'nginx:latest']},
                context={}
            )

            assert result.success is True
            assert result.metadata.get('adapter_type') == 'CONTAINER'


class TestToolExecutorBuildCommand:
    """Testes de construcao de comando por integration_type."""

    @pytest.mark.asyncio
    async def test_build_command_for_cli(self, cli_tool, mock_settings):
        """Deve construir comando CLI corretamente."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor()

            # CLI usa tool_name ou cli_command do metadata
            cmd = executor._build_command(cli_tool, {})

            assert cmd == 'pytest'

    @pytest.mark.asyncio
    async def test_build_command_for_rest(self, rest_tool, mock_settings):
        """Deve construir URL REST corretamente."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor()

            # REST usa endpoint_url
            cmd = executor._build_command(rest_tool, {})

            assert cmd == 'http://sonarqube:9000/api/analyze'

    @pytest.mark.asyncio
    async def test_build_command_for_container(self, container_tool, mock_settings):
        """Deve construir imagem Docker corretamente."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor()

            # Container usa docker_image do metadata
            cmd = executor._build_command(container_tool, {})

            assert cmd == 'aquasec/trivy:0.45.0'


class TestToolExecutorMetrics:
    """Testes de metricas e feedback loop."""

    @pytest.mark.asyncio
    async def test_records_execution_metrics(
        self,
        cli_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve registrar metricas de execucao."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_result = ExecutionResult(
            success=True,
            output='output',
            execution_time_ms=1000.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.cli_adapter.execute = AsyncMock(return_value=mock_result)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            await executor.execute_tool(cli_tool, {}, {})

            mock_metrics.record_tool_execution.assert_called_once()
            call_kwargs = mock_metrics.record_tool_execution.call_args.kwargs
            assert call_kwargs['tool_id'] == cli_tool.tool_id
            assert call_kwargs['status'] == 'success'
            assert call_kwargs['execution_route'] == 'adapter'

    @pytest.mark.asyncio
    async def test_updates_tool_registry_feedback(
        self,
        cli_tool,
        mock_settings,
        mock_metrics,
        mock_tool_registry
    ):
        """Deve atualizar reputacao no tool registry."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_result = ExecutionResult(
            success=True,
            output='output',
            execution_time_ms=1000.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(
                tool_registry=mock_tool_registry,
                metrics=mock_metrics
            )
            executor.cli_adapter.execute = AsyncMock(return_value=mock_result)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            # Simular update_tool_metrics no registry
            mock_tool_registry.update_tool_metrics = AsyncMock()

            await executor.execute_tool(cli_tool, {}, {})

            mock_tool_registry.update_tool_metrics.assert_called_once()


class TestToolExecutorBatchExecution:
    """Testes de execucao em batch."""

    @pytest.mark.asyncio
    async def test_execute_tools_batch(
        self,
        benchmark_tools,
        mock_settings,
        mock_metrics
    ):
        """Deve executar multiplas ferramentas em paralelo."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        mock_result = ExecutionResult(
            success=True,
            output='batch output',
            execution_time_ms=100.0,
            exit_code=0
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.cli_adapter.execute = AsyncMock(return_value=mock_result)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            results = await executor.execute_tools_batch(
                tools=benchmark_tools[:3],  # Usar 3 ferramentas
                execution_params={},
                context={}
            )

            assert len(results) == 3
            for tool_id, result in results.items():
                assert result.success is True

    @pytest.mark.asyncio
    async def test_batch_handles_individual_failures(
        self,
        benchmark_tools,
        mock_settings,
        mock_metrics
    ):
        """Deve tratar falhas individuais no batch."""
        from src.services.tool_executor import ToolExecutor
        from src.adapters.base_adapter import ExecutionResult

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception('Tool 2 failed')
            return ExecutionResult(
                success=True,
                output='success',
                execution_time_ms=100.0,
                exit_code=0
            )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.cli_adapter.execute = mock_execute
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)

            results = await executor.execute_tools_batch(
                tools=benchmark_tools[:3],
                execution_params={},
                context={}
            )

            # 2 sucesso, 1 falha
            successes = sum(1 for r in results.values() if r.success)
            failures = sum(1 for r in results.values() if not r.success)

            assert successes == 2
            assert failures == 1


class TestToolExecutorLifecycle:
    """Testes de lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_initializes_mcp_clients(self, mock_settings_with_mcp):
        """Deve inicializar clientes MCP no start."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings_with_mcp):
            with patch('src.services.tool_executor.MCPServerClient') as MockMCPClient:
                mock_client = AsyncMock()
                mock_client.start = AsyncMock()
                mock_client.list_tools = AsyncMock(return_value=[])
                MockMCPClient.return_value = mock_client

                executor = ToolExecutor()
                await executor.start()

                # Deve ter tentado criar clientes para MCP_SERVERS configurados
                assert MockMCPClient.call_count > 0

    @pytest.mark.asyncio
    async def test_stop_closes_mcp_clients(self, mock_settings_with_mcp):
        """Deve fechar clientes MCP no stop."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings_with_mcp):
            executor = ToolExecutor()

            # Adicionar cliente mock
            mock_client = AsyncMock()
            mock_client.stop = AsyncMock()
            executor.mcp_clients['test-tool'] = mock_client

            await executor.stop()

            mock_client.stop.assert_called_once()
            assert len(executor.mcp_clients) == 0


class TestToolExecutorErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_returns_error_when_no_adapter_available(
        self,
        mock_settings
    ):
        """Deve retornar erro quando nenhum adapter disponivel."""
        from src.services.tool_executor import ToolExecutor
        from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType

        # Criar tool com integration_type desconhecido
        unknown_tool = ToolDescriptor(
            tool_id='unknown-001',
            tool_name='unknown',
            category=ToolCategory.ANALYSIS,
            version='1.0.0',
            capabilities=['test'],
            reputation_score=0.5,
            cost_score=0.1,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.MCP,  # Sem adapter direto
            authentication_method='NONE',
            output_format='json'
        )

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor()

            result = await executor.execute_tool(unknown_tool, {}, {})

            assert result.success is False
            assert 'No executor available' in result.error

    @pytest.mark.asyncio
    async def test_handles_tool_not_available(
        self,
        cli_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve tratar ferramenta nao disponivel."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=False)

            result = await executor.execute_tool(cli_tool, {}, {})

            assert result.success is False
            assert 'not available' in result.error

    @pytest.mark.asyncio
    async def test_handles_adapter_exception(
        self,
        cli_tool,
        mock_settings,
        mock_metrics
    ):
        """Deve tratar excecao do adapter graciosamente."""
        from src.services.tool_executor import ToolExecutor

        with patch('src.services.tool_executor.get_settings', return_value=mock_settings):
            executor = ToolExecutor(metrics=mock_metrics)
            executor.cli_adapter.validate_tool_availability = AsyncMock(return_value=True)
            executor.cli_adapter.execute = AsyncMock(side_effect=Exception('Adapter crashed'))

            result = await executor.execute_tool(cli_tool, {}, {})

            assert result.success is False
            assert 'Adapter crashed' in result.error
            assert result.metadata.get('exception') == 'Exception'
