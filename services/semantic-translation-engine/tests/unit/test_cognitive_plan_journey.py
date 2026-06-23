"""Testes unitários para os campos journey no CognitivePlan (Fase 3 / Task 4.2).

Valida que o modelo CognitivePlan ganha campos journey OPCIONAIS COM DEFAULT
(compat Avro — consumidores antigos ignoram), seguindo o padrão dos campos
workflow_type/workflow_confidence existentes.

Campos:
    - journey (str, default "UNKNOWN")
    - journey_id (str, default "")
    - journey_confidence (float, default 0.0)
    - journey_reasoning (str, default "")
    - journey_classification_method (str, default "")
"""

import pytest
from src.models.cognitive_plan import CognitivePlan, RiskBand, TaskNode


@pytest.fixture()
def minimal_valid_plan_data():
    """Dados mínimos para criar um CognitivePlan válido."""
    return {
        "intent_id": "intent-journey-001",
        "tasks": [TaskNode(task_id="task-1", task_type="query", description="Query database")],
        "execution_order": ["task-1"],
        "risk_score": 0.3,
        "risk_band": RiskBand.LOW,
        "explainability_token": "token-001",
        "reasoning_summary": "Simple query operation",
        "complexity_score": 0.2,
        "original_domain": "data_management",
        "original_priority": "normal",
        "original_security_level": "internal",
    }


class TestJourneyFieldsDefaults:
    """Campos journey têm defaults (compat Avro / consumidores antigos)."""

    def test_journey_defaults_when_absent(self, minimal_valid_plan_data):
        """Sem campos journey, o plano usa os defaults (não quebra)."""
        plan = CognitivePlan(**minimal_valid_plan_data)
        assert plan.journey == "UNKNOWN"
        assert plan.journey_id == ""
        assert plan.journey_confidence == 0.0
        assert plan.journey_reasoning == ""
        assert plan.journey_classification_method == ""

    def test_journey_fields_assigned(self, minimal_valid_plan_data):
        """Campos journey são aceites e preservados quando fornecidos."""
        plan = CognitivePlan(
            **minimal_valid_plan_data,
            journey="J3_BUILD",
            journey_id="jid-123",
            journey_confidence=0.95,
            journey_reasoning="Tier 1: workflow_type == generation",
            journey_classification_method="structured_signal",
        )
        assert plan.journey == "J3_BUILD"
        assert plan.journey_id == "jid-123"
        assert plan.journey_confidence == 0.95
        assert plan.journey_reasoning == "Tier 1: workflow_type == generation"
        assert plan.journey_classification_method == "structured_signal"


class TestJourneyFieldsValidation:
    """Validação anti-verde-falso de journey_confidence."""

    def test_journey_confidence_bounds(self, minimal_valid_plan_data):
        """journey_confidence fora de [0,1] é rejeitada (padrão do projeto)."""
        with pytest.raises(ValueError):
            CognitivePlan(**minimal_valid_plan_data, journey_confidence=1.5)
        with pytest.raises(ValueError):
            CognitivePlan(**minimal_valid_plan_data, journey_confidence=-0.1)


class TestJourneyFieldsAvro:
    """Serialização Avro inclui os campos journey (propagação a jusante)."""

    def test_to_avro_dict_includes_journey_fields(self, minimal_valid_plan_data):
        """to_avro_dict serializa os 5 campos journey (consumer downstream lê)."""
        plan = CognitivePlan(
            **minimal_valid_plan_data,
            journey="J2_ORCHESTRATE",
            journey_id="jid-abc",
            journey_confidence=0.8,
            journey_reasoning="Tier 1",
            journey_classification_method="structured_signal",
        )
        avro = plan.to_avro_dict()
        assert avro["journey"] == "J2_ORCHESTRATE"
        assert avro["journey_id"] == "jid-abc"
        assert avro["journey_confidence"] == 0.8
        assert avro["journey_reasoning"] == "Tier 1"
        assert avro["journey_classification_method"] == "structured_signal"

    def test_to_avro_dict_journey_defaults(self, minimal_valid_plan_data):
        """to_avro_dict expõe os defaults quando journey não foi decidida."""
        plan = CognitivePlan(**minimal_valid_plan_data)
        avro = plan.to_avro_dict()
        assert avro["journey"] == "UNKNOWN"
        assert avro["journey_id"] == ""
        assert avro["journey_confidence"] == 0.0
        assert avro["journey_reasoning"] == ""
        assert avro["journey_classification_method"] == ""
