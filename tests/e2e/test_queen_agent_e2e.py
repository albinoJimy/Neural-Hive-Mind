import pytest


@pytest.fixture
async def queen_client():
    pytest.skip("queen_client fixture not configured in this environment")


@pytest.fixture
async def test_mongodb_collections():
    pytest.skip("test_mongodb_collections fixture not configured in this environment")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_queen_agent_replanning_trigger(queen_client, test_mongodb_collections):
    """Test replanning triggered after multiple ticket failures."""
    for i in range(3):
        await test_mongodb_collections["execution_tickets"].insert_one(
            {"ticket_id": f"fail-{i}", "status": "FAILED", "plan_id": "plan-001"}
        )

    response = await queen_client.post("/api/v1/replanning/check", json={"plan_id": "plan-001"})

    assert response.status_code == 200
    data = response.json()
    assert data["replanning_needed"] is True
    assert data["reason"] == "multiple_ticket_failures"
