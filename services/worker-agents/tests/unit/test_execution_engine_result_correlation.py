"""Testes unitários para FIX-4 (I4): propagação de plan_id/workflow_id/correlation_id.

O ExecutionEngine deve extrair estes campos do ticket e propagá-los a
publish_result, para que o ExecutionResultConsumer do orchestrator não dependa
sempre do lookup Redis (workflow:by:ticket:*).
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


def test_extracts_all_fields_top_level_and_metadata():
    ticket = {
        "ticket_id": "T-1",
        "plan_id": "PLAN-1",
        "correlation_id": "CORR-1",
        "metadata": {"workflow_id": "WF-1"},
    }
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs == {
        "plan_id": "PLAN-1",
        "workflow_id": "WF-1",
        "correlation_id": "CORR-1",
    }


def test_workflow_id_top_level_takes_precedence():
    ticket = {
        "ticket_id": "T-2",
        "plan_id": "PLAN-2",
        "workflow_id": "WF-TOP",
        "metadata": {"workflow_id": "WF-META"},
    }
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs["workflow_id"] == "WF-TOP"


def test_omits_missing_fields():
    ticket = {"ticket_id": "T-3", "plan_id": "PLAN-3"}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    # Não inventa workflow_id/correlation_id quando ausentes.
    assert kwargs == {"plan_id": "PLAN-3"}


def test_empty_ticket_returns_empty_kwargs():
    kwargs = ExecutionEngine._result_correlation_kwargs({})
    assert kwargs == {}


def test_correlation_id_camelcase_fallback():
    ticket = {"ticket_id": "T-4", "correlationId": "CORR-CAMEL"}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs.get("correlation_id") == "CORR-CAMEL"


def test_none_metadata_is_safe():
    ticket = {"ticket_id": "T-5", "plan_id": "PLAN-5", "metadata": None}
    kwargs = ExecutionEngine._result_correlation_kwargs(ticket)
    assert kwargs == {"plan_id": "PLAN-5"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
