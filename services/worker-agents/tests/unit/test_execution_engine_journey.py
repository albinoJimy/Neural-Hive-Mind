"""Testes unitários para propagação de journey_id no Worker (Fase 3 / Task 4.4).

O ExecutionEngine deve extrair journey_id do ticket e propagá-lo a
publish_result, para que o evento execution.results carregue journey_id e o
_emit_feedback do orchestrator (já pronto) preencha o ExecutionFeedback.

Elo da cadeia: execution_ticket.journey_id -> execution.results.journey_id.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Mock neural_hive_observability antes de importar o módulo.
mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock()
sys.modules["neural_hive_observability"] = mock_tracer_module

from engine.execution_engine import ExecutionEngine


def test_journey_id_propagated_when_present():
    ticket = {
        "ticket_id": "T-1",
        "plan_id": "PLAN-1",
        "journey_id": "JID-1",
    }
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs.get("journey_id") == "JID-1"


def test_journey_id_omitted_when_absent():
    """Sem journey_id no ticket -> não inventa (não inclui a chave)."""
    ticket = {"ticket_id": "T-2", "plan_id": "PLAN-2"}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert "journey_id" not in kwargs


def test_journey_id_empty_string_omitted():
    """journey_id="" (sem decisão) é tratado como ausente."""
    ticket = {"ticket_id": "T-3", "plan_id": "PLAN-3", "journey_id": ""}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert "journey_id" not in kwargs


def test_journey_id_alongside_other_correlation_fields():
    ticket = {
        "ticket_id": "T-4",
        "plan_id": "PLAN-4",
        "correlation_id": "CORR-4",
        "journey_id": "JID-4",
        "metadata": {"workflow_id": "WF-4"},
    }
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs == {
        "plan_id": "PLAN-4",
        "workflow_id": "WF-4",
        "correlation_id": "CORR-4",
        "journey_id": "JID-4",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
