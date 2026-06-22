"""
Testes do fix da race de duplicação de tickets (camada 1).

Diagnóstico (2026-06-22): o polling _get_tickets_from_workflow desistia em ~1.24s
(o wait_fixed(2) do AsyncRetrying não era respeitado), antes de o workflow Temporal
gerar os tickets (~5s). O fallback _extract_tickets_from_plan disparava sempre e
criava um 2º lote → 16 tickets (2x8).

Fix: polling robusto com espera real (asyncio.sleep) entre tentativas + tratar
erros transitórios da query (workflow recém-iniciado, 404/5xx) como retryable.
Assim o polling espera o workflow gerar e usa esses tickets — o fallback só dispara
quando o workflow genuinamente falha.

Ficheiro novo — não toca test_flow_c_orchestrator.py (contrato).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neural_hive_integration.clients.orchestrator_client import (
    WorkflowTicketsNotReadyError,
)
from neural_hive_integration.orchestration.flow_c_orchestrator import FlowCOrchestrator


@pytest.fixture()
def orch():
    o = FlowCOrchestrator()
    o._validate_ticket_schema = MagicMock(return_value=(True, []))
    o._extract_tickets_from_plan = AsyncMock(return_value=[{"ticket_id": "fallback"}])
    return o


def _ctx():
    return MagicMock(plan_id="p1")


class TestPollingWaitsForWorkflow:
    @pytest.mark.asyncio()
    async def test_waits_between_attempts_and_uses_workflow_tickets(self, orch):
        # workflow vazio nas primeiras tentativas, depois devolve tickets
        results = [[], [], [], [{"ticket_id": "t1", "task_id": "task_0"}]]
        orch.orchestrator_client.query_workflow = AsyncMock(side_effect=results)

        sleeps = []

        async def fake_sleep(s):
            sleeps.append(s)

        with patch(
            "neural_hive_integration.orchestration.flow_c_orchestrator.asyncio.sleep",
            fake_sleep,
        ):
            tickets = await orch._get_tickets_from_workflow("wf1", {"tasks": []}, _ctx())

        assert len(tickets) == 1
        assert tickets[0]["ticket_id"] == "t1"
        # NÃO caiu no fallback — usou os tickets do workflow
        orch._extract_tickets_from_plan.assert_not_called()
        # esperou (real) entre tentativas, com wait >= 2s — cobre os ~5s do workflow
        assert len(sleeps) >= 3
        assert all(s >= 2 for s in sleeps)

    @pytest.mark.asyncio()
    async def test_transient_query_error_is_retried_not_immediate_fallback(self, orch):
        # workflow recém-iniciado: query falha (transitório) antes de ficar pronto
        boom = RuntimeError("workflow not queryable yet (404)")
        results = [boom, boom, [{"ticket_id": "t1", "task_id": "task_0"}]]
        orch.orchestrator_client.query_workflow = AsyncMock(side_effect=results)

        async def fake_sleep(_s):
            pass

        with patch(
            "neural_hive_integration.orchestration.flow_c_orchestrator.asyncio.sleep",
            fake_sleep,
        ):
            tickets = await orch._get_tickets_from_workflow("wf1", {"tasks": []}, _ctx())

        assert len(tickets) == 1
        orch._extract_tickets_from_plan.assert_not_called()

    @pytest.mark.asyncio()
    async def test_not_ready_error_is_retried(self, orch):
        results = [
            WorkflowTicketsNotReadyError(workflow_id="wf1"),
            [{"ticket_id": "t1", "task_id": "task_0"}],
        ]
        orch.orchestrator_client.query_workflow = AsyncMock(side_effect=results)

        async def fake_sleep(_s):
            pass

        with patch(
            "neural_hive_integration.orchestration.flow_c_orchestrator.asyncio.sleep",
            fake_sleep,
        ):
            tickets = await orch._get_tickets_from_workflow("wf1", {"tasks": []}, _ctx())

        assert len(tickets) == 1
        orch._extract_tickets_from_plan.assert_not_called()

    @pytest.mark.asyncio()
    async def test_falls_back_only_after_exhausting_attempts(self, orch):
        orch._workflow_poll_max_attempts = 3
        # workflow nunca gera tickets
        orch.orchestrator_client.query_workflow = AsyncMock(return_value=[])

        async def fake_sleep(_s):
            pass

        with patch(
            "neural_hive_integration.orchestration.flow_c_orchestrator.asyncio.sleep",
            fake_sleep,
        ):
            tickets = await orch._get_tickets_from_workflow("wf1", {"tasks": []}, _ctx())

        # esgotou → fallback (comportamento legítimo quando o workflow falha)
        assert tickets == [{"ticket_id": "fallback"}]
        orch._extract_tickets_from_plan.assert_called_once()
        # tentou o nº configurado de vezes antes de desistir
        assert orch.orchestrator_client.query_workflow.await_count == 3
