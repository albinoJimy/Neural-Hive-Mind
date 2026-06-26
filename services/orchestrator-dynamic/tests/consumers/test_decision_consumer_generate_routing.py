"""Testes do routing via capacidade GENERATE no Decision Consumer (Task 3 / Fase 2).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 3.

A fronteira deixa de estar vazada: o consumer decide "requer geração" pela
SEMÂNTICA da jornada (J3_BUILD) — não por conhecer a classe do workflow — e
delega na ``GenerateCapability`` (que arranca o FluxoGWorkflow durável), em vez
de chamar ``start_workflow`` diretamente. Preservado:

    - J2_ORCHESTRATE / J4_MIGRATE -> OrchestrationWorkflow (caminho legado);
    - J1_PLAN_ONLY                -> sem execução;
    - sem journey + workflow_type=generation -> geração (fallback compat);
    - sem journey (default)       -> OrchestrationWorkflow (fallback compat).

Anti-verde-falso: ``UnsupportedStackError`` na capacidade não crasha o consumer;
faz commit do offset e retorna (erro permanente, sem retry infinito).
"""

from unittest.mock import AsyncMock, Mock

import pytest
from src.capabilities.generate import GenerateTarget, UnsupportedStackError
from src.capabilities.generate.capability import GenerateHandle
from src.consumers.decision_consumer import (
    DecisionConsumer,
    _extract_generate_target,
    _journey_requires_generation,
    _requires_generate_capability,
)
from src.workflows.orchestration_workflow import OrchestrationWorkflow

# =============================================================================
# Helpers module-level (isolados)
# =============================================================================


class TestJourneyRequiresGeneration:
    """A decisão deriva da semântica da jornada (hoje só J3_BUILD)."""

    def test_j3_build_requires_generation(self):
        assert _journey_requires_generation("J3_BUILD") is True

    def test_other_journeys_do_not_require_generation(self):
        for journey in ("J1_PLAN_ONLY", "J2_ORCHESTRATE", "J4_MIGRATE", "UNKNOWN", ""):
            assert _journey_requires_generation(journey) is False


class TestRequiresGenerateCapability:
    """Autoridade única partilhada por consumer e resume (não devem divergir)."""

    def test_j3_build_by_journey(self):
        # journey J3_BUILD requer geração independentemente do workflow_type.
        assert _requires_generate_capability("J3_BUILD", "orchestration") is True

    def test_unknown_journey_generation_workflow_type_fallback(self):
        # Sem journey (UNKNOWN) + workflow_type=generation → fallback legado.
        assert _requires_generate_capability("UNKNOWN", "generation") is True

    def test_unknown_journey_orchestration_is_not_generation(self):
        assert _requires_generate_capability("UNKNOWN", "orchestration") is False

    def test_orchestration_journeys_are_not_generation(self):
        for journey in ("J2_ORCHESTRATE", "J4_MIGRATE"):
            # Mesmo com workflow_type=generation, a jornada de orquestração manda.
            assert _requires_generate_capability(journey, "generation") is False


class TestExtractGenerateTarget:
    """Deriva a stack-alvo do plano (default provado python/fastapi)."""

    def test_empty_plan_defaults_to_python_fastapi(self):
        target = _extract_generate_target({})
        assert isinstance(target, GenerateTarget)
        assert target.language == "python"
        assert target.framework == "fastapi"

    def test_explicit_parameters_are_respected(self):
        plan = {"parameters": {"language": "go", "framework": "gin"}}
        target = _extract_generate_target(plan)
        assert target.language == "go"
        assert target.framework == "gin"

    def test_explicit_unsupported_stack_is_returned_verbatim(self):
        """A resolução (suportada ou não) é da capacidade, não do extractor."""
        plan = {"parameters": {"language": "rust", "framework": "actix"}}
        target = _extract_generate_target(plan)
        assert target.language == "rust"
        assert target.framework == "actix"


# =============================================================================
# Harness do handler _process_message (caminho direct-plan; bypassa Mongo)
# =============================================================================


