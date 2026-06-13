"""Testes unitários para os fixes REPLAY-SAFE do OrchestrationWorkflow.

Cobre:
- FIX-1: uso de tracer/spans REPLAY-SAFE (nunca crashar com tracer/span None).
- FIX-2: self._workflow_id inicializado no __init__ e atribuído em run().

Os helpers module-level (_safe_set_baggage / _safe_span_event) são testados
isoladamente porque encapsulam a lógica de proteção contra None que causava o
AttributeError 'NoneType' object has no attribute 'start_as_current_span'.
"""

from unittest.mock import MagicMock

import pytest
from src.workflows.orchestration_workflow import (
    OrchestrationWorkflow,
    _safe_set_baggage,
    _safe_span_event,
)


class TestWorkflowIdInitialization:
    """FIX-2: self._workflow_id deve existir após __init__."""

    def test_workflow_id_initialized_to_none(self):
        workflow = OrchestrationWorkflow()
        # Antes do fix, este atributo não existia e o signal handler
        # ticket_completed crashava com AttributeError engolido pelo try/except.
        assert hasattr(workflow, "_workflow_id")
        assert workflow._workflow_id is None


class TestSafeSpanEvent:
    """FIX-1: _safe_span_event nunca crasha quando span é None."""

    def test_none_span_is_noop(self):
        # Não deve lançar quando span é None (tracer None no REPLAY/QUERY).
        _safe_span_event(None, "evento")
        _safe_span_event(None, "evento", {"count": 3})

    def test_emits_event_without_attributes(self):
        span = MagicMock()
        _safe_span_event(span, "evento")
        span.add_event.assert_called_once_with("evento")

    def test_emits_event_with_attributes(self):
        span = MagicMock()
        _safe_span_event(span, "evento", {"count": 5})
        span.add_event.assert_called_once_with("evento", {"count": 5})

    def test_swallows_span_exceptions(self):
        span = MagicMock()
        span.add_event.side_effect = RuntimeError("tracing inactivo")
        # Não deve propagar — proteção REPLAY-SAFE.
        _safe_span_event(span, "evento")


class TestSafeSetBaggage:
    """FIX-1: _safe_set_baggage é REPLAY-SAFE e ignora valores None."""

    def test_none_value_is_noop(self, monkeypatch):
        called = {"n": 0}

        def _fake_set_baggage(_key, _value):
            called["n"] += 1

        monkeypatch.setattr("src.workflows.orchestration_workflow.set_baggage", _fake_set_baggage)
        _safe_set_baggage("plan_id", None)
        assert called["n"] == 0

    def test_sets_baggage_for_real_value(self, monkeypatch):
        captured = {}

        def _fake_set_baggage(key, value):
            captured[key] = value

        monkeypatch.setattr("src.workflows.orchestration_workflow.set_baggage", _fake_set_baggage)
        _safe_set_baggage("plan_id", "PLAN-001")
        assert captured == {"plan_id": "PLAN-001"}

    def test_swallows_set_baggage_exceptions(self, monkeypatch):
        def _boom(_key, _value):
            raise RuntimeError("sandbox sem tracing")

        monkeypatch.setattr("src.workflows.orchestration_workflow.set_baggage", _boom)
        # Não deve propagar.
        _safe_set_baggage("plan_id", "PLAN-001")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
