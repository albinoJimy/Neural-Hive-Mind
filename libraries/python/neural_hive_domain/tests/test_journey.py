"""Tests for the Journey enum and JourneyDecision model (Fase 0)."""

import json

import pytest
from pydantic import BaseModel, ValidationError

from neural_hive_domain import Journey, JourneyDecision


class TestJourneyValues:
    """Test Journey enum values."""

    def test_has_five_values(self):
        """Verify Journey has exactly 5 values (J1-J4 + UNKNOWN)."""
        assert len(list(Journey)) == 5

    def test_expected_journeys_exist(self):
        """Verify all expected journeys are defined with name == value."""
        expected = [
            "J1_PLAN_ONLY",
            "J2_ORCHESTRATE",
            "J3_BUILD",
            "J4_MIGRATE",
            "UNKNOWN",
        ]
        for journey_name in expected:
            assert hasattr(Journey, journey_name)
            assert getattr(Journey, journey_name).value == journey_name

    def test_unknown_exists(self):
        """Verify UNKNOWN journey exists (anti-verde-falso)."""
        assert Journey.UNKNOWN.value == "UNKNOWN"

    def test_values_equal_names(self):
        """Verify every value matches its member name."""
        for journey in Journey:
            assert journey.value == journey.name


class TestJourneySerialization:
    """Test Journey serialization behavior (str + Enum)."""

    def test_string_conversion(self):
        """Verify journeys convert to their string value."""
        assert str(Journey.J3_BUILD) == "J3_BUILD"
        assert str(Journey.UNKNOWN) == "UNKNOWN"

    def test_string_equality(self):
        """Verify journeys are equal to their string values."""
        assert Journey.J1_PLAN_ONLY == "J1_PLAN_ONLY"
        assert Journey.J4_MIGRATE == "J4_MIGRATE"

    def test_json_serialization(self):
        """Verify journeys serialize to JSON correctly."""
        serialized = json.dumps(Journey.J2_ORCHESTRATE)
        assert serialized == '"J2_ORCHESTRATE"'

    def test_json_deserialization(self):
        """Verify journeys deserialize from JSON correctly."""
        value = json.loads('"J3_BUILD"')
        assert Journey(value) == Journey.J3_BUILD


class TestJourneyDecision:
    """Test the JourneyDecision Pydantic model."""

    def test_accepts_all_fields(self):
        """Verify JourneyDecision accepts all required fields."""
        decision = JourneyDecision(
            journey=Journey.J3_BUILD,
            journey_id="abc-123",
            confidence=0.92,
            reasoning="workflow_type indicates build",
            classification_method="structured_signal",
        )
        assert decision.journey == Journey.J3_BUILD
        assert decision.journey_id == "abc-123"
        assert decision.confidence == 0.92
        assert decision.reasoning == "workflow_type indicates build"
        assert decision.classification_method == "structured_signal"

    def test_journey_from_string(self):
        """Verify JourneyDecision coerces a string into a Journey."""
        decision = JourneyDecision(
            journey="J1_PLAN_ONLY",
            journey_id="id-1",
            confidence=0.5,
            reasoning="execution_mode plan-only",
            classification_method="structured_signal",
        )
        assert decision.journey == Journey.J1_PLAN_ONLY

    def test_classification_method_field(self):
        """Verify classification_method captures the decision provenance."""
        for method in ("structured_signal", "llm", "no_match"):
            decision = JourneyDecision(
                journey=Journey.UNKNOWN,
                journey_id="id-x",
                confidence=0.0,
                reasoning="ambiguous",
                classification_method=method,
            )
            assert decision.classification_method == method

    def test_unknown_decision(self):
        """Verify a low-confidence UNKNOWN decision is representable."""
        decision = JourneyDecision(
            journey=Journey.UNKNOWN,
            journey_id="id-unknown",
            confidence=0.0,
            reasoning="no strong signal",
            classification_method="no_match",
        )
        assert decision.journey == Journey.UNKNOWN

    def test_serialization_str_of_journey(self):
        """Verify model_dump serializes journey as its string value."""
        decision = JourneyDecision(
            journey=Journey.J4_MIGRATE,
            journey_id="id-mig",
            confidence=0.8,
            reasoning="source=doc-ingestion",
            classification_method="structured_signal",
        )
        data = decision.model_dump()
        assert data["journey"] == "J4_MIGRATE"

        json_str = decision.model_dump_json()
        assert '"J4_MIGRATE"' in json_str

    def test_invalid_journey_raises(self):
        """Verify an invalid journey value raises a ValidationError."""
        with pytest.raises(ValidationError):
            JourneyDecision(
                journey="J9_INVALID",
                journey_id="id-bad",
                confidence=0.1,
                reasoning="invalid",
                classification_method="no_match",
            )

    def test_missing_required_field_raises(self):
        """Verify missing a required field raises a ValidationError."""
        with pytest.raises(ValidationError):
            JourneyDecision(
                journey=Journey.J1_PLAN_ONLY,
                journey_id="id-1",
                confidence=0.5,
                reasoning="missing classification_method",
            )

    def test_confidence_out_of_range_raises(self):
        """Anti-verde-falso: confidence fora de [0,1] falha (não aceita inválido)."""
        for bad in (1.5, -0.3):
            with pytest.raises(ValidationError):
                JourneyDecision(
                    journey=Journey.J2_ORCHESTRATE,
                    journey_id="id-c",
                    confidence=bad,
                    reasoning="out of range",
                    classification_method="structured_signal",
                )

    def test_invalid_classification_method_raises(self):
        """Contrato fechado: classification_method fora do Literal falha."""
        with pytest.raises(ValidationError):
            JourneyDecision(
                journey=Journey.J2_ORCHESTRATE,
                journey_id="id-m",
                confidence=0.5,
                reasoning="bad method",
                classification_method="keyword_rules",
            )
