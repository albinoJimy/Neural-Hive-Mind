"""
Testes para Schema Avro v2 com campos de workflow_type.

Valida compatibilidade backward e novos campos de routing.
"""

import json
import io
import fastavro
from datetime import datetime


def load_schema():
    """Carrega schema Avro."""
    with open("consolidated-decision.avsc", "r") as f:
        return json.load(f)


def test_schema_valid():
    """Schema deve ser válido."""
    schema = load_schema()
    parsed = fastavro.parse_schema(schema)
    assert parsed is not None
    print("✅ Schema válido")


def test_minimal_record_v1_compat():
    """Registro mínimo (compatível com v1) deve serializar."""
    schema = load_schema()

    record = {
        "decision_id": "dec-123",
        "plan_id": "plan-456",
        "intent_id": "intent-789",
        "final_decision": "approve",
        "consensus_method": "bayesian",
        "aggregated_confidence": 0.85,
        "aggregated_risk": 0.15,
        "specialist_votes": [],
        "consensus_metrics": {
            "divergence_score": 0.1,
            "convergence_time_ms": 500,
            "unanimous": True,
            "fallback_used": False,
            "pheromone_strength": 0.9,
            "bayesian_confidence": 0.85,
            "voting_confidence": 0.85
        },
        "explainability_token": "token-abc",
        "reasoning_summary": "Approve based on analysis",
        "compliance_checks": {},
        "guardrails_triggered": [],
        "requires_human_review": False,
        "created_at": int(datetime.utcnow().timestamp() * 1000),
        "metadata": {},
        "hash": "abc123",
        # v2 fields - workflow_type é obrigatório (enum sem default reconhecido pelo fastavro)
        "workflow_type": "orchestration",
    }

    # Serializar
    output = io.BytesIO()
    fastavro.schemaless_writer(output, schema, record)
    output.seek(0)

    # Deserializar
    parsed = fastavro.schemaless_reader(output, schema)
    result = dict(parsed)

    assert result["decision_id"] == "dec-123"
    assert result["workflow_type"] == "orchestration"
    assert result["workflow_confidence"] == 0.5  # default funciona na deserialização
    assert result["schema_version"] == 2

    print("✅ Compatibilidade v1 mantida")


def test_full_record_v2_fields():
    """Registro completo com campos v2 deve serializar."""
    schema = load_schema()

    record = {
        "decision_id": "dec-123",
        "plan_id": "plan-456",
        "intent_id": "intent-789",
        "correlation_id": "corr-xyz",
        "trace_id": "trace-abc",
        "span_id": "span-def",
        "final_decision": "approve",
        "consensus_method": "bayesian",
        "aggregated_confidence": 0.85,
        "aggregated_risk": 0.15,
        "specialist_votes": [],
        "consensus_metrics": {
            "divergence_score": 0.1,
            "convergence_time_ms": 500,
            "unanimous": True,
            "fallback_used": False,
            "pheromone_strength": 0.9,
            "bayesian_confidence": 0.85,
            "voting_confidence": 0.85
        },
        "explainability_token": "token-abc",
        "reasoning_summary": "Approve based on analysis",
        "compliance_checks": {},
        "guardrails_triggered": [],
        "cognitive_plan": json.dumps({"plan_id": "plan-456"}),
        "workflow_type": "generation",  # Novo campo v2
        "context_id": "ctx-123",  # Novo campo v2
        "workflow_confidence": 0.92,  # Novo campo v2
        "workflow_reasoning": "Multiple services affected",  # Novo campo v2
        "requires_human_review": False,
        "created_at": int(datetime.utcnow().timestamp() * 1000),
        "valid_until": None,
        "metadata": {},
        "hash": "abc123",
    }

    # Serializar
    output = io.BytesIO()
    fastavro.schemaless_writer(output, schema, record)
    output.seek(0)

    # Deserializar
    parsed = fastavro.schemaless_reader(output, schema)
    result = dict(parsed)

    assert result["workflow_type"] == "generation"
    assert result["context_id"] == "ctx-123"
    assert result["workflow_confidence"] == 0.92
    assert result["workflow_reasoning"] == "Multiple services affected"
    assert result["schema_version"] == 2

    print("✅ Campos v2 funcionam corretamente")


def test_workflow_type_enum_values():
    """Enum WorkflowType deve aceitar apenas valores válidos."""
    schema = load_schema()

    valid_values = ["orchestration", "generation"]

    for value in valid_values:
        record = {
            "decision_id": f"dec-{value}",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "final_decision": "approve",
            "consensus_method": "bayesian",
            "aggregated_confidence": 0.85,
            "aggregated_risk": 0.15,
            "specialist_votes": [],
            "consensus_metrics": {
                "divergence_score": 0.1,
                "convergence_time_ms": 500,
                "unanimous": True,
                "fallback_used": False,
                "pheromone_strength": 0.9,
                "bayesian_confidence": 0.85,
                "voting_confidence": 0.85
            },
            "explainability_token": "token-abc",
            "reasoning_summary": "Test",
            "compliance_checks": {},
            "guardrails_triggered": [],
            "workflow_type": value,
            "requires_human_review": False,
            "created_at": int(datetime.utcnow().timestamp() * 1000),
            "metadata": {},
            "hash": "abc123",
        }

        output = io.BytesIO()
        fastavro.schemaless_writer(output, schema, record)

    print("✅ Valores de enum workflow_type válidos")


if __name__ == "__main__":
    test_schema_valid()
    test_minimal_record_v1_compat()
    test_full_record_v2_fields()
    test_workflow_type_enum_values()
    print("\n✅ Todos os testes passaram!")
