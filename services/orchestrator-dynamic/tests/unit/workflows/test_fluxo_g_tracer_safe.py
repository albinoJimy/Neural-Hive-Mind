"""Testes REPLAY-SAFE do tracer no FluxoGWorkflow — Fase 3 j3-build-generate.

Bug bloqueador observado em cluster: get_tracer() devolve None durante
REPLAY/QUERY no sandbox Temporal, e `with tracer.start_as_current_span(...)`
crashava com AttributeError ('NoneType' object has no attribute
'start_as_current_span'), falhando o FluxoGWorkflow ANTES do G1 — nenhum
code_artifact era gerado. Espelha o fix já aplicado ao OrchestrationWorkflow.
"""

from unittest.mock import MagicMock

from src.workflows.fluxo_g_workflow import _safe_span_event


def test_safe_span_event_none_span_noop():
    """span None (tracer None no sandbox) -> não rebenta."""
    # Não deve levantar exceção.
    _safe_span_event(None, "evento")


def test_safe_span_event_calls_add_event_when_span_present():
    span = MagicMock()
    _safe_span_event(span, "evento")
    span.add_event.assert_called_once_with("evento")


def test_safe_span_event_swallows_span_errors():
    """Erros do span são engolidos (best-effort, nunca quebram o workflow)."""
    span = MagicMock()
    span.add_event.side_effect = RuntimeError("boom")
    # Não deve propagar.
    _safe_span_event(span, "evento")
