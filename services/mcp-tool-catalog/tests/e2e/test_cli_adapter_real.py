import os
import subprocess
import tempfile

import pytest

from src.adapters.cli_adapter import CLIAdapter
from src.models.tool_descriptor import AuthenticationMethod, IntegrationType, ToolCategory, ToolDescriptor


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_trivy_scan_real():
    """Test Trivy CLI adapter with real scan."""
    adapter = CLIAdapter(timeout_seconds=60)

    subprocess.run(["docker", "pull", "nginx:alpine"], check=True)

    tool = ToolDescriptor(
        tool_id="trivy-001",
        tool_name="trivy",
        category=ToolCategory.ANALYSIS,
        version="0.48.0",
        capabilities=["vulnerability_scan"],
        reputation_score=0.92,
        cost_score=0.1,
        average_execution_time_ms=15000,
        output_format="json",
        integration_type=IntegrationType.CLI,
        authentication_method=AuthenticationMethod.NONE,
        metadata={"cli_command": "trivy image"},
    )

    result = await adapter.execute(
        tool_id=tool.tool_id,
        tool_name=tool.tool_name,
        command="trivy image",
        parameters={"severity": "HIGH,CRITICAL", "format": "json", "_target": "nginx:alpine"},
        context={"working_dir": "/tmp"},
    )

    assert result.success is True
    assert result.exit_code == 0
    assert "nginx:alpine" in result.output
    assert result.execution_time_ms > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pytest_execution_real():
    """Test Pytest CLI adapter with real test execution."""
    adapter = CLIAdapter(timeout_seconds=30)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_sample.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("def test_pass():\n    assert True\n")

        result = await adapter.execute(
            tool_id="pytest-001",
            tool_name="pytest",
            command="pytest",
            parameters={"verbose": True, "_target": test_file},
            context={"working_dir": tmpdir},
        )

        assert result.success is True
        assert "1 passed" in result.output


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_black_formatter_real():
    """Test Black CLI adapter with real formatting."""
    adapter = CLIAdapter(timeout_seconds=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        py_file = os.path.join(tmpdir, "sample.py")
        with open(py_file, "w", encoding="utf-8") as f:
            f.write("def foo( x,y ):\n  return x+y\n")

        result = await adapter.execute(
            tool_id="black-001",
            tool_name="black",
            command="black",
            parameters={"check": True, "_target": py_file},
            context={"working_dir": tmpdir},
        )

        assert result.exit_code in [0, 1]
        assert result.execution_time_ms > 0
