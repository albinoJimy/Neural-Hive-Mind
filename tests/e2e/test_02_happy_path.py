import asyncio
import time

import pytest

from tests.e2e.utils.kafka_helpers import collect_kafka_messages, wait_for_kafka_message
from tests.e2e.utils.metrics import query_prometheus
from tests.e2e.utils.assertions import assert_ticket_valid, assert_workflow_completed


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_flow_c_happy_path(
    gateway_client,
    avro_consumer,
    test_mongodb_collections,
    sample_intent_request,
    test_kafka_topics,
    port_forward_manager,
):
    response = await gateway_client.post("/intentions", json=sample_intent_request)
    assert response.status_code == 200
    intent_data = response.json()
    intent_id = intent_data["intent_id"]
    correlation_id = intent_data["correlation_id"]

    plan = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.ready"],
        filter_fn=lambda msg: msg.get("intent_id") == intent_id,
        timeout=60,
    )
    assert plan is not None
    assert "tasks" in plan and plan["tasks"]

    decision = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.consensus"],
        filter_fn=lambda msg: msg.get("plan_id") == plan.get("plan_id"),
        timeout=90,
    )
    assert decision is not None
    assert decision.get("status") in {"approved", "APPROVED"}

    tickets = await collect_kafka_messages(
        avro_consumer,
        topic=test_kafka_topics["execution.tickets"],
        filter_fn=lambda msg: msg.get("correlation_id") == correlation_id,
        timeout=120,
        expected_count=len(plan["tasks"]),
    )
    assert len(tickets) == len(plan["tasks"])
    for ticket in tickets:
        assert_ticket_valid(ticket)
        assert ticket["status"] == "PENDING"

    tickets_in_db = await test_mongodb_collections["execution_tickets"].find(
        {"correlation_id": correlation_id}
    ).to_list(length=100)
    assert len(tickets_in_db) == len(tickets)

    for ticket in tickets:
        deadline = time.time() + 300
        while time.time() < deadline:
            stored = await test_mongodb_collections["execution_tickets"].find_one({"ticket_id": ticket["ticket_id"]})
            if stored and stored.get("status") == "COMPLETED":
                assert "result" in stored
                break
            await asyncio.sleep(5)
        else:
            pytest.fail(f"Ticket {ticket['ticket_id']} não completou no tempo esperado")

    workflow_result = await test_mongodb_collections["workflows"].find_one({"correlation_id": correlation_id})
    assert_workflow_completed(workflow_result)

    telemetry = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics.get("telemetry.orchestration", "telemetry.orchestration"),
        filter_fn=lambda msg: msg.get("correlation_id") == correlation_id,
        timeout=60,
    )
    assert telemetry is not None
    assert telemetry.get("duration_ms") is not None

    metrics = await query_prometheus(
        port_forward_manager["prometheus"],
        query=f'neural_hive_flow_c_success_total{{correlation_id="{correlation_id}"}}',
    )
    results = metrics.get("data", {}).get("result", [])
    if results:
        assert results[0]["value"][1] == "1"
