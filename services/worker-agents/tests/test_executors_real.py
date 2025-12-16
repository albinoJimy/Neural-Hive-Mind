import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

sys.path.append(str(ROOT / "src"))  # noqa: E402

from executors.execute_executor import ExecuteExecutor  # noqa: E402
from executors.build_executor import BuildExecutor  # noqa: E402
from executors.test_executor import TestExecutor  # noqa: E402
from executors.validate_executor import ValidateExecutor  # noqa: E402
from executors.deploy_executor import DeployExecutor  # noqa: E402
from neural_hive_integration.clients.code_forge_client import (  # noqa: E402
    GenerationStatus,
    PipelineStatus,
)


class DummyMetric:
    def __init__(self):
        self.calls = []

    def labels(self, **kwargs):
        self.calls.append(('labels', kwargs))
        return self

    def inc(self, value=1):
        self.calls.append(('inc', value))
        return self

    def observe(self, value):
        self.calls.append(('observe', value))
        return self


@pytest.fixture
def base_config():
    return SimpleNamespace(
        allowed_test_commands=["pytest", "npm", "npm test", "go", "go test", "mvn", "mvn test"],
        test_execution_timeout_seconds=5,
        trivy_enabled=False,
        trivy_timeout_seconds=5,
        opa_enabled=True,
        opa_url="http://opa.test",
        argocd_enabled=False,
        argocd_url=None,
        argocd_token=None,
    )


@pytest.mark.asyncio
async def test_execute_executor_with_code_forge(monkeypatch, base_config):
    statuses = [
        GenerationStatus(request_id="req-1", status="pending", artifacts=[], pipeline_id=None, error=None),
        GenerationStatus(request_id="req-1", status="completed", artifacts=[{"name": "file.py"}], pipeline_id="pipe-1", error=None),
    ]

    class StubCF:
        def __init__(self):
            self.status_calls = 0

        async def submit_generation_request(self, ticket_id, template_id, parameters):
            return "req-1"

        async def get_generation_status(self, request_id):
            self.status_calls += 1
            return statuses[min(self.status_calls - 1, len(statuses) - 1)]

    executor = ExecuteExecutor(base_config, code_forge_client=StubCF())
    ticket = {"ticket_id": "t1", "task_id": "task", "task_type": "EXECUTE", "parameters": {"template_id": "tpl"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_execute_executor_fallback_without_cf(base_config):
    executor = ExecuteExecutor(base_config, code_forge_client=None)
    ticket = {"ticket_id": "t1", "task_id": "task", "task_type": "EXECUTE", "parameters": {}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True


@pytest.mark.asyncio
async def test_build_executor_with_code_forge(base_config):
    class StubCF:
        async def trigger_pipeline(self, artifact_id):
            return "pipeline-1"

        async def wait_for_pipeline_completion(self, pipeline_id, poll_interval=1, timeout=10):
            return PipelineStatus(
                pipeline_id=pipeline_id,
                status="completed",
                stage="done",
                duration_ms=1000,
                artifacts=[{"id": "artifact"}],
                sbom={"components": []},
                signature="sig",
            )

    executor = BuildExecutor(base_config, code_forge_client=StubCF())
    ticket = {"ticket_id": "b1", "task_id": "task", "task_type": "BUILD", "parameters": {"artifact_id": "artifact-1"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["pipeline_id"] == "pipeline-1"


@pytest.mark.asyncio
async def test_build_executor_timeout_fallback(base_config):
    class StubCF:
        async def trigger_pipeline(self, artifact_id):
            return "pipeline-1"

        async def wait_for_pipeline_completion(self, pipeline_id, poll_interval=1, timeout=10):
            raise TimeoutError("timeout")

    executor = BuildExecutor(base_config, code_forge_client=StubCF())
    ticket = {"ticket_id": "b2", "task_id": "task", "task_type": "BUILD", "parameters": {"artifact_id": "artifact-1"}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True


@pytest.mark.asyncio
async def test_test_executor_runs_subprocess(monkeypatch, tmp_path, base_config):
    report = {"tests_passed": 5, "tests_failed": 1, "coverage": 0.8}
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None):
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("executors.test_executor.subprocess.run", fake_run)

    executor = TestExecutor(base_config)
    ticket = {
        "ticket_id": "test-1",
        "task_id": "task",
        "task_type": "TEST",
        "parameters": {"test_command": "pytest", "working_dir": str(tmp_path), "report_path": "report.json"},
    }
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["output"]["tests_passed"] == 5
    assert result["output"]["coverage"] == 0.8


@pytest.mark.asyncio
async def test_validate_executor_with_opa(monkeypatch, base_config):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("http error")

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, payload):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

        async def post(self, url, json=None):
            return FakeResponse(self.payload)

    class FakeAsyncClientFactory:
        def __init__(self, payload):
            self.payload = payload

        def __call__(self, *args, **kwargs):
            return FakeClient(self.payload)

    monkeypatch.setattr(
        "executors.validate_executor.httpx.AsyncClient",
        FakeAsyncClientFactory({"result": {"allow": True, "violations": []}})
    )

    executor = ValidateExecutor(base_config)
    ticket = {"ticket_id": "v1", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "policy"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False


@pytest.mark.asyncio
async def test_validate_executor_metrics_success(monkeypatch, base_config):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("http error")

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, payload):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

        async def post(self, url, json=None):
            return FakeResponse(self.payload)

    class FakeAsyncClientFactory:
        def __init__(self, payload):
            self.payload = payload

        def __call__(self, *args, **kwargs):
            return FakeClient(self.payload)

    metrics = SimpleNamespace(
        validate_tasks_executed_total=DummyMetric(),
        validate_tools_executed_total=DummyMetric()
    )

    monkeypatch.setattr(
        "executors.validate_executor.httpx.AsyncClient",
        FakeAsyncClientFactory({"result": {"allow": True, "violations": []}})
    )

    executor = ValidateExecutor(base_config, metrics=metrics)
    ticket = {"ticket_id": "v1", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "policy"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert any(call for call in metrics.validate_tasks_executed_total.calls if call[0] == "labels" and call[1]["status"] == "success")


@pytest.mark.asyncio
async def test_validate_executor_metrics_error(monkeypatch, base_config):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

        async def post(self, url, json=None):
            raise RuntimeError("boom")

    class FakeAsyncClientFactory:
        def __call__(self, *args, **kwargs):
            return FakeClient()

    tasks_metric = DummyMetric()
    metrics = SimpleNamespace(
        validate_tasks_executed_total=tasks_metric,
        validate_tools_executed_total=DummyMetric()
    )

    monkeypatch.setattr(
        "executors.validate_executor.httpx.AsyncClient",
        FakeAsyncClientFactory()
    )

    executor = ValidateExecutor(base_config, metrics=metrics)
    ticket = {"ticket_id": "v2", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "policy"}}
    await executor.execute(ticket)

    error_labels = [call for call in tasks_metric.calls if call[0] == "labels" and call[1]["status"] == "error"]
    assert len(error_labels) == 1


@pytest.mark.asyncio
async def test_deploy_executor_fallback(base_config):
    executor = DeployExecutor(base_config)
    ticket = {"ticket_id": "d1", "task_id": "task", "task_type": "DEPLOY", "parameters": {}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
