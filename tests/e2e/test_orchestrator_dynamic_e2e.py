import pytest

from tests.e2e.utils.k8s_helpers import get_pod_logs, scale_deployment


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_orchestrator_workflow_c3_allocation_failure(orchestrator_client, k8s_client):
    """Test C3 allocation failure triggers compensation."""
    scale_deployment(k8s_client, "neural-hive-orchestration", "service-registry", replicas=0)

    ticket = {"ticket_id": "alloc-fail-001", "task_type": "BUILD"}
    response = await orchestrator_client.post("/api/v1/flow-c/allocate", json=ticket)

    assert response.status_code in [500, 503]

    logs = get_pod_logs(k8s_client, "neural-hive-orchestration", "app=orchestrator-dynamic", tail_lines=50)
    assert "compensation_triggered" in logs or "allocation_failed" in logs

    scale_deployment(k8s_client, "neural-hive-orchestration", "service-registry", replicas=2)
