"""
Testes de serialização Avro para ConsolidatedDecision.

Valida que o campo cognitive_plan é corretamente serializado como JSON string
no formato Avro e pode ser deserializado de volta para dict.
"""

import json
import pytest
import uuid
from datetime import datetime, timezone

from src.models.consolidated_decision import (
    ConsolidatedDecision,
    DecisionType,
    ConsensusMethod,
    SpecialistVote,
    ConsensusMetrics,
)


@pytest.fixture
def sample_cognitive_plan_for_avro():
    """Plano cognitivo completo para testes de serialização Avro."""
    return {
        "plan_id": str(uuid.uuid4()),
        "version": "1.0",
        "intent_id": str(uuid.uuid4()),
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "code_generation",
                "description": "Generate API endpoint",
                "dependencies": [],
                "parameters": {"language": "python", "framework": "fastapi"},
            },
            {
                "task_id": "task-2",
                "task_type": "test_generation",
                "description": "Generate unit tests",
                "dependencies": ["task-1"],
                "parameters": {"coverage_target": 80},
            },
        ],
        "execution_order": ["task-1", "task-2"],
        "risk_score": 0.25,
        "risk_band": "medium",
        "explainability_token": "exp-token-123",
        "reasoning_summary": "Plan approved by all specialists",
        "status": "approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"created_by": "semantic-translation-engine"},
    }


@pytest.fixture
def sample_specialist_votes():
    """Votos de especialistas para testes."""
    return [
        SpecialistVote(
            specialist_type="business",
            opinion_id=str(uuid.uuid4()),
            confidence_score=0.85,
            risk_score=0.2,
            recommendation="approve",
            weight=0.2,
            processing_time_ms=100,
        ),
        SpecialistVote(
            specialist_type="technical",
            opinion_id=str(uuid.uuid4()),
            confidence_score=0.88,
            risk_score=0.15,
            recommendation="approve",
            weight=0.2,
            processing_time_ms=120,
        ),
    ]


@pytest.fixture
def sample_consensus_metrics():
    """Métricas de consenso para testes."""
    return ConsensusMetrics(
        divergence_score=0.1,
        convergence_time_ms=500,
        unanimous=True,
        fallback_used=False,
        pheromone_strength=0.7,
        bayesian_confidence=0.87,
        voting_confidence=0.85,
    )


@pytest.fixture
def consolidated_decision_with_plan(
    sample_cognitive_plan_for_avro, sample_specialist_votes, sample_consensus_metrics
):
    """ConsolidatedDecision completa com cognitive_plan populado."""
    return ConsolidatedDecision(
        decision_id=str(uuid.uuid4()),
        plan_id=sample_cognitive_plan_for_avro["plan_id"],
        intent_id=sample_cognitive_plan_for_avro["intent_id"],
        correlation_id=str(uuid.uuid4()),
        final_decision=DecisionType.APPROVE,
        consensus_method=ConsensusMethod.BAYESIAN,
        aggregated_confidence=0.86,
        aggregated_risk=0.18,
        specialist_votes=sample_specialist_votes,
        consensus_metrics=sample_consensus_metrics,
        explainability_token="exp-token-123",
        reasoning_summary="All specialists approved the plan",
        compliance_checks={"security": True, "data_privacy": True},
        guardrails_triggered=[],
        requires_human_review=False,
        cognitive_plan=sample_cognitive_plan_for_avro,
        metadata={"source": "consensus-engine"},
    )


