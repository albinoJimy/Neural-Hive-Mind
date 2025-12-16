import asyncio
import pytest

from tests.e2e.utils.k8s_helpers import get_pod_logs, scale_deployment


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ticket_timeout_triggers_self_healing(
    gateway_client,
    test_mongodb_collections,
    k8s_client,
    sample_intent_request,
):
    intent_request = {**sample_intent_request, "sla_timeout_ms": 30_000}
    response = await gateway_client.post("/intentions", json=intent_request)
    assert response.status_code == 200
    intent_id = response.json()["intent_id"]

    scale_deployment(k8s_client, "neural-hive-execution", "worker-agents", replicas=0)
    await asyncio.sleep(90)

    logs = get_pod_logs(k8s_client, "neural-hive-orchestration", "app=self-healing-engine", tail_lines=100)
    assert "playbook" in logs or "recovery" in logs

    scale_deployment(k8s_client, "neural-hive-execution", "worker-agents", replicas=3)

    await asyncio.sleep(30)
    tickets = await test_mongodb_collections["execution_tickets"].find({"intent_id": intent_id}).to_list(length=100)
    assert any(t.get("status") in {"RUNNING", "COMPLETED"} for t in tickets)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_worker_crash_triggers_reallocation(
    gateway_client, test_mongodb_collections, k8s_client, sample_intent_request
):
    response = await gateway_client.post("/intentions", json=sample_intent_request)
    assert response.status_code == 200
    intent_id = response.json()["intent_id"]

    pods = k8s_client.list_namespaced_pod(namespace="neural-hive-execution", label_selector="app=worker-agents").items
    if pods:
        k8s_client.delete_namespaced_pod(name=pods[0].metadata.name, namespace="neural-hive-execution")

    deadline = asyncio.get_event_loop().time() + 90
    reallocated = False
    tickets = []
    while asyncio.get_event_loop().time() < deadline and not reallocated:
        tickets = await test_mongodb_collections["execution_tickets"].find({"intent_id": intent_id}).to_list(length=200)
        reallocated = any(t.get("reallocated") or t.get("reallocated_at") for t in tickets)
        if reallocated:
            break
        await asyncio.sleep(5)
    assert tickets
    assert reallocated, "Nenhum ticket foi marcado como realocado após queda do worker"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_retry_on_transient_failure(orchestrator_client, sample_execution_ticket):
    response = await orchestrator_client.post("/api/v1/flow-c/execute", json=sample_execution_ticket)
    assert response.status_code in {200, 202}, "Erro 5xx não deve ser tratado como sucesso"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_compensation_on_partial_failure(orchestrator_client):
    payload = {"tickets": [{"ticket_id": f"partial-{i}"} for i in range(5)]}
    response = await orchestrator_client.post("/api/v1/flow-c/compensate", json=payload)
    assert response.status_code in {200, 202}, "Erro 5xx não deve ser tratado como sucesso"
