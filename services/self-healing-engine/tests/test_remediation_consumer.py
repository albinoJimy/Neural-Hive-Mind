import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))
import pytest

from src.consumers.remediation_consumer import RemediationConsumer


class FakeExecutor:
    async def execute_playbook(self, playbook_name: str, context: dict, **kwargs):
        return {"success": True, "actions": []}


class FakeKafkaConsumer:
    def __init__(self, *args, **kwargs):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def commit(self):
        return True

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_remediation_consumer_start_and_stop(monkeypatch):
    monkeypatch.setattr("src.consumers.remediation_consumer.AIOKafkaConsumer", lambda *args, **kwargs: FakeKafkaConsumer())

    consumer = RemediationConsumer(
        bootstrap_servers="kafka:9092",
        group_id="test-group",
        topic="remediation-actions",
        playbook_executor=FakeExecutor()
    )

    await consumer.start()
    await consumer.stop()

    assert consumer._running is False
