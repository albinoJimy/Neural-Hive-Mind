"""Tests do contrato canónico na emissão de tickets (Fase 2 j3-build-generate).

O produtor (generate_execution_tickets) passava `task_type`/`priority` em bruto do
plano cognitivo (decompostos pelo STE), emitindo legado: task_type minúsculo
(ex.: 'transform') e priority inteiro (ex.: 5). Isto fazia o code-forge rejeitar
(DLQ). O produtor passa a emitir o contrato CANÓNICO: task_type MAIÚSCULAS e
priority enum string {LOW,NORMAL,HIGH,CRITICAL}.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.activities.ticket_generation import generate_execution_tickets


@pytest.fixture()
def mock_activity_info():
    with patch("src.activities.ticket_generation.activity") as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = "wf-canon-123"
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


def _plan(task_type, plan_priority):
    return {
        "plan_id": "plan-canon-001",
        "intent_id": "intent-canon-001",
        "priority": plan_priority,
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": task_type,
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


class TestCanonicalTaskTypeEmission:
    @pytest.mark.asyncio
    async def test_lowercase_task_type_emitted_uppercase(self, mock_activity_info):
        tickets = await generate_execution_tickets(_plan("transform", "NORMAL"))
        assert tickets[0]["task_type"] == "TRANSFORM"

    @pytest.mark.asyncio
    async def test_canonical_task_type_passthrough(self, mock_activity_info):
        tickets = await generate_execution_tickets(_plan("BUILD", "NORMAL"))
        assert tickets[0]["task_type"] == "BUILD"


class TestCanonicalPriorityEmission:
    @pytest.mark.asyncio
    async def test_int_priority_emitted_as_enum_string(self, mock_activity_info):
        tickets = await generate_execution_tickets(_plan("EXECUTE", 5))
        assert tickets[0]["priority"] == "NORMAL"

    @pytest.mark.asyncio
    async def test_high_int_priority_emitted_critical(self, mock_activity_info):
        tickets = await generate_execution_tickets(_plan("EXECUTE", 9))
        assert tickets[0]["priority"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_lowercase_priority_string_emitted_uppercase(self, mock_activity_info):
        tickets = await generate_execution_tickets(_plan("EXECUTE", "high"))
        assert tickets[0]["priority"] == "HIGH"


class TestMixedLegacyEmission:
    @pytest.mark.asyncio
    async def test_lowercase_task_type_and_int_priority_both_canonical(self, mock_activity_info):
        """Caso real do DLQ: o produtor já não emite o que o code-forge rejeitava."""
        tickets = await generate_execution_tickets(_plan("query", 5))
        assert tickets[0]["task_type"] == "QUERY"
        assert tickets[0]["priority"] == "NORMAL"
