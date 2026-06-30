"""Testes unitarios para JourneyClassifier (Tier 1 estruturado + Tier 2 LLM).

Spec journey-router. `classify()` e `_classify_llm()` sao ASYNC; o pytest deste
servico tem asyncio_mode=auto (pytest.ini), portanto os testes async correm sem
marcadores explicitos. Cobre:
- Tier 1: cada sinal estruturado -> jornada correta (sincrono, sem await LLM);
- classification_method correto ("structured_signal" / "no_match" / "llm");
- UNKNOWN quando nao ha sinal e nao ha (ou falha) o LLM (anti-verde-falso);
- precedencia dos sinais (source vence workflow_type);
- acesso defensivo (intent_envelope/cognitive_plan vazios nao rebentam);
- nenhuma invocacao de LLM no Tier 1;
- Tier 2: parsing defensivo, fallbacks e extracao de JSON ruidoso.
"""

from neural_hive_domain import Journey, JourneyDecision
from src.services.journey_classifier import (
    JOURNEY_CONFIDENCE_THRESHOLD,
    JourneyClassifier,
)


class TestJourneyClassifierStructuredSignals:
    """Tier 1: cada sinal estruturado resolve a jornada deterministicamente."""

    async def test_doc_ingestion_source_resolves_j4_migrate(self):
        classifier = JourneyClassifier()
        envelope = {"context": {"source": "doc-ingestion"}}

        decision = await classifier.classify(envelope, {})

        assert isinstance(decision, JourneyDecision)
        assert decision.journey == Journey.J4_MIGRATE
        assert decision.classification_method == "structured_signal"
        assert decision.confidence >= 0.9

    async def test_execution_mode_plan_only_resolves_j1_plan_only(self):
        classifier = JourneyClassifier()
        envelope = {"constraints": {"execution_mode": "plan_only"}}

        decision = await classifier.classify(envelope, {})

        assert decision.journey == Journey.J1_PLAN_ONLY
        assert decision.classification_method == "structured_signal"

    async def test_workflow_type_generation_resolves_j3_build(self):
        classifier = JourneyClassifier()
        plan = {"workflow_type": "GENERATION"}

        decision = await classifier.classify({}, plan)

        assert decision.journey == Journey.J3_BUILD
        assert decision.classification_method == "structured_signal"

    async def test_workflow_type_orchestration_resolves_j2_orchestrate(self):
        classifier = JourneyClassifier()
        plan = {"workflow_type": "ORCHESTRATION"}

        decision = await classifier.classify({}, plan)

        assert decision.journey == Journey.J2_ORCHESTRATE
        assert decision.classification_method == "structured_signal"

    async def test_workflow_type_lowercase_value_resolves(self):
        """O valor canonico de WorkflowType e lowercase ('generation')."""
        classifier = JourneyClassifier()

        decision = await classifier.classify({}, {"workflow_type": "generation"})

        assert decision.journey == Journey.J3_BUILD
        assert decision.classification_method == "structured_signal"


class TestJourneyClassifierPrecedence:
    """A ordem de precedencia dos sinais deve ser respeitada."""

    async def test_source_beats_workflow_type(self):
        classifier = JourneyClassifier()
        envelope = {"context": {"source": "doc-ingestion"}}
        plan = {"workflow_type": "GENERATION"}

        decision = await classifier.classify(envelope, plan)

        assert decision.journey == Journey.J4_MIGRATE

    async def test_plan_only_beats_workflow_type(self):
        classifier = JourneyClassifier()
        envelope = {"constraints": {"execution_mode": "plan_only"}}
        plan = {"workflow_type": "ORCHESTRATION"}

        decision = await classifier.classify(envelope, plan)

        assert decision.journey == Journey.J1_PLAN_ONLY

    async def test_source_beats_plan_only(self):
        classifier = JourneyClassifier()
        envelope = {
            "context": {"source": "doc-ingestion"},
            "constraints": {"execution_mode": "plan_only"},
        }

        decision = await classifier.classify(envelope, {})

        assert decision.journey == Journey.J4_MIGRATE


