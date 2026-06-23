"""Tests para propagação de journey_id na geração de tickets (Fase 3 / Task 4.4).

Cadeia de propagação: cognitive_plan.journey_id -> execution_ticket.journey_id.
O worker copia journey_id do ticket para o payload execution.results, e o
_emit_feedback (já pronto) lê result_data.get("journey_id") para preencher o
ExecutionFeedback. Aqui validamos o primeiro elo: plano -> ticket.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.activities.ticket_generation import generate_execution_tickets


@pytest.fixture()
def mock_activity_info():
    with patch("src.activities.ticket_generation.activity") as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = "wf-journey-123"
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


def _plan(journey_id: str | None):
    plan = {
        "plan_id": "plan-j-001",
        "intent_id": "intent-j-001",
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "EXECUTE",
                "description": "task",
                "dependencies": [],
                "estimated_duration_ms": 60000,
                "parameters": {},
                "required_capabilities": [],
            }
        ],
        "execution_order": ["task-1"],
        "risk_band": "low",
    }
    if journey_id is not None:
        plan["journey_id"] = journey_id
        plan["journey"] = "J3_BUILD"
    return plan


class TestJourneyIdPropagationToTicket:
    @pytest.mark.asyncio
    async def test_ticket_carries_journey_id(self, mock_activity_info):
        """journey_id do plano é copiado para cada ticket gerado."""
        tickets = await generate_execution_tickets(_plan("jid-xyz"))
        assert len(tickets) == 1
        assert tickets[0]["journey_id"] == "jid-xyz"

    @pytest.mark.asyncio
    async def test_ticket_journey_id_absent_is_none(self, mock_activity_info):
        """Plano antigo sem journey_id -> ticket.journey_id None (não inventa)."""
        tickets = await generate_execution_tickets(_plan(None))
        assert tickets[0].get("journey_id") is None

    @pytest.mark.asyncio
    async def test_ticket_journey_id_empty_string_is_none(self, mock_activity_info):
        """journey_id="" (default do modelo, sem decisão) normaliza para None."""
        plan = _plan("")
        tickets = await generate_execution_tickets(plan)
        assert tickets[0].get("journey_id") is None