def _make_consumer() -> DecisionConsumer:
    config = Mock()
    config.temporal_workflow_id_prefix = "workflow-"
    config.temporal_task_queue = "q"
    config.ml_drift_check_enabled = False

    consumer = DecisionConsumer(config, AsyncMock(), AsyncMock(), AsyncMock())
    consumer.consumer = AsyncMock()
    consumer._check_ml_drift = AsyncMock(return_value=None)
    consumer._is_duplicate_decision = AsyncMock(return_value=False)
    consumer._mark_decision_processed = AsyncMock()
    return consumer


def _make_message(journey: str | None = None, workflow_type: str | None = None):
    plan: dict = {
        "plan_id": "p1",
        "tasks": [{"task_id": "t1"}],
        "execution_order": ["t1"],
        "risk_band": "low",
    }
    if journey is not None:
        plan["journey"] = journey
    if workflow_type is not None:
        plan["workflow_type"] = workflow_type
    return Mock(headers=[], value=plan, topic="t", partition=0, offset=1)


@pytest.mark.asyncio()
async def test_j3_build_invokes_generate_capability():
    """J3_BUILD -> capability.start awaited 1x; start_workflow NÃO chamado."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()
    consumer.generate_capability.start = AsyncMock(
        return_value=GenerateHandle(workflow_id="workflow-p1", journey="J3_BUILD")
    )

    await consumer._process_message(_make_message(journey="J3_BUILD"))

    consumer.generate_capability.start.assert_awaited_once()
    request = consumer.generate_capability.start.call_args.args[0]
    assert request.journey == "J3_BUILD"
    assert request.target.language == "python"
    assert request.target.framework == "fastapi"
    consumer.temporal_client.start_workflow.assert_not_called()
    consumer.consumer.commit.assert_awaited()


@pytest.mark.asyncio()
async def test_j2_orchestrate_uses_orchestration_workflow():
    """J2_ORCHESTRATE -> capability NÃO chamada; start_workflow OrchestrationWorkflow.run."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()

    await consumer._process_message(_make_message(journey="J2_ORCHESTRATE"))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    assert consumer.temporal_client.start_workflow.call_args.args[0] == OrchestrationWorkflow.run


@pytest.mark.asyncio()
async def test_j4_migrate_uses_orchestration_workflow():
    """J4_MIGRATE -> orquestração (cutover é sub-fluxo da orquestração)."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()

    await consumer._process_message(_make_message(journey="J4_MIGRATE"))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    assert consumer.temporal_client.start_workflow.call_args.args[0] == OrchestrationWorkflow.run


@pytest.mark.asyncio()
async def test_j1_plan_only_executes_nothing():
    """J1_PLAN_ONLY -> nem capability nem start_workflow; commit feito."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()

    await consumer._process_message(_make_message(journey="J1_PLAN_ONLY"))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_not_called()
    consumer.consumer.commit.assert_awaited()


@pytest.mark.asyncio()
async def test_no_journey_generation_workflow_type_falls_back_to_generation():
    """sem journey + workflow_type=generation -> capability.start (fallback compat)."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()
    consumer.generate_capability.start = AsyncMock(
        return_value=GenerateHandle(workflow_id="workflow-p1", journey="UNKNOWN")
    )

    await consumer._process_message(_make_message(workflow_type="generation"))

    consumer.generate_capability.start.assert_awaited_once()
    consumer.temporal_client.start_workflow.assert_not_called()


@pytest.mark.asyncio()
async def test_no_journey_defaults_to_orchestration():
    """sem journey (default orchestration) -> start_workflow OrchestrationWorkflow.run."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()

    await consumer._process_message(_make_message())

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    assert consumer.temporal_client.start_workflow.call_args.args[0] == OrchestrationWorkflow.run


@pytest.mark.asyncio()
async def test_unsupported_stack_does_not_crash_commits_and_returns():
    """J3_BUILD com UnsupportedStackError -> sem crash, commit, return (anti-verde-falso)."""
    consumer = _make_consumer()
    consumer.generate_capability = AsyncMock()
    consumer.generate_capability.start = AsyncMock(
        side_effect=UnsupportedStackError("stack não suportada")
    )

    # Não deve propagar exceção
    await consumer._process_message(_make_message(journey="J3_BUILD"))

    consumer.generate_capability.start.assert_awaited_once()
    consumer.temporal_client.start_workflow.assert_not_called()
    consumer.consumer.commit.assert_awaited()
