"""
Testes de integração com MongoDB usando Testcontainers.
Valida persistência, indexação e integridade para LedgerClient e ExplainabilityGenerator.
"""

import pytest
import uuid
from datetime import datetime

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.ledger_client import LedgerClient
from neural_hive_specialists.explainability_generator import ExplainabilityGenerator


@pytest.mark.integration
def test_ledger_save_and_retrieve_opinion(mongodb_uri, sample_opinion):
    """Valida persistência e recuperação de parecer no MongoDB."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions",
        enable_circuit_breaker=False,
    )

    ledger = LedgerClient(config)

    # Salvar parecer
    opinion_id = ledger.save_opinion_with_fallback(sample_opinion)
    assert opinion_id

    # Recuperar parecer
    retrieved = ledger.get_opinion(opinion_id)
    assert retrieved is not None
    assert retrieved["opinion_id"] == opinion_id
    assert retrieved["specialist_type"] == sample_opinion["specialist_type"]
    assert retrieved["plan_id"] == sample_opinion["plan_id"]
    assert retrieved["recommendation"] == sample_opinion["recommendation"]
    assert retrieved["confidence_score"] == sample_opinion["confidence_score"]


@pytest.mark.integration
def test_ledger_get_opinions_by_plan(mongodb_uri):
    """Valida recuperação de múltiplos pareceres por plan_id."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_plan",
        enable_circuit_breaker=False,
    )

    ledger = LedgerClient(config)

    plan_id = f"plan-{uuid.uuid4()}"

    # Salvar 3 pareceres para o mesmo plano
    for i in range(3):
        opinion = {
            "opinion_id": f"opinion-{uuid.uuid4()}",
            "specialist_type": f"specialist-{i}",
            "specialist_version": "1.0.0",
            "plan_id": plan_id,
            "intent_id": f"intent-{uuid.uuid4()}",
            "correlation_id": f"corr-{uuid.uuid4()}",
            "recommendation": "approve",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.0,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "explainability_token": f"token-{i}",
            "processing_time_ms": 100.0,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {},
        }
        ledger.save_opinion_with_fallback(opinion)

    # Recuperar pareceres por plan_id
    opinions = ledger.get_opinions_by_plan(plan_id)
    assert len(opinions) == 3
    assert all(op["plan_id"] == plan_id for op in opinions)


@pytest.mark.integration
def test_ledger_verify_integrity(mongodb_uri):
    """Valida integridade de hash em parecer persistido."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_integrity",
        enable_circuit_breaker=False,
    )

    ledger = LedgerClient(config)

    opinion = {
        "opinion_id": f"opinion-{uuid.uuid4()}",
        "specialist_type": "test",
        "specialist_version": "1.0.0",
        "plan_id": f"plan-{uuid.uuid4()}",
        "intent_id": f"intent-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4()}",
        "recommendation": "approve",
        "confidence_score": 0.85,
        "risk_score": 0.2,
        "estimated_effort_hours": 8.0,
        "reasoning_factors": [],
        "suggested_mitigations": [],
        "explainability_token": "token-123",
        "processing_time_ms": 100.0,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {},
    }

    opinion_id = ledger.save_opinion_with_fallback(opinion)

    # Verificar integridade
    is_valid = ledger.verify_integrity(opinion_id)
    assert is_valid is True


@pytest.mark.integration
def test_ledger_index_creation(mongodb_uri):
    """Valida criação de índices MongoDB."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_indexes",
        enable_circuit_breaker=False,
    )

    ledger = LedgerClient(config)

    # Verificar índices criados
    indexes = list(ledger._collection.list_indexes())
    index_names = [idx["name"] for idx in indexes]

    # Validar índices esperados
    assert "opinion_id_1" in index_names
    assert "plan_id_1" in index_names
    assert "intent_id_1" in index_names
    assert "timestamp_-1" in index_names


@pytest.mark.integration
def test_explainability_save_and_retrieve(mongodb_uri):
    """Valida persistência e recuperação de explicabilidade no MongoDB."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_explainability_collection="test_explainability",
        enable_circuit_breaker=False,
        enable_explainability=True,
    )

    explainability_gen = ExplainabilityGenerator(config)

    # Dados de teste
    plan_data = {
        "plan_id": f"plan-{uuid.uuid4()}",
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "analysis",
                "required_capabilities": ["data_analysis"],
            }
        ],
    }

    evaluation = {
        "recommendation": "approve",
        "confidence_score": 0.85,
        "risk_score": 0.2,
    }

    # Gerar explicabilidade
    token, metadata = explainability_gen.generate(
        plan_data=plan_data, evaluation_result=evaluation, specialist_type="test"
    )

    assert token
    assert metadata
    assert metadata["method"] in ["heuristic", "shap", "lime"]

    # Recuperar explicabilidade
    retrieved = explainability_gen.get_explainability(token)
    assert retrieved is not None
    assert retrieved["explainability_token"] == token
    assert retrieved["specialist_type"] == "test"


@pytest.mark.integration
def test_ledger_buffer_flush_on_reconnect(mongodb_uri):
    """Valida flush de buffer quando reconectar ao MongoDB."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_buffer",
        ledger_buffer_size=10,
        enable_circuit_breaker=True,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_recovery_timeout=5,
    )

    ledger = LedgerClient(config)

    # Adicionar alguns pareceres ao buffer (simulando falha de conexão)
    opinions = []
    for i in range(5):
        opinion = {
            "opinion_id": f"opinion-buffer-{i}",
            "specialist_type": "test",
            "specialist_version": "1.0.0",
            "plan_id": f"plan-{uuid.uuid4()}",
            "intent_id": f"intent-{uuid.uuid4()}",
            "correlation_id": f"corr-{uuid.uuid4()}",
            "recommendation": "approve",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.0,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "explainability_token": f"token-{i}",
            "processing_time_ms": 100.0,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {},
        }
        opinions.append(opinion)

    # Tentar salvar com sucesso (conexão funcional)
    for opinion in opinions:
        opinion_id = ledger.save_opinion_with_fallback(opinion)
        assert opinion_id

    # Validar que todos foram salvos
    for opinion in opinions:
        retrieved = ledger.get_opinion(opinion["opinion_id"])
        assert retrieved is not None
        assert retrieved["opinion_id"] == opinion["opinion_id"]


@pytest.mark.integration
def test_ledger_get_opinions_by_intent(mongodb_uri):
    """Valida recuperação de pareceres por intent_id."""
    config = SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        mongodb_uri=mongodb_uri,
        mongodb_database="test_integration_db",
        mongodb_opinions_collection="test_opinions_intent",
        enable_circuit_breaker=False,
    )

    ledger = LedgerClient(config)

    intent_id = f"intent-{uuid.uuid4()}"

    # Salvar 2 pareceres para o mesmo intent
    for i in range(2):
        opinion = {
            "opinion_id": f"opinion-{uuid.uuid4()}",
            "specialist_type": "test",
            "specialist_version": "1.0.0",
            "plan_id": f"plan-{uuid.uuid4()}",
            "intent_id": intent_id,
            "correlation_id": f"corr-{uuid.uuid4()}",
            "recommendation": "approve",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.0,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "explainability_token": f"token-{i}",
            "processing_time_ms": 100.0,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {},
        }
        ledger.save_opinion_with_fallback(opinion)

    # Recuperar pareceres por intent_id
    opinions = ledger.get_opinions_by_intent(intent_id)
    assert len(opinions) == 2
    assert all(op["intent_id"] == intent_id for op in opinions)