class TestCognitivePlanAvroSerialization:
    """Testes de serialização do campo cognitive_plan para formato Avro."""

    def test_cognitive_plan_serialized_as_json_string(
        self, consolidated_decision_with_plan
    ):
        """Valida que cognitive_plan é serializado como JSON string no Avro dict."""
        avro_dict = consolidated_decision_with_plan.to_avro_dict()

        # cognitive_plan deve ser uma string JSON
        assert isinstance(avro_dict["cognitive_plan"], str)

        # Deve ser JSON válido
        parsed = json.loads(avro_dict["cognitive_plan"])
        assert isinstance(parsed, dict)

    def test_cognitive_plan_preserves_structure_after_serialization(
        self, consolidated_decision_with_plan, sample_cognitive_plan_for_avro
    ):
        """Valida que a estrutura do cognitive_plan é preservada após serialização/deserialização."""
        avro_dict = consolidated_decision_with_plan.to_avro_dict()

        # Deserializar o JSON string
        parsed_plan = json.loads(avro_dict["cognitive_plan"])

        # Validar campos principais
        assert parsed_plan["plan_id"] == sample_cognitive_plan_for_avro["plan_id"]
        assert parsed_plan["version"] == sample_cognitive_plan_for_avro["version"]
        assert parsed_plan["intent_id"] == sample_cognitive_plan_for_avro["intent_id"]

        # Validar tasks
        assert len(parsed_plan["tasks"]) == 2
        assert parsed_plan["tasks"][0]["task_id"] == "task-1"
        assert parsed_plan["tasks"][0]["task_type"] == "code_generation"
        assert parsed_plan["tasks"][1]["dependencies"] == ["task-1"]

        # Validar execution_order
        assert parsed_plan["execution_order"] == ["task-1", "task-2"]

        # Validar risk data
        assert parsed_plan["risk_score"] == 0.25
        assert parsed_plan["risk_band"] == "medium"

    def test_cognitive_plan_none_serializes_to_null(
        self, sample_specialist_votes, sample_consensus_metrics
    ):
        """Valida que cognitive_plan=None resulta em null no Avro dict."""
        decision = ConsolidatedDecision(
            plan_id=str(uuid.uuid4()),
            intent_id=str(uuid.uuid4()),
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.VOTING,
            aggregated_confidence=0.85,
            aggregated_risk=0.15,
            specialist_votes=sample_specialist_votes,
            consensus_metrics=sample_consensus_metrics,
            explainability_token="token-123",
            reasoning_summary="Approved",
            cognitive_plan=None,  # Explicitamente None
        )

        avro_dict = decision.to_avro_dict()

        # cognitive_plan deve ser None (null no Avro)
        assert avro_dict["cognitive_plan"] is None

    def test_cognitive_plan_empty_dict_serializes_to_json_empty_object(
        self, sample_specialist_votes, sample_consensus_metrics
    ):
        """Valida que cognitive_plan={} serializa para JSON string '{}'."""
        decision = ConsolidatedDecision(
            plan_id=str(uuid.uuid4()),
            intent_id=str(uuid.uuid4()),
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.VOTING,
            aggregated_confidence=0.85,
            aggregated_risk=0.15,
            specialist_votes=sample_specialist_votes,
            consensus_metrics=sample_consensus_metrics,
            explainability_token="token-123",
            reasoning_summary="Approved",
            cognitive_plan={},  # Dict vazio
        )

        avro_dict = decision.to_avro_dict()

        # cognitive_plan deve ser string JSON de objeto vazio
        assert avro_dict["cognitive_plan"] == "{}"
        assert json.loads(avro_dict["cognitive_plan"]) == {}

    def test_cognitive_plan_with_nested_objects(
        self, sample_specialist_votes, sample_consensus_metrics
    ):
        """Valida serialização de cognitive_plan com objetos aninhados complexos."""
        complex_plan = {
            "plan_id": "plan-complex",
            "tasks": [
                {
                    "task_id": "t1",
                    "parameters": {
                        "nested": {"deep": {"value": 123}},
                        "list": [1, 2, {"three": 3}],
                    },
                }
            ],
            "metadata": {
                "annotations": {"key1": "value1", "key2": ["a", "b", "c"]},
                "numbers": [1.5, 2.5, 3.5],
            },
        }

        decision = ConsolidatedDecision(
            plan_id="plan-complex",
            intent_id=str(uuid.uuid4()),
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.9,
            aggregated_risk=0.1,
            specialist_votes=sample_specialist_votes,
            consensus_metrics=sample_consensus_metrics,
            explainability_token="token-123",
            reasoning_summary="Approved",
            cognitive_plan=complex_plan,
        )

        avro_dict = decision.to_avro_dict()
        parsed = json.loads(avro_dict["cognitive_plan"])

        # Validar estrutura aninhada preservada
        assert parsed["tasks"][0]["parameters"]["nested"]["deep"]["value"] == 123
        assert parsed["tasks"][0]["parameters"]["list"][2]["three"] == 3
        assert parsed["metadata"]["annotations"]["key2"] == ["a", "b", "c"]
        assert parsed["metadata"]["numbers"] == [1.5, 2.5, 3.5]

    def test_avro_dict_field_order_includes_cognitive_plan(
        self, consolidated_decision_with_plan
    ):
        """Valida que cognitive_plan está presente no Avro dict na posição correta."""
        avro_dict = consolidated_decision_with_plan.to_avro_dict()

        # Verificar que o campo existe
        assert "cognitive_plan" in avro_dict

        # Verificar campos vizinhos (ordem conforme schema Avro)
        keys = list(avro_dict.keys())
        assert "guardrails_triggered" in keys
        assert "requires_human_review" in keys

        # cognitive_plan deve estar entre guardrails_triggered e requires_human_review
        guardrails_idx = keys.index("guardrails_triggered")
        cognitive_plan_idx = keys.index("cognitive_plan")
        requires_human_idx = keys.index("requires_human_review")

        assert guardrails_idx < cognitive_plan_idx < requires_human_idx