class TestJourneyClassifierAntiVerdeFalso:
    """Sem sinal forte e sem LLM -> UNKNOWN (anti-verde-falso)."""

    async def test_no_signal_returns_unknown_no_match(self):
        classifier = JourneyClassifier()

        decision = await classifier.classify({}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"
        assert decision.confidence < JOURNEY_CONFIDENCE_THRESHOLD

    async def test_unrecognized_workflow_type_returns_unknown(self):
        classifier = JourneyClassifier()

        decision = await classifier.classify({}, {"workflow_type": "SOMETHING_ELSE"})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_unrecognized_source_does_not_force_journey(self):
        classifier = JourneyClassifier()
        envelope = {"context": {"source": "gateway"}}

        decision = await classifier.classify(envelope, {})

        assert decision.journey == Journey.UNKNOWN


class TestJourneyClassifierDefensiveAccess:
    """Campos em falta nao podem rebentar (acesso defensivo)."""

    async def test_empty_dicts_do_not_raise(self):
        classifier = JourneyClassifier()

        decision = await classifier.classify({}, {})

        assert decision.journey == Journey.UNKNOWN

    async def test_none_context_does_not_raise(self):
        classifier = JourneyClassifier()
        envelope = {"context": None, "constraints": None}

        decision = await classifier.classify(envelope, {})

        assert decision.journey == Journey.UNKNOWN

    async def test_none_cognitive_plan_does_not_raise(self):
        classifier = JourneyClassifier()

        decision = await classifier.classify({"context": {"source": "doc-ingestion"}}, None)

        assert decision.journey == Journey.J4_MIGRATE

    async def test_context_not_a_dict_does_not_raise(self):
        classifier = JourneyClassifier()
        envelope = {"context": "unexpected", "constraints": []}

        decision = await classifier.classify(envelope, {})

        assert decision.journey == Journey.UNKNOWN


class TestJourneyClassifierContract:
    """Contrato da decisao: journey_id, reasoning, threshold configuravel."""

    async def test_journey_id_is_unique_uuid(self):
        classifier = JourneyClassifier()

        d1 = await classifier.classify({}, {"workflow_type": "GENERATION"})
        d2 = await classifier.classify({}, {"workflow_type": "GENERATION"})

        assert d1.journey_id and d2.journey_id
        assert d1.journey_id != d2.journey_id

    async def test_reasoning_is_always_present(self):
        classifier = JourneyClassifier()

        decision = await classifier.classify({}, {})

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

    async def test_tier1_does_not_invoke_llm(self):
        """Tier 1 nunca chama o LLM (nem no caminho com sinal nem no sem-sinal).

        Sem llm_client injetado, o caminho sem-sinal cai em _no_match sem nunca
        tocar no _classify_llm.
        """
        from unittest.mock import AsyncMock, patch

        classifier = JourneyClassifier()

        with patch.object(classifier, "_classify_llm", new=AsyncMock()) as mock_llm:
            # caminho com sinal estruturado
            await classifier.classify({}, {"workflow_type": "GENERATION"})
            # caminho sem sinal (cai em UNKNOWN, NÃO no LLM, pois nao ha client)
            await classifier.classify({}, {})
            assert mock_llm.await_count == 0

    async def test_no_client_no_signal_returns_no_match_not_raises(self):
        """Comportamento real de produção: sem llm_client, o caminho sem-sinal
        devolve UNKNOWN/no_match — o NotImplementedError de _classify_llm NUNCA
        é exposto ao fluxo (classify só chama o LLM quando ha client).
        """
        classifier = JourneyClassifier()  # sem client

        decision = await classifier.classify({"intent": {"text": "ambíguo"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_all_three_signals_present_source_wins(self):
        """Precedência total: source(J4) > execution_mode(J1) > workflow_type."""
        classifier = JourneyClassifier()
        decision = await classifier.classify(
            {
                "context": {"source": "doc-ingestion"},
                "constraints": {"execution_mode": "plan_only"},
            },
            {"workflow_type": "generation"},
        )
        assert decision.journey == Journey.J4_MIGRATE

    async def test_intent_envelope_none_does_not_raise(self):
        """envelope=None com plano ativo → defensivo, roteia pelo workflow_type."""
        classifier = JourneyClassifier()
        decision = await classifier.classify(None, {"workflow_type": "orchestration"})
        assert decision.journey == Journey.J2_ORCHESTRATE

    async def test_workflow_type_as_enum_object_falls_back_unknown(self):
        """workflow_type não-string (enum cru) é tratado defensivamente → UNKNOWN."""
        classifier = JourneyClassifier()

        class _FakeEnum:
            value = "generation"

        decision = await classifier.classify({}, {"workflow_type": _FakeEnum()})
        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"


# --------------------------------------------------------------------------- #
# Fase 2 (Task 3) — Tier 2 (LLM semântico). LLM SEMPRE mockado.
# --------------------------------------------------------------------------- #


def _make_llm_client(text):
    """Cria um cliente LLM fake cujo .generate(...) async devolve um objeto
    com o atributo .text (espelha o contrato de neural_hive_llm.LLMResponse).

    Args:
        text: conteúdo de resposta do LLM (string) OU uma Exception a levantar.
    """
    from unittest.mock import AsyncMock

    class _FakeResponse:
        def __init__(self, t):
            self.text = t

    client = AsyncMock()
    if isinstance(text, Exception):
        client.generate = AsyncMock(side_effect=text)
    else:
        client.generate = AsyncMock(return_value=_FakeResponse(text))
    return client


class TestJourneyClassifierTier2LLM:
    """Tier 2: quando o Tier 1 não dá sinal, recorre ao LLM (mockado)."""

    async def test_llm_resolves_journey_with_method_llm(self):
        """LLM devolve {journey,confidence,reasoning} válido → classification_method='llm'."""
        client = _make_llm_client(
            '{"journey": "J2_ORCHESTRATE", "confidence": 0.91, '
            '"reasoning": "Intenção orquestra serviços existentes."}'
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "coordena os serviços A e B"}}, {})

        assert decision.journey == Journey.J2_ORCHESTRATE
        assert decision.classification_method == "llm"
        assert decision.confidence == 0.91
        assert decision.reasoning
        assert client.generate.await_count == 1

    async def test_llm_invoked_only_when_tier1_has_no_signal(self):
        """Tier 1 com sinal forte NÃO chama o LLM mesmo com client injetado."""
        client = _make_llm_client(
            '{"journey": "J2_ORCHESTRATE", "confidence": 0.9, "reasoning": "x"}'
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({}, {"workflow_type": "GENERATION"})

        assert decision.journey == Journey.J3_BUILD
        assert decision.classification_method == "structured_signal"
        assert client.generate.await_count == 0

    async def test_llm_low_confidence_returns_unknown(self):
        """confidence < threshold → UNKNOWN (anti-verde-falso), nunca força jornada."""
        client = _make_llm_client(
            '{"journey": "J3_BUILD", "confidence": 0.3, "reasoning": "incerto"}'
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "algo ambíguo"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_exception_falls_back_to_no_match(self):
        """LLM falha/timeout/circuit aberto → fallback _no_match (não rebenta)."""
        client = _make_llm_client(RuntimeError("LLM down / circuit open"))
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "qualquer coisa"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_malformed_response_falls_back(self):
        """Resposta não-JSON → parsing defensivo → fallback _no_match."""
        client = _make_llm_client("isto não é json {{{")
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_invalid_journey_value_falls_back(self):
        """journey fora do enum → fallback _no_match (não inventa jornada)."""
        client = _make_llm_client(
            '{"journey": "J9_TELEPORT", "confidence": 0.95, "reasoning": "x"}'
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_missing_confidence_falls_back(self):
        """confidence ausente → fallback _no_match (não assume confiança)."""
        client = _make_llm_client('{"journey": "J3_BUILD", "reasoning": "x"}')
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_json_embedded_in_markdown_fence_is_parsed(self):
        """Parsing tolerante: JSON envolto em ```json ... ``` é extraído."""
        client = _make_llm_client(
            "Aqui está:\n```json\n"
            '{"journey": "J4_MIGRATE", "confidence": 0.8, "reasoning": "migra dados"}\n'
            "```"
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "migrar legado"}}, {})

        assert decision.journey == Journey.J4_MIGRATE
        assert decision.classification_method == "llm"

    async def test_llm_json_with_prefix_and_suffix_is_parsed(self):
        """Texto extra à volta do JSON: regex LAZY extrai só o objeto válido.

        Regressão do achado: regex GREEDY (\\{.*\\}) apanhava do 1º { ao último
        } e produzia JSON malformado → _no_match silencioso.
        """
        client = _make_llm_client(
            "Prefácio explicativo do modelo. "
            '{"journey": "J2_ORCHESTRATE", "confidence": 0.88, "reasoning": "ok"} '
            "E aqui um sufixo qualquer."
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.J2_ORCHESTRATE
        assert decision.classification_method == "llm"
        assert decision.confidence == 0.88

    async def test_llm_empty_response_falls_back(self):
        """Resposta vazia do LLM → _no_match (não tenta parsear)."""
        client = _make_llm_client("")
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_whitespace_only_response_falls_back(self):
        """Resposta só com whitespace → _no_match."""
        client = _make_llm_client("   \n\t  ")
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_boolean_confidence_falls_back(self):
        """confidence booleano (True) é inválido (bool é subclasse de int) → _no_match."""
        client = _make_llm_client('{"journey": "J3_BUILD", "confidence": true, "reasoning": "x"}')
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_out_of_range_confidence_falls_back(self):
        """confidence fora de [0,1] → inválida → _no_match."""
        client = _make_llm_client('{"journey": "J3_BUILD", "confidence": 1.5, "reasoning": "x"}')
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_missing_reasoning_uses_default_and_decides(self):
        """reasoning ausente mas confidence válida → usa default e decide (llm)."""
        client = _make_llm_client('{"journey": "J4_MIGRATE", "confidence": 0.9}')
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "migrar"}}, {})

        assert decision.journey == Journey.J4_MIGRATE
        assert decision.classification_method == "llm"
        assert decision.reasoning  # default preenchido

    async def test_no_llm_client_preserves_phase1_no_match(self):
        """Sem llm_client (Fase 1) → UNKNOWN/no_match (comportamento preservado)."""
        classifier = JourneyClassifier()  # sem client

        decision = await classifier.classify({"intent": {"text": "ambíguo sem sinal"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"

    async def test_llm_unknown_journey_with_high_confidence_stays_unknown(self):
        """LLM pode devolver UNKNOWN explícito → respeitado como no_match."""
        client = _make_llm_client(
            '{"journey": "UNKNOWN", "confidence": 0.95, "reasoning": "não dá para decidir"}'
        )
        classifier = JourneyClassifier(llm_client=client)

        decision = await classifier.classify({"intent": {"text": "x"}}, {})

        assert decision.journey == Journey.UNKNOWN
        assert decision.classification_method == "no_match"
