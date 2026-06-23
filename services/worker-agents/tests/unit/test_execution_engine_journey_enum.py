"""Testes: propagação do ENUM `journey` (J1-J4) no Worker (spec journey-router Fase 4).

A Fase 3 já propaga `journey_id` (UUID). A Fase 4 propaga também o ENUM `journey`
(ex "J3_BUILD") pela MESMA cadeia ticket -> worker -> execution.results, para que a
métrica `record_execution_result_processed(journey=...)` no orchestrator tenha valor
real (e não caia sempre em "unknown").

Elo: execution_ticket.journey -> execution.results.journey.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock()
sys.modules["neural_hive_observability"] = mock_tracer_module

from engine.execution_engine import ExecutionEngine


def test_journey_enum_propagated_when_present():
    ticket = {
        "ticket_id": "T-1",
        "plan_id": "PLAN-1",
        "journey_id": "JID-1",
        "journey": "J3_BUILD",
    }
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs.get("journey") == "J3_BUILD"
    # journey_id continua a propagar (Fase 3 não regride).
    assert kwargs.get("journey_id") == "JID-1"


def test_journey_enum_omitted_when_absent():
    """Sem journey no ticket -> não inventa (não inclui a chave)."""
    ticket = {"ticket_id": "T-2", "plan_id": "PLAN-2"}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert "journey" not in kwargs


def test_journey_enum_empty_string_omitted():
    """journey="" (sem decisão) tratado como ausente."""
    ticket = {"ticket_id": "T-3", "plan_id": "PLAN-3", "journey": ""}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert "journey" not in kwargs


def test_journey_enum_alongside_all_correlation_fields():
    ticket = {
        "ticket_id": "T-4",
        "plan_id": "PLAN-4",
        "correlation_id": "CORR-4",
        "journey_id": "JID-4",
        "journey": "J4_MIGRATE",
        "metadata": {"workflow_id": "WF-4"},
    }
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs == {
        "plan_id": "PLAN-4",
        "workflow_id": "WF-4",
        "correlation_id": "CORR-4",
        "journey_id": "JID-4",
        "journey": "J4_MIGRATE",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
