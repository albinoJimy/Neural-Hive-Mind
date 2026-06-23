"""Testes unitarios para JourneyClassifier (Tier 1 - sinais estruturados, sem LLM).

Fase 1 da spec journey-router (Task 2). Cobre:
- cada sinal estruturado -> jornada correta;
- classification_method correto ("structured_signal" / "no_match");
- UNKNOWN quando nao ha sinal (Tier 2/LLM ainda nao existe);
- precedencia dos sinais (source vence workflow_type);
- acesso defensivo (intent_envelope/cognitive_plan vazios nao rebentam);
- nenhuma invocacao de LLM no Tier 1.
"""

from neural_hive_domain import Journey, JourneyDecision
from src.services.journey_classifier import (
    JOURNEY_CONFIDENCE_THRESHOLD,
    JourneyClassifier,
)


class TestJourneyClassifierStructuredSignals:
    """Tier 1: cada sinal estruturado resolve a jornada deterministicamente."""

    def test_doc_ingestion_source_resolves_j4_migrate(self):
        classifier = JourneyClassifier()
        envelope = {"context": {"source": "doc-ingestion"}}

        decision = classifier.classify(envelope, {})

        assert isinstance(decision, JourneyDecision)
        assert decision.journey == Journey.J4_MIGRATE
        assert decision.classification_method == "structured_signal"
        assert decision.confidence >= 0.9

    def test_execution_mode_plan_only_resolves_j1_plan_only(self):
        classifier = JourneyClassifier()
        envelope = {"constraints": {"execution_mode": "plan_only"}}

        decision = classifier.classify(envelope, {})

        assert decision.journey == Journey.J1_PLAN_ONLY
        assert decision.classification_method == "structured_signal"

    def test_workflow_type_generation_resolves_j3_build(self):
        classifier = JourneyClassifier()
        plan = {"workflow_type": "GENERATION"}

        decision = classifier.classify({}, plan)

        assert decision.journey == Journey.J3_BUILD
        assert decision.classification_method == "structured_signal"

    def test_workflow_type_orchestration_resolves_j2_orchestrate(self):
        classifier = JourneyClassifier()
        plan = {"workflow_type": "ORCHESTRATION"}

        decision = classifier.classify({}, plan)

        assert decision.journey == Journey.J2_ORCHESTRATE
        assert decision.classification_method == "structured_signal"

    def test_workflow_type_lowercase_value_resolves(self):
        """O valor canonico de WorkflowType e lowercase ('generation')."""
        classifier = JourneyClassifier()

        decision = classifier.classify({}, {"workflow_type": "generation"})

        assert decision.journey == Journey.J3_BUILD
        assert decision.classification_method == "structured_signal"


class TestJourneyClassifierPrecedence:
    """A ordem de precedencia dos sinais deve ser respeitada."""

    def test_source_beats_workflow_type(self):
        classifier = JourneyClassifier()
        envelope = {"context": {"source": "doc-ingestion"}}
        plan = {"workflow_type": "GENERATION"}

        decision = classifier.classify(envelope, plan)

        assert decision.journey == Journey.J4_MIGRATE

    def test_plan_only_beats_workflow_type(self):
        classifier = JourneyClassifier()
        envelope = {"constraints": {"execution_mode": "plan_only"}}
        plan = {"workflow_type": "ORCHESTRATION"}

        decision = classifier.classify(envelope, plan)

        assert decision.journey == Journey.J1_PLAN_ONLY

    def test_source_beats_plan_only(self):
        classifier = JourneyClassifier()
        envelope = {
            "context": {"source": "doc-ingestion"},
            "constraints": {"execution_mode": "plan_only"},
        }

        decision = classifier.classify(envelope, {})

        assert decision.journey == Journey.J4_MIGRATE


