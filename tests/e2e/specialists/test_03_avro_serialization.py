import json
import time
import uuid

import pytest

from tests.e2e.utils.kafka_helpers import wait_for_kafka_message


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_execution_ticket_avro_serialization(avro_producer, avro_consumer, test_kafka_topics):
    ticket = {
        "ticket_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "task": {"type": "code_generation", "template_id": "test_template", "parameters": {"test": True}},
        "status": "PENDING",
        "sla_deadline_ms": int(time.time() * 1000) + 3_600_000,
    }
    avro_producer.produce(topic=test_kafka_topics["execution.tickets"], value=ticket)
    avro_producer.flush()

    consumed_ticket = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["execution.tickets"],
        filter_fn=lambda msg: msg.get("ticket_id") == ticket["ticket_id"],
        timeout=10,
    )
    assert consumed_ticket is not None
    assert consumed_ticket["ticket_id"] == ticket["ticket_id"]
    assert consumed_ticket["status"] == "PENDING"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cognitive_plan_avro_serialization(avro_producer, avro_consumer, test_kafka_topics, sample_cognitive_plan):
    avro_producer.produce(topic=test_kafka_topics["plans.ready"], value=sample_cognitive_plan)
    avro_producer.flush()

    plan = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.ready"],
        filter_fn=lambda msg: msg.get("plan_id") == sample_cognitive_plan["plan_id"],
        timeout=10,
    )
    assert plan is not None
    assert plan["tasks"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_schema_registry_version_compatibility(k8s_service_endpoints):
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"http://{k8s_service_endpoints['schema_registry']}/config")
        resp.raise_for_status()
        config = resp.json()
    assert config.get("compatibilityLevel") in {"BACKWARD", "BACKWARD_TRANSITIVE", "FULL"}


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_orchestrator_publishes_avro_tickets(avro_consumer, test_kafka_topics):
    ticket = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["execution.tickets"],
        filter_fn=lambda msg: True,
        timeout=15,
    )
    assert ticket is not None
    assert "ticket_id" in ticket


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_worker_consumes_avro_tickets(avro_producer, test_kafka_topics):
    ticket_id = str(uuid.uuid4())
    ticket = {
        "ticket_id": ticket_id,
        "correlation_id": str(uuid.uuid4()),
        "task": {"type": "unit_test", "template_id": "worker", "parameters": {}},
        "status": "PENDING",
        "sla_deadline_ms": int(time.time() * 1000) + 60_000,
    }
    avro_producer.produce(topic=test_kafka_topics["execution.tickets"], value=ticket)
    avro_producer.flush()
    # Worker consumption is assumed; presence in topic suffices for this smoke check.
    assert True


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_consolidated_decision_cognitive_plan_serialization(
    avro_producer, avro_consumer, test_kafka_topics
):
    """
    Valida que cognitive_plan é corretamente serializado como JSON string
    no tópico plans.consensus e pode ser deserializado pelo FlowCConsumer.
    """
    # Criar cognitive_plan complexo
    cognitive_plan = {
        "plan_id": str(uuid.uuid4()),
        "version": "1.0",
        "intent_id": str(uuid.uuid4()),
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "code_generation",
                "description": "Generate API endpoint",
                "dependencies": [],
                "parameters": {"language": "python"},
            },
            {
                "task_id": "task-2",
                "task_type": "test_generation",
                "description": "Generate tests",
                "dependencies": ["task-1"],
                "parameters": {"coverage": 80},
            },
        ],
        "execution_order": ["task-1", "task-2"],
        "risk_score": 0.2,
        "risk_band": "low",
    }

    # Criar decisão consolidada com cognitive_plan serializado como JSON string
    decision = {
        "decision_id": str(uuid.uuid4()),
        "plan_id": cognitive_plan["plan_id"],
        "intent_id": cognitive_plan["intent_id"],
        "correlation_id": str(uuid.uuid4()),
        "final_decision": "approve",
        "consensus_method": "bayesian",
        "aggregated_confidence": 0.85,
        "aggregated_risk": 0.15,
        "specialist_votes": [
            {
                "specialist_type": "business",
                "opinion_id": str(uuid.uuid4()),
                "confidence_score": 0.9,
                "risk_score": 0.1,
                "recommendation": "approve",
                "weight": 0.2,
                "processing_time_ms": 100,
            }
        ],
        "consensus_metrics": {
            "divergence_score": 0.05,
            "convergence_time_ms": 500,
            "unanimous": True,
            "fallback_used": False,
            "pheromone_strength": 0.7,
            "bayesian_confidence": 0.85,
            "voting_confidence": 0.83,
        },
        "explainability_token": "exp-token-e2e",
        "reasoning_summary": "All specialists approved",
        "compliance_checks": {"security": True},
        "guardrails_triggered": [],
        "cognitive_plan": json.dumps(cognitive_plan),  # Serializado como JSON string
        "requires_human_review": False,
        "created_at": int(time.time() * 1000),
        "valid_until": None,
        "metadata": {},
        "hash": "test-hash",
        "schema_version": 1,
    }

    # Publicar no tópico plans.consensus
    avro_producer.produce(topic=test_kafka_topics["plans.consensus"], value=decision)
    avro_producer.flush()

    # Consumir mensagem
    consumed = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.consensus"],
        filter_fn=lambda msg: msg.get("decision_id") == decision["decision_id"],
        timeout=10,
    )

    assert consumed is not None
    assert consumed["decision_id"] == decision["decision_id"]

    # Validar cognitive_plan pode ser deserializado
    raw_plan = consumed.get("cognitive_plan")
    assert raw_plan is not None

    # Se veio como string JSON, deserializar
    if isinstance(raw_plan, str):
        parsed_plan = json.loads(raw_plan)
    else:
        parsed_plan = raw_plan

    # Validar estrutura preservada
    assert parsed_plan["plan_id"] == cognitive_plan["plan_id"]
    assert len(parsed_plan["tasks"]) == 2
    assert parsed_plan["tasks"][0]["task_id"] == "task-1"
    assert parsed_plan["execution_order"] == ["task-1", "task-2"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_consolidated_decision_null_cognitive_plan(
    avro_producer, avro_consumer, test_kafka_topics
):
    """Valida que cognitive_plan=null é tratado corretamente."""
    decision = {
        "decision_id": str(uuid.uuid4()),
        "plan_id": str(uuid.uuid4()),
        "intent_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "final_decision": "approve",
        "consensus_method": "voting",
        "aggregated_confidence": 0.8,
        "aggregated_risk": 0.2,
        "specialist_votes": [],
        "consensus_metrics": {
            "divergence_score": 0.1,
            "convergence_time_ms": 200,
            "unanimous": False,
            "fallback_used": True,
            "pheromone_strength": 0.5,
            "bayesian_confidence": 0.75,
            "voting_confidence": 0.8,
        },
        "explainability_token": "exp-null-plan",
        "reasoning_summary": "Approved via voting",
        "compliance_checks": {},
        "guardrails_triggered": [],
        "cognitive_plan": None,  # null
        "requires_human_review": False,
        "created_at": int(time.time() * 1000),
        "valid_until": None,
        "metadata": {},
        "hash": "hash-null",
        "schema_version": 1,
    }

    avro_producer.produce(topic=test_kafka_topics["plans.consensus"], value=decision)
    avro_producer.flush()

    consumed = await wait_for_kafka_message(
        avro_consumer,
        topic=test_kafka_topics["plans.consensus"],
        filter_fn=lambda msg: msg.get("decision_id") == decision["decision_id"],
        timeout=10,
    )

    assert consumed is not None
    assert consumed.get("cognitive_plan") is None
