import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CODE_FORGE_SRC = ROOT / "services" / "code-forge" / "src"
if str(CODE_FORGE_SRC) not in sys.path:
    sys.path.append(str(CODE_FORGE_SRC))

from src.models.execution_ticket import ExecutionTicket, Priority, QoS, RiskBand, SLA, TaskType, TicketStatus, DeliveryMode, Consistency, Durability, SecurityLevel  # noqa: E402
from src.services.pipeline_engine import PipelineEngine  # noqa: E402


class _StageStub:
    def __init__(self, name: str):
        self.name = name

    async def __call__(self, context):
        context.metadata[self.name] = "ok"


class _KafkaStub:
    async def publish_result(self, *_, **__):
        return True


class _TicketClientStub:
    async def update_status(self, ticket_id, status, metadata=None):
        self.last_status = status
        self.last_metadata = metadata


class _DbStub:
    async def upsert_pipeline_result(self, *_, **__):
        return True


def _build_ticket():
    return ExecutionTicket(
        ticket_id="t-1",
        plan_id="p-1",
        intent_id="i-1",
        decision_id="d-1",
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters={"artifact_id": "a-1"},
        sla=SLA(deadline=datetime.utcnow() + timedelta(minutes=5), timeout_ms=1000, max_retries=1),
        qos=QoS(delivery_mode=DeliveryMode.AT_LEAST_ONCE, consistency=Consistency.EVENTUAL, durability=Durability.PERSISTENT),
        security_level=SecurityLevel.INTERNAL,
        created_at=datetime.utcnow(),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_code_forge_pipeline(monkeypatch):
    pipeline = PipelineEngine(
        template_selector=_StageStub("template_selection"),
        code_composer=_StageStub("code_composition"),
        validator=_StageStub("validation"),
        test_runner=_StageStub("testing"),
        packager=_StageStub("packaging"),
        approval_gate=_StageStub("approval_gate"),
        kafka_producer=_KafkaStub(),
        ticket_client=_TicketClientStub(),
        postgres_client=_DbStub(),
        mongodb_client=_DbStub(),
        max_concurrent=1,
        pipeline_timeout=5,
    )

    ticket = _build_ticket()
    result = await pipeline.execute_pipeline(ticket)

    assert result.status in ("completed", "COMPLETED")
    assert result.artifacts is not None
