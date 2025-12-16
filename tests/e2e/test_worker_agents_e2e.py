import asyncio

import pytest


@pytest.fixture
async def worker_client():
    pytest.skip("worker_client fixture not configured in this environment")


@pytest.fixture
async def code_forge_client():
    pytest.skip("code_forge_client fixture not configured in this environment")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_worker_agent_build_executor_code_forge(worker_client, code_forge_client):
    """Test BUILD executor integrates with Code Forge."""
    ticket = {
        "ticket_id": "build-001",
        "task_type": "BUILD",
        "artifact_type": "CODE",
        "language": "python",
        "context": {"framework": "fastapi"},
    }

    response = await worker_client.post("/api/v1/execute", json=ticket)
    assert response.status_code == 202

    await asyncio.sleep(10)

    artifact_response = await code_forge_client.get("/api/v1/artifacts?ticket_id=build-001")
    assert artifact_response.status_code == 200
    artifacts = artifact_response.json()
    assert len(artifacts) > 0
    assert artifacts[0]["artifact_type"] == "CODE"
