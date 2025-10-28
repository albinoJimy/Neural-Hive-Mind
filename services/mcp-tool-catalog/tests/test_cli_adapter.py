"""
Testes unitários para CLIAdapter.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.adapters.cli_adapter import CLIAdapter
from src.adapters.base_adapter import ExecutionResult


@pytest.fixture
def cli_adapter():
    """Fixture do adapter."""
    return CLIAdapter(timeout_seconds=10)


@pytest.mark.asyncio
async def test_execute_success(cli_adapter):
    """Testa execução CLI bem-sucedida."""
    # Mock subprocess
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(
        return_value=(b"Success output", b"")
    )

    with patch('asyncio.create_subprocess_shell', return_value=mock_process):
        result = await cli_adapter.execute(
            tool_id="test-001",
            tool_name="echo",
            command="echo hello",
            parameters={},
            context={}
        )

        assert result.success is True
        assert "Success output" in result.output
        assert result.exit_code == 0
        assert result.execution_time_ms > 0


@pytest.mark.asyncio
async def test_execute_failure(cli_adapter):
    """Testa execução CLI com falha."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(
        return_value=(b"", b"Error message")
    )

    with patch('asyncio.create_subprocess_shell', return_value=mock_process):
        result = await cli_adapter.execute(
            tool_id="test-002",
            tool_name="false",
            command="false",
            parameters={},
            context={}
        )

        assert result.success is False
        assert result.exit_code == 1
        assert "Error message" in result.error


@pytest.mark.asyncio
async def test_execute_timeout(cli_adapter):
    """Testa timeout de execução."""
    import asyncio

    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(
        side_effect=asyncio.TimeoutError()
    )
    mock_process.kill = MagicMock()

    with patch('asyncio.create_subprocess_shell', return_value=mock_process):
        result = await cli_adapter.execute(
            tool_id="test-003",
            tool_name="sleep",
            command="sleep 100",
            parameters={},
            context={}
        )

        assert result.success is False
        assert "timed out" in result.error
        mock_process.kill.assert_called_once()


@pytest.mark.asyncio
async def test_build_command(cli_adapter):
    """Testa construção de comando CLI."""
    command = cli_adapter._build_command(
        base_command="trivy image",
        parameters={
            "severity": "HIGH",
            "format": "json",
            "_target": "nginx:latest"
        }
    )

    assert "trivy image" in command
    assert "--severity HIGH" in command or "--severity 'HIGH'" in command
    assert "--format json" in command or "--format 'json'" in command


@pytest.mark.asyncio
async def test_validate_tool_availability_success(cli_adapter):
    """Testa validação de ferramenta disponível."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"/usr/bin/echo", b""))

    with patch('asyncio.create_subprocess_shell', return_value=mock_process):
        is_available = await cli_adapter.validate_tool_availability("echo")
        assert is_available is True


@pytest.mark.asyncio
async def test_validate_tool_availability_failure(cli_adapter):
    """Testa validação de ferramenta não disponível."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"not found"))

    with patch('asyncio.create_subprocess_shell', return_value=mock_process):
        is_available = await cli_adapter.validate_tool_availability("nonexistent")
        assert is_available is False
