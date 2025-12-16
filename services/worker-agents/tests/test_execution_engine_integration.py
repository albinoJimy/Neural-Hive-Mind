import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from engine.execution_engine import ExecutionEngine, TaskExecutionError  # noqa: E402


class StubTicketClient:
    def __init__(self):
        self.status_calls = []

    async def update_ticket_status(self, ticket_id, status, error_message=None, actual_duration_ms=None):
        self.status_calls.append(
            {
                "ticket_id": ticket_id,
                "status": status,
                "error_message": error_message,
                "actual_duration_ms": actual_duration_ms,
            }
        )

    async def get_ticket_token(self, ticket_id):
        return f"token-{ticket_id}"


class StubResultProducer:
    def __init__(self):
        self.published = []

    async def publish_result(self, ticket_id, status, result, error_message=None, actual_duration_ms=None):
        self.published.append(
            {
                "ticket_id": ticket_id,
                "status": status,
                "result": result,
                "error_message": error_message,
                "actual_duration_ms": actual_duration_ms,
            }
        )


class StubDependencyCoordinator:
    def __init__(self):
        self.called = False

    async def wait_for_dependencies(self, ticket):
        self.called = True


class StubExecutorSuccess:
    def __init__(self):
        self.calls = 0

    async def execute(self, ticket):
        self.calls += 1
        return {"success": True, "output": {"ok": True}, "metadata": {}, "logs": []}

    def get_task_type(self):
        return "TEST"  # pragma: no cover - not used directly


class StubExecutorRetry:
    def __init__(self, fail_times=1):
        self.calls = 0
        self.fail_times = fail_times

    async def execute(self, ticket):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient failure")
        return {"success": True, "output": {"ok": True}, "metadata": {}, "logs": []}

    def get_task_type(self):
        return "TEST"  # pragma: no cover - not used directly


class StubExecutorTimeout:
    async def execute(self, ticket):
        await asyncio.sleep(2)

    def get_task_type(self):
        return "TEST"  # pragma: no cover - not used directly


class RegistryWrapper:
    def __init__(self, executor):
        self.executor = executor

    def get_executor(self, task_type: str):
        return self.executor


@pytest.fixture
def config():
    return SimpleNamespace(
        max_concurrent_tasks=5,
        max_retries_per_ticket=2,
        retry_backoff_base_seconds=0,
        retry_backoff_max_seconds=0,
        task_timeout_multiplier=1.0,
    )


@pytest.fixture
def sample_ticket():
    return {
        "ticket_id": "ticket-123",
        "task_id": "task-1",
        "task_type": "TEST",
        "status": "PENDING",
        "dependencies": [],
        "sla": {"timeout_ms": 500, "max_retries": 1},
    }


@pytest.mark.asyncio
async def test_execute_ticket_success(config, sample_ticket):
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorSuccess()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(config, ticket_client, result_producer, dependency_coordinator, registry)
    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket["ticket_id"]], timeout=2)

    assert ticket_client.status_calls[0]["status"] == "RUNNING"
    assert ticket_client.status_calls[-1]["status"] == "COMPLETED"
    assert result_producer.published[-1]["status"] == "COMPLETED"
    assert dependency_coordinator.called


@pytest.mark.asyncio
async def test_execute_ticket_with_retry(config, sample_ticket):
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorRetry(fail_times=1)
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(config, ticket_client, result_producer, dependency_coordinator, registry)
    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket["ticket_id"]], timeout=3)

    assert executor.calls == 2
    assert ticket_client.status_calls[-1]["status"] == "COMPLETED"
    assert result_producer.published[-1]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_execute_ticket_timeout(config, sample_ticket):
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorTimeout()
    registry = RegistryWrapper(executor)

    # reduce retries and timeout for test speed
    sample_ticket["sla"]["timeout_ms"] = 100
    config.max_retries_per_ticket = 0

    engine = ExecutionEngine(config, ticket_client, result_producer, dependency_coordinator, registry)
    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket["ticket_id"]], timeout=3)

    assert ticket_client.status_calls[-1]["status"] == "FAILED"
    assert result_producer.published[-1]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_execute_ticket_executor_error_marks_failed(config, sample_ticket):
    class BadRegistry:
        def get_executor(self, task_type: str):
            raise TaskExecutionError("Executor not available")

    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    registry = BadRegistry()

    engine = ExecutionEngine(config, ticket_client, result_producer, dependency_coordinator, registry)
    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket["ticket_id"]], timeout=2)

    assert ticket_client.status_calls[-1]["status"] == "FAILED"
    assert result_producer.published[-1]["status"] == "FAILED"
