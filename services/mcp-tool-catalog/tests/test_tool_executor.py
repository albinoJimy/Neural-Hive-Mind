"""
Testes unitários para ToolExecutor.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.tool_executor import ToolExecutor
from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType
from src.adapters.base_adapter import ExecutionResult


@pytest.fixture
def tool_executor():
    """Fixture do executor."""
    return ToolExecutor()


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


@pytest.mark.asyncio
async def test_execute_tool_cli_success(tool_executor, cli_tool):
    """Testa execução de ferramenta CLI."""
    # Mock do adapter
    mock_result = ExecutionResult(
        success=True,
        output="All tests passed",
        execution_time_ms=1234.56,
        exit_code=0
    )

    with patch.object(
        tool_executor.adapters[IntegrationType.CLI],
        'execute',
        return_value=mock_result
    ):
        with patch.object(
            tool_executor.adapters[IntegrationType.CLI],
            'validate_tool_availability',
            return_value=True
        ):
            result = await tool_executor.execute_tool(
                tool=cli_tool,
                execution_params={"verbose": True},
                context={"working_dir": "/app"}
            )

            assert result.success is True
            assert result.output == "All tests passed"
            assert result.execution_time_ms == 1234.56


@pytest.mark.asyncio
async def test_execute_tool_adapter_not_found(tool_executor):
    """Testa erro quando adapter não disponível."""
    # Ferramenta com tipo não implementado
    invalid_tool = ToolDescriptor(
        tool_id="grpc-001",
        tool_name="grpc-tool",
        category=ToolCategory.INTEGRATION,
        version="1.0.0",
        capabilities=["rpc"],
        reputation_score=0.8,
        cost_score=0.3,
        average_execution_time_ms=1000,
        integration_type=IntegrationType.GRPC,  # Não implementado ainda
        authentication_method="NONE",
        is_healthy=True
    )

    from src.adapters.base_adapter import AdapterError

    with pytest.raises(AdapterError, match="No adapter available"):
        await tool_executor.execute_tool(
            tool=invalid_tool,
            execution_params={},
            context={}
        )


@pytest.mark.asyncio
async def test_execute_tool_batch(tool_executor, cli_tool):
    """Testa execução em batch."""
    # Criar múltiplas ferramentas
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

    # Mock adapter
    mock_result = ExecutionResult(
        success=True,
        output="Success",
        execution_time_ms=500.0,
        exit_code=0
    )

    with patch.object(
        tool_executor.adapters[IntegrationType.CLI],
        'execute',
        return_value=mock_result
    ):
        with patch.object(
            tool_executor.adapters[IntegrationType.CLI],
            'validate_tool_availability',
            return_value=True
        ):
            results = await tool_executor.execute_tool_batch(
                tools=tools,
                execution_params={},
                context={}
            )

            assert len(results) == 3
            assert all(r.success for r in results.values())


@pytest.mark.asyncio
async def test_get_execution_command(tool_executor, cli_tool):
    """Testa extração de comando de execução."""
    command = tool_executor._get_execution_command(cli_tool)
    assert command == "pytest"

    # Tool com metadata de comando customizado
    custom_tool = ToolDescriptor(
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

    command = tool_executor._get_execution_command(custom_tool)
    assert command == "custom-cmd --flag"
