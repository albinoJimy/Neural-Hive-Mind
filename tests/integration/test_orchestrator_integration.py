import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
ORCH_SRC = ROOT / "services" / "orchestrator-dynamic" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.append(str(ORCH_SRC))

# Stub mínimo de temporalio.activity para ambientes sem Temporal instalado
try:
    import temporalio.activity  # type: ignore
except ImportError:  # pragma: no cover
    temporalio = SimpleNamespace()
    temporalio.activity = SimpleNamespace(logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))
    sys.modules["temporalio"] = temporalio
    sys.modules["temporalio.activity"] = temporalio.activity

from src.activities.ticket_generation import generate_execution_tickets  # noqa: E402


def create_sample_cognitive_plan():
    return {
        "plan_id": "plan-123",
        "intent_id": "intent-456",
        "tasks": [
            {"task_id": "t1", "task_type": "ANALYZE", "estimated_duration_ms": 1000},
            {"task_id": "t2", "task_type": "EXECUTE", "estimated_duration_ms": 1000, "dependencies": ["t1"]},
        ],
        "execution_order": ["t1", "t2"],
        "priority": "NORMAL",
        "risk_band": "medium",
        "security_level": "INTERNAL",
    }


def create_consolidated_decision():
    return {
        "decision_id": "dec-001",
        "correlation_id": "corr-001",
        "trace_id": "trace-001",
        "span_id": "span-001",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_end_to_end(monkeypatch):
    # Simula contexto do Temporal Activity
    monkeypatch.setattr(
        "temporalio.activity.info",
        lambda: SimpleNamespace(workflow_id="wf-test"),
    )

    cognitive_plan = create_sample_cognitive_plan()
    decision = create_consolidated_decision()

    tickets = await generate_execution_tickets(cognitive_plan, decision)

    assert len(tickets) == 2
    assert all(ticket["status"] == "PENDING" for ticket in tickets)
    assert tickets[1]["dependencies"]  # segunda task depende da primeira
