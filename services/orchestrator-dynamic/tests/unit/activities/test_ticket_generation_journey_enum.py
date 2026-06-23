"""Testes: o ticket gerado carrega o ENUM `journey` (spec journey-router Fase 4).

A Fase 3 já propaga `journey_id` (UUID) no ticket. A Fase 4 propaga também o ENUM
`journey` (ex "J3_BUILD"), de `plan_data.get("journey")` (ou cognitive_plan), para
fechar a cadeia ticket -> worker -> execution.results e dar valor real à métrica
`record_execution_result_processed(journey=...)` no orchestrator.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.activities.ticket_generation import (
    generate_execution_tickets,
    set_activity_dependencies,
)


@pytest.fixture()
def mock_activity_info():
    with patch("src.activities.ticket_generation.activity") as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = "wf-journey"
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


def _plan(**extra):
    plan = {
        "plan_id": "plan-j",
        "intent_id": "intent-j",
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "EXECUTE",
                "description": "t",
                "dependencies": [],
                "estimated_duration_ms": 60000,
                "parameters": {},
                "required_capabilities": ["python"],
            }
        ],
        "execution_order": ["task-1"],
        "risk_band": "low",
    }
    plan.update(extra)
    return plan


@pytest.mark.asyncio()
async def test_ticket_carries_journey_enum(mock_activity_info):
    set_activity_dependencies(kafka_producer=None, mongodb_client=None)
    tickets = await generate_execution_tickets(_plan(journey="J3_BUILD"), None)
    assert tickets[0]["journey"] == "J3_BUILD"


@pytest.mark.asyncio()
async def test_ticket_journey_none_when_absent(mock_activity_info):
    set_activity_dependencies(kafka_producer=None, mongodb_client=None)
    tickets = await generate_execution_tickets(_plan(), None)
    assert tickets[0]["journey"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
