import asyncio

import pytest


@pytest.fixture
async def code_forge_client():
    pytest.skip("code_forge_client fixture not configured in this environment")


@pytest.fixture
async def mcp_client():
    pytest.skip("mcp_client fixture not configured in this environment")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_code_forge_pipeline_with_mcp_selection(code_forge_client, mcp_client):
    """Test full Code Forge pipeline with MCP tool selection."""
    request = {
        "ticket_id": "cf-001",
        "artifact_type": "CODE",
        "language": "python",
        "complexity_score": 0.6,
        "context": {"framework": "fastapi", "test_framework": "pytest"},
    }

    response = await code_forge_client.post("/api/v1/artifacts/generate", json=request)
    assert response.status_code == 202

    await asyncio.sleep(5)

    mcp_selections = await mcp_client.get("/api/v1/selections?ticket_id=cf-001")
    assert mcp_selections.status_code == 200
    selections = mcp_selections.json()
    assert len(selections) > 0
    assert selections[0]["selection_method"] in ["GENETIC_ALGORITHM", "HEURISTIC"]

    await asyncio.sleep(15)

    artifact_response = await code_forge_client.get("/api/v1/artifacts/cf-001")
    assert artifact_response.status_code == 200
    artifact = artifact_response.json()
    assert artifact["metadata"]["mcp_selection_id"] is not None
    assert len(artifact["metadata"]["mcp_tools_used"]) > 0
    assert artifact["confidence_score"] > 0.5
