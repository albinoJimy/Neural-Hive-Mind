import pytest

from src.models.tool_selection import ToolSelectionRequest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_genetic_selection_with_real_execution(genetic_selector, tool_executor):
    """Test full flow: genetic selection + real tool execution."""

    request = ToolSelectionRequest(
        request_id="e2e-test-001",
        correlation_id="corr-001",
        artifact_type="CODE",
        language="python",
        complexity_score=0.5,
        required_categories=["ANALYSIS", "VALIDATION"],
        constraints={"max_execution_time_ms": 60000, "max_cost_score": 0.5, "min_reputation_score": 0.7},
        context={"framework": "fastapi"},
    )

    response = await genetic_selector.select_tools(request)

    assert response.selection_method in ["GENETIC_ALGORITHM", "HEURISTIC"]
    assert len(response.selected_tools) >= 2
    assert response.total_fitness_score > 0.5

    for selected_tool in response.selected_tools:
        tool_descriptor = await genetic_selector.tool_registry.get_tool(selected_tool.tool_id)

        if tool_descriptor.integration_type in ["CLI", "CONTAINER"]:
            result = await tool_executor.execute_tool(
                tool=tool_descriptor, execution_params={"verbose": True}, context={"working_dir": "/tmp"}
            )

            assert result is not None
            assert result.execution_time_ms > 0

            await genetic_selector.tool_registry.update_reputation(
                tool_id=selected_tool.tool_id, success=result.success, execution_time_ms=result.execution_time_ms
            )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cache_hit_after_selection(genetic_selector):
    """Test cache hit on repeated selection."""
    request = ToolSelectionRequest(
        request_id="cache-test-001",
        correlation_id="corr-002",
        artifact_type="CODE",
        language="python",
        complexity_score=0.6,
        required_categories=["GENERATION"],
        constraints={},
    )

    response1 = await genetic_selector.select_tools(request)
    assert response1.cached is False

    response2 = await genetic_selector.select_tools(request)
    assert response2.cached is True
    assert response2.selected_tools == response1.selected_tools