class TestJourneyClassifierAntiVerdeFalso:
    """Sem sinal forte -> UNKNOWN (Tier 2/LLM e Fase 2, ainda nao existe)."""

    def test_no_signal_returns_unknown_no_match(self):
        classifier = JourneyClassifier()

        decision = classifier.classify({}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"
        assert decision.confidence < JOURNEY_CONFIDENCE_THRESHOLD

    def test_unrecognized_workflow_type_returns_unknown(self):
        classifier = JourneyClassifier()

        decision = classifier.classify({}, {"workflow_type": "SOMETHING_ELSE"})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    def test_unrecognized_source_does_not_force_journey(self):
        classifier = JourneyClassifier()
        envelope = {"context": {"source": "gateway"}}

        decision = classifier.classify(envelope, {})

        assert decision.journey == Journey.UNKNOWN


class TestJourneyClassifierDefensiveAccess:
    """Campos em falta nao podem rebentar (acesso defensivo)."""

    def test_empty_dicts_do_not_raise(self):
        classifier = JourneyClassifier()

        decision = classifier.classify({}, {})

        assert decision.journey == Journey.UNKNOWN

    def test_none_context_does_not_raise(self):
        classifier = JourneyClassifier()
        envelope = {"context": None, "constraints": None}

        decision = classifier.classify(envelope, {})

        assert decision.journey == Journey.UNKNOWN

    def test_none_cognitive_plan_does_not_raise(self):
        classifier = JourneyClassifier()

        decision = classifier.classify({"context": {"source": "doc-ingestion"}}, None)

        assert decision.journey == Journey.J4_MIGRATE

    def test_context_not_a_dict_does_not_raise(self):
        classifier = JourneyClassifier()
        envelope = {"context": "unexpected", "constraints": []}

        decision = classifier.classify(envelope, {})

        assert decision.journey == Journey.UNKNOWN


class TestJourneyClassifierContract:
    """Contrato da decisao: journey_id, reasoning, threshold configuravel."""

    def test_journey_id_is_unique_uuid(self):
        classifier = JourneyClassifier()

        d1 = classifier.classify({}, {"workflow_type": "GENERATION"})
        d2 = classifier.classify({}, {"workflow_type": "GENERATION"})

        assert d1.journey_id and d2.journey_id
        assert d1.journey_id != d2.journey_id

    def test_reasoning_is_always_present(self):
        classifier = JourneyClassifier()

        decision = classifier.classify({}, {})

        assert decision.reasoning
        assert isinstance(decision.reasoning, str)

    def test_threshold_default_constant(self):
        classifier = JourneyClassifier()

        assert classifier.confidence_threshold == JOURNEY_CONFIDENCE_THRESHOLD

    def test_threshold_read_from_settings(self):
        class FakeSettings:
            journey_confidence_threshold = 0.42

        classifier = JourneyClassifier(settings=FakeSettings())

        assert classifier.confidence_threshold == 0.42

    def test_tier1_does_not_invoke_llm(self):
        """Tier 1 nunca chama o LLM (nem no caminho com sinal nem no sem-sinal)."""
        from unittest.mock import patch

        classifier = JourneyClassifier()

        with patch.object(classifier, "_classify_llm") as mock_llm:
            # caminho com sinal estruturado
            classifier.classify({}, {"workflow_type": "GENERATION"})
            # caminho sem sinal (cai em UNKNOWN, NÃO no LLM)
            classifier.classify({}, {})
            assert mock_llm.call_count == 0

    def test_classify_llm_hook_not_implemented(self):
        """O gancho de Fase 2 existe mas ainda não está implementado."""
        import pytest

        classifier = JourneyClassifier()
        with pytest.raises(NotImplementedError):
            classifier._classify_llm({}, {})

    def test_all_three_signals_present_source_wins(self):
        """Precedência total: source(J4) > execution_mode(J1) > workflow_type."""
        classifier = JourneyClassifier()
        decision = classifier.classify(
            {
                "context": {"source": "doc-ingestion"},
                "constraints": {"execution_mode": "plan_only"},
            },
            {"workflow_type": "generation"},
        )
        assert decision.journey == Journey.J4_MIGRATE

    def test_intent_envelope_none_does_not_raise(self):
        """envelope=None com plano ativo → defensivo, roteia pelo workflow_type."""
        classifier = JourneyClassifier()
        decision = classifier.classify(None, {"workflow_type": "orchestration"})
        assert decision.journey == Journey.J2_ORCHESTRATE

    def test_workflow_type_as_enum_object_falls_back_unknown(self):
        """workflow_type não-string (enum cru) é tratado defensivamente → UNKNOWN."""
        classifier = JourneyClassifier()

        class _FakeEnum:
            value = "generation"

        decision = classifier.classify({}, {"workflow_type": _FakeEnum()})
        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"