class TestCognitivePlanDeserialization:
    """Testes simulando deserialização do formato Avro (JSON string -> dict)."""

    def test_deserialize_cognitive_plan_json_string(
        self, sample_cognitive_plan_for_avro
    ):
        """Simula deserialização de cognitive_plan vindo do Avro como JSON string."""
        # Simular mensagem Avro deserializada
        avro_message = {
            "decision_id": str(uuid.uuid4()),
            "plan_id": sample_cognitive_plan_for_avro["plan_id"],
            "intent_id": sample_cognitive_plan_for_avro["intent_id"],
            "cognitive_plan": json.dumps(sample_cognitive_plan_for_avro),  # JSON string
        }

        # Lógica de deserialização (como no FlowCConsumer)
        cognitive_plan = avro_message.get("cognitive_plan")
        if isinstance(cognitive_plan, str):
            cognitive_plan = json.loads(cognitive_plan)

        # Validar que é dict após deserialização
        assert isinstance(cognitive_plan, dict)
        assert cognitive_plan["plan_id"] == sample_cognitive_plan_for_avro["plan_id"]
        assert len(cognitive_plan["tasks"]) == 2

    def test_deserialize_cognitive_plan_already_dict(
        self, sample_cognitive_plan_for_avro
    ):
        """Valida que cognitive_plan já como dict não quebra a deserialização."""
        # Simular mensagem com cognitive_plan já como dict (fallback JSON sem Avro)
        message = {
            "decision_id": str(uuid.uuid4()),
            "cognitive_plan": sample_cognitive_plan_for_avro,  # Já é dict
        }

        # Lógica de deserialização
        cognitive_plan = message.get("cognitive_plan")
        if isinstance(cognitive_plan, str):
            cognitive_plan = json.loads(cognitive_plan)

        # Deve continuar sendo dict
        assert isinstance(cognitive_plan, dict)
        assert cognitive_plan["plan_id"] == sample_cognitive_plan_for_avro["plan_id"]

    def test_deserialize_cognitive_plan_null(self):
        """Valida que cognitive_plan=null é tratado corretamente."""
        message = {
            "decision_id": str(uuid.uuid4()),
            "cognitive_plan": None,  # null no Avro
        }

        cognitive_plan = message.get("cognitive_plan")
        if isinstance(cognitive_plan, str):
            cognitive_plan = json.loads(cognitive_plan)

        # Deve permanecer None
        assert cognitive_plan is None


class TestAvroSchemaCompatibility:
    """Testes de compatibilidade com o schema Avro definido."""

    def test_to_avro_dict_produces_valid_avro_types(
        self, consolidated_decision_with_plan
    ):
        """Valida que to_avro_dict() produz tipos compatíveis com o schema Avro."""
        avro_dict = consolidated_decision_with_plan.to_avro_dict()

        # Campos string
        assert isinstance(avro_dict["decision_id"], str)
        assert isinstance(avro_dict["plan_id"], str)
        assert isinstance(avro_dict["intent_id"], str)

        # Campos enum (string no Avro)
        assert avro_dict["final_decision"] in ["approve", "reject", "review_required", "conditional"]
        assert avro_dict["consensus_method"] in ["bayesian", "voting", "unanimous", "fallback"]

        # Campos double
        assert isinstance(avro_dict["aggregated_confidence"], float)
        assert isinstance(avro_dict["aggregated_risk"], float)

        # Campos array
        assert isinstance(avro_dict["specialist_votes"], list)
        assert isinstance(avro_dict["guardrails_triggered"], list)

        # Campo cognitive_plan (union null/string)
        assert avro_dict["cognitive_plan"] is None or isinstance(avro_dict["cognitive_plan"], str)

        # Campo timestamp (long em ms)
        assert isinstance(avro_dict["created_at"], int)

        # Campo map<string>
        assert isinstance(avro_dict["metadata"], dict)
        for v in avro_dict["metadata"].values():
            assert isinstance(v, str)
