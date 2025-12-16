import os
import tempfile

import pytest

from src.adapters.container_adapter import ContainerAdapter


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_trivy_container_scan_real():
    """Test Trivy container adapter with real Docker execution."""
    adapter = ContainerAdapter(timeout_seconds=120)

    result = await adapter.execute(
        tool_id="trivy-container",
        tool_name="trivy",
        command="aquasec/trivy:latest",
        parameters={"args": ["image", "--severity", "HIGH", "nginx:alpine"], "volumes": []},
        context={"tool_id": "trivy-container", "network": "bridge"},
    )

    assert result.success is True
    assert result.exit_code == 0
    assert "nginx:alpine" in result.output


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_hadolint_container_real():
    """Test Hadolint container adapter."""
    adapter = ContainerAdapter(timeout_seconds=30)

    with tempfile.TemporaryDirectory() as tmpdir:
        dockerfile = os.path.join(tmpdir, "Dockerfile")
        with open(dockerfile, "w", encoding="utf-8") as f:
            f.write("FROM ubuntu:latest\nRUN apt-get update\n")

        result = await adapter.execute(
            tool_id="hadolint-001",
            tool_name="hadolint",
            command="hadolint/hadolint:latest",
            parameters={"args": ["hadolint", "/Dockerfile"], "volumes": [f"{tmpdir}:/workspace"]},
            context={"tool_id": "hadolint-001", "network": "bridge"},
        )

        assert result.execution_time_ms > 0
