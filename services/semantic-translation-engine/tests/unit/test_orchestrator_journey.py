"""Testes unitários para a integração do JourneyClassifier no STE orchestrator.

Fase 3 / Task 4.2 — o orchestrator (process_intent), depois do
workflow_classifier + DAG, instancia/usa o JourneyClassifier e faz
``await journey_classifier.classify(intent_envelope, cognitive_plan_dict)``,
gravando os 5 campos journey no cognitive_plan.

Os testes accionam o ``process_intent`` real com dependências mockadas e um
``journey_classifier`` injetado (DI), capturam o CognitivePlan persistido no
ledger (mongodb.append_to_ledger) e validam os campos journey.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models.cognitive_plan import RiskBand, TaskNode, WorkflowType
from src.services.orchestrator import SemanticTranslationOrchestrator

from neural_hive_domain import Journey, JourneyDecision


@contextmanager
def _noop_span(*args, **kwargs):
    """Span context-manager no-op (tracer não inicializado em testes unitários)."""
    span = MagicMock()
    yield span


@pytest.fixture(autouse=True)
def _mock_tracer():
    """Mocka get_tracer() do orchestrator (sem OTEL configurado nos unit tests)."""
    tracer = MagicMock()
    tracer.start_as_current_span = _noop_span
    with patch("src.services.orchestrator.get_tracer", return_value=tracer):
        yield


@pytest.fixture()
def captured_plans():
    """Lista mutável onde o append_to_ledger mockado guarda o plano."""
    return []


@pytest.fixture()
def orchestrator(captured_plans):
    """Orchestrator com dependências mockadas e classificadores injetados.

    - workflow_classifier devolve GENERATION (sinal forte → Tier 1 J3_BUILD).
    - dag_generator/risk_scorer/explainability devolvem outputs mínimos válidos.
    - mongodb.append_to_ledger captura o CognitivePlan construído.
    - journey_classifier é um AsyncMock com classify() configurável por teste.
    """
    parser = MagicMock()
    parser.parse = AsyncMock(
        return_value={"intent": {"text": "gerar código"}, "historical_context": {}}
    )

    dag_generator = MagicMock()
    dag_generator.generate = MagicMock(
        return_value=(
            [TaskNode(task_id="t1", task_type="generate", description="gerar")],
            ["t1"],
        )
    )

    risk_scorer = MagicMock()
    risk_scorer.score_multi_domain = MagicMock(
        return_value=(0.2, RiskBand.LOW, {}, {}, {"is_destructive": False})
    )

    explainability = MagicMock()
    explainability.generate = MagicMock(return_value=("tok-1", "resumo"))

    mongodb = MagicMock()

    async def _append(plan):
        captured_plans.append(plan)
        return "hash-1"

    mongodb.append_to_ledger = AsyncMock(side_effect=_append)

    neo4j = MagicMock()
    neo4j.persist_intent_to_graph = AsyncMock(return_value=True)

    plan_producer = MagicMock()
    plan_producer.send_plan = AsyncMock()

    approval_producer = MagicMock()
    approval_producer.send_approval_request = AsyncMock()

    metrics = MagicMock()

    workflow_classifier = MagicMock()
    workflow_classifier.classify = MagicMock(
        return_value=(
            WorkflowType.GENERATION,
            {"score": 0.9, "confidence": 0.9, "reason": "kw"},
        )
    )

    journey_classifier = MagicMock()
    journey_classifier.classify = AsyncMock(
        return_value=JourneyDecision(
            journey=Journey.J3_BUILD,
            journey_id="jid-fixture",
            confidence=0.95,
            reasoning="Tier 1 (sinal estruturado): workflow_type == generation",
            classification_method="structured_signal",
        )
    )

    orch = SemanticTranslationOrchestrator(
        semantic_parser=parser,
        dag_generator=dag_generator,
        risk_scorer=risk_scorer,
        explainability_generator=explainability,
        mongodb_client=mongodb,
        neo4j_client=neo4j,
        plan_producer=plan_producer,
        approval_producer=approval_producer,
        metrics=metrics,
        workflow_classifier=workflow_classifier,
        journey_classifier=journey_classifier,
    )
    return orch


@pytest.fixture()
def intent_envelope():
    return {
        "id": "intent-001",
        "confidence": 0.9,
        "intent": {"text": "gerar código", "domain": "technical"},
        "constraints": {"priority": "normal"},
        "context": {},
    }


class TestOrchestratorJourneyDI:
    """O orchestrator aceita um journey_classifier injetado."""

    def test_accepts_journey_classifier_in_constructor(self, orchestrator):
        assert orchestrator.journey_classifier is not None

    def test_default_journey_classifier_when_not_injected(self):
        """Sem injeção, usa o singleton get_journey_classifier (como workflow)."""
        orch = SemanticTranslationOrchestrator(
            semantic_parser=MagicMock(),
            dag_generator=MagicMock(),
            risk_scorer=MagicMock(),
            explainability_generator=MagicMock(),
            mongodb_client=MagicMock(),
            neo4j_client=MagicMock(),
            plan_producer=MagicMock(),
            approval_producer=MagicMock(),
            metrics=MagicMock(),
        )
        assert orch.journey_classifier is not None
        # Contrato: expõe classify (async).
        assert hasattr(orch.journey_classifier, "classify")


class TestOrchestratorJourneyPropagation:
    """process_intent chama o classifier e grava os 5 campos journey no plano."""

    @pytest.mark.asyncio
    async def test_journey_classifier_invoked(self, orchestrator, intent_envelope, captured_plans):
        await orchestrator.process_intent(intent_envelope, {})
        orchestrator.journey_classifier.classify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_journey_fields_written_to_plan(
        self, orchestrator, intent_envelope, captured_plans
    ):
        await orchestrator.process_intent(intent_envelope, {})
        assert len(captured_plans) == 1
        plan = captured_plans[0]
        assert plan.journey == "J3_BUILD"
        assert plan.journey_id == "jid-fixture"
        assert plan.journey_confidence == 0.95
        assert plan.journey_classification_method == "structured_signal"
        assert "workflow_type" in plan.journey_reasoning or plan.journey_reasoning

    @pytest.mark.asyncio
    async def test_classify_receives_plan_dict_with_workflow_type(
        self, orchestrator, intent_envelope, captured_plans
    ):
        """O classifier recebe um dict do plano com workflow_type (sinal Tier 1)."""
        await orchestrator.process_intent(intent_envelope, {})
        call = orchestrator.journey_classifier.classify.await_args
        # classify(intent_envelope, cognitive_plan_dict)
        passed_envelope, passed_plan = call.args[0], call.args[1]
        assert passed_envelope is intent_envelope
        assert isinstance(passed_plan, dict)
        assert passed_plan.get("workflow_type") == "generation"

    @pytest.mark.asyncio
    async def test_journey_failure_does_not_block_pipeline(
        self, orchestrator, intent_envelope, captured_plans
    ):
        """Falha do classifier não bloqueia o pipeline: plano gravado com UNKNOWN."""
        orchestrator.journey_classifier.classify = AsyncMock(
            side_effect=RuntimeError("classifier explodiu")
        )
        await orchestrator.process_intent(intent_envelope, {})
        assert len(captured_plans) == 1
        plan = captured_plans[0]
        # Degrada para defaults (UNKNOWN) — anti-verde-falso, não bloqueia.
        assert plan.journey == "UNKNOWN"
        assert plan.journey_classification_method in ("", "no_match")
