import asyncio
import uuid

import pytest

from tests.e2e.utils.kafka_helpers import collect_kafka_messages, wait_for_kafka_message
from tests.e2e.utils.assertions import assert_workflow_completed

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.skip(reason="Requires full platform environment")]


@pytest.mark.asyncio
async def test_complete_flow_intent_to_artifact_with_real_tools(
    gateway_client,
    avro_consumer,
    test_mongodb_collections,
    test_kafka_topics,
    mcp_client,
    code_forge_client,
    worker_client,
    port_forward_manager,
):
    """
    Test complete flow: Intent → Semantic Translation → Consensus →
    Orchestrator → MCP Selection → Code Forge → Worker Execution → Artifact.

    Uses REAL tools: Trivy (security scan), Pytest (validation), Black (formatting).
    """

    intent_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    intent_request = {
        "text": "Criar microserviço Python FastAPI com endpoint /health e testes automatizados",
        "language": "pt-BR",
        "domain": "TECHNICAL",
        "priority": "HIGH",
        "metadata": {"framework": "fastapi", "test_framework": "pytest", "security_scan": True},
    }

    response = await gateway_client.post("/intentions", json=intent_request)
    assert response.status_code == 200
    intent_data = response.json()
    intent_id = intent_data["intent_id"]
    correlation_id = intent_data["correlation_id"]

    plan = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.ready"],
        filter_fn=lambda msg: msg.get("intent_id") == intent_id,
        timeout=90,
    )
    assert plan is not None
    assert "tasks" in plan
    assert len(plan["tasks"]) > 0

    plan_id = plan["plan_id"]

    decision = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.consensus"],
        filter_fn=lambda msg: msg.get("plan_id") == plan_id,
        timeout=120,
    )
    assert decision is not None
    assert decision.get("status") in {"approved", "APPROVED"}

    decision_id = decision["decision_id"]

    tickets = await collect_kafka_messages(
        avro_consumer,
        topic=test_kafka_topics["execution.tickets"],
        filter_fn=lambda msg: msg.get("correlation_id") == correlation_id,
        timeout=180,
        expected_count=len(plan["tasks"]),
    )
    assert len(tickets) == len(plan["tasks"])

    build_ticket = next((t for t in tickets if t["task_type"] == "BUILD"), None)
    assert build_ticket is not None

    ticket_id = build_ticket["ticket_id"]

    await asyncio.sleep(5)

    mcp_selections_response = await mcp_client.get(f"/api/v1/selections?ticket_id={ticket_id}")
    assert mcp_selections_response.status_code == 200
    mcp_selections = mcp_selections_response.json()

    if len(mcp_selections) > 0:
        mcp_selection = mcp_selections[0]
        assert mcp_selection["selection_method"] in ["GENETIC_ALGORITHM", "HEURISTIC"]
        assert len(mcp_selection["selected_tools"]) >= 2

    await asyncio.sleep(20)

    artifact_response = await code_forge_client.get(f"/api/v1/artifacts?ticket_id={ticket_id}")
    assert artifact_response.status_code == 200
    artifacts = artifact_response.json()
    assert len(artifacts) > 0

    artifact = artifacts[0]
    assert artifact["artifact_type"] == "CODE"
    assert artifact["language"] == "python"
    assert artifact["confidence_score"] > 0.5

    artifact_id = artifact["artifact_id"]

    validate_ticket = next((t for t in tickets if t["task_type"] == "VALIDATE"), None)
    if validate_ticket:
        validate_ticket_id = validate_ticket["ticket_id"]

        stored_ticket = await test_mongodb_collections["execution_tickets"].find_one({"ticket_id": validate_ticket_id})

        if stored_ticket:
            assert stored_ticket["status"] in ["COMPLETED", "RUNNING"]

            if stored_ticket["status"] == "COMPLETED":
                result = stored_ticket.get("result", {})
                if "validation_results" in result:
                    for tool_result in result["validation_results"]:
                        assert tool_result["status"] in ["PASSED", "FAILED"]

    await asyncio.sleep(10)

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

    from tests.e2e.utils.metrics import query_prometheus

    metrics = await query_prometheus(
        port_forward_manager["prometheus"],
        query=f'neural_hive_flow_c_success_total{{correlation_id="{correlation_id}"}}',
    )

    results = metrics.get("data", {}).get("result", [])
    if results:
        assert results[0]["value"][1] == "1"

    assert intent_id is not None
    assert plan_id is not None
    assert decision_id is not None
    assert len(tickets) > 0
    assert artifact_id is not None
    assert workflow_result["status"] == "COMPLETED"
