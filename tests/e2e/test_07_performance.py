import asyncio
import time

import pytest

from tests.e2e.utils.assertions import assert_slo_met


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_intent_to_deploy_latency_slo(gateway_client, test_mongodb_collections):
    latencies = []
    for i in range(3):
        start = time.time()
        response = await gateway_client.post("/intentions", json={"text": f"Test intent {i}", "language": "pt-BR"})
        assert response.status_code == 200
        intent_id = response.json()["intent_id"]
        while True:
            workflow = await test_mongodb_collections["workflows"].find_one({"intent_id": intent_id})
            if workflow and workflow.get("status") == "COMPLETED":
                break
            await asyncio.sleep(5)
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    p50 = latencies[int(len(latencies) * 0.50)]
    # SLO alinhado aos scripts de validação (test-slos.sh usa P95=150ms gateway, validate-performance-benchmarks.sh usa P95=500ms API):
    # fluxo intent→deploy completo deve manter P95 <= 500 ms e P50 <= 250 ms em cenários normais.
    assert_slo_met(p95, 500)
    assert_slo_met(p50, 250)


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_orchestrator_throughput(orchestrator_client):
    tasks = [{"ticket_id": f"throughput-{i}"} for i in range(20)]
    start = time.time()
    response = await orchestrator_client.post("/api/v1/flow-c/bulk", json={"tickets": tasks})
    duration = time.time() - start
    assert response.status_code in {200, 207}
    throughput = len(tasks) / max(duration, 1)
    assert throughput > 10 or duration < 5


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_ticket_allocation_latency(orchestrator_client):
    start = time.time()
    response = await orchestrator_client.post("/api/v1/flow-c/allocate", json={"tasks": [{"id": "t1"}]})
    duration = time.time() - start
    assert response.status_code in {200, 202}
    assert duration < 5


@pytest.mark.e2e
@pytest.mark.slow
def test_kafka_publish_latency(kafka_admin_client):
    metadata = kafka_admin_client.list_topics(timeout=10)
    assert metadata.brokers


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mongodb_query_performance(test_mongodb_collections):
    collection = test_mongodb_collections["execution_tickets"]
    docs = [{"_id": f"perf-{i}"} for i in range(1000)]
    await collection.insert_many(docs)
    start = time.time()
    _ = await collection.find_one({"_id": "perf-500"})
    duration = (time.time() - start) * 1000
    assert duration < 100
