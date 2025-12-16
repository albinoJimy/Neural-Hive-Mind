import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

sys.path.append(str(ROOT / "src"))  # noqa: E402

from executors.build_executor import BuildExecutor  # noqa: E402
from executors.deploy_executor import DeployExecutor  # noqa: E402
from executors.test_executor import TestExecutor  # noqa: E402
from executors.validate_executor import ValidateExecutor  # noqa: E402
from neural_hive_integration.clients.code_forge_client import PipelineStatus  # noqa: E402


@pytest.fixture
def config_with_all_integrations():
    return SimpleNamespace(
        allowed_test_commands=["pytest", "npm test", "go test", "mvn test", "jest", "cargo test"],
        test_execution_timeout_seconds=600,
        trivy_enabled=True,
        trivy_timeout_seconds=5,
        opa_enabled=True,
        opa_url="http://opa.test",
        argocd_enabled=True,
        argocd_url="https://argocd.example.com",
        argocd_token="token-123",
    )


@pytest.fixture
def config_with_fallbacks():
    return SimpleNamespace(
        allowed_test_commands=["pytest"],
        test_execution_timeout_seconds=1,
        trivy_enabled=False,
        trivy_timeout_seconds=1,
        opa_enabled=False,
        opa_url=None,
        argocd_enabled=False,
        argocd_url=None,
        argocd_token=None,
    )


# ---------------------- BuildExecutor ---------------------- #
@pytest.mark.asyncio
async def test_build_with_code_forge_integration():
    class StubCF:
        async def trigger_pipeline(self, artifact_id):
            return f"pipe-{artifact_id}"

        async def wait_for_pipeline_completion(self, pipeline_id, poll_interval=1, timeout=10):
            return PipelineStatus(
                pipeline_id=pipeline_id,
                status="completed",
                stage="done",
                duration_ms=500,
                artifacts=[{"id": "artifact-1"}],
                sbom={"components": []},
                signature="sig",
            )

    executor = BuildExecutor(SimpleNamespace())
    executor.code_forge_client = StubCF()

    ticket = {"ticket_id": "b-int-1", "task_id": "task", "task_type": "BUILD", "parameters": {"artifact_id": "a1"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["pipeline_id"] == "pipe-a1"


@pytest.mark.asyncio
async def test_build_fallback_on_code_forge_error():
    class ErrorCF:
        async def trigger_pipeline(self, artifact_id):
            raise RuntimeError("boom")

    executor = BuildExecutor(SimpleNamespace())
    executor.code_forge_client = ErrorCF()

    ticket = {"ticket_id": "b-int-2", "task_id": "task", "task_type": "BUILD", "parameters": {"artifact_id": "a2"}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
    assert result["output"]["artifact_url"].startswith("stub://")


@pytest.mark.asyncio
async def test_build_fallback_on_code_forge_timeout():
    class TimeoutCF:
        async def trigger_pipeline(self, artifact_id):
            return "pipeline-timeout"

        async def wait_for_pipeline_completion(self, pipeline_id, poll_interval=1, timeout=10):
            raise TimeoutError("timeout")

    executor = BuildExecutor(SimpleNamespace())
    executor.code_forge_client = TimeoutCF()

    ticket = {"ticket_id": "b-int-3", "task_id": "task", "task_type": "BUILD", "parameters": {"artifact_id": "a3"}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
    assert result["success"] is True


# ---------------------- DeployExecutor ---------------------- #
class _StubResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class _StubAsyncClient:
    def __init__(self, post_response=None, get_responses=None, raise_on_post=None):
        self.post_response = post_response or _StubResponse()
        self.get_responses = get_responses or []
        self.raise_on_post = raise_on_post
        self.get_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def post(self, url, json=None, headers=None):
        if self.raise_on_post:
            raise self.raise_on_post
        return self.post_response

    async def get(self, url, headers=None):
        if not self.get_responses:
            return _StubResponse({"status": {"health": {"status": "Healthy"}}})
        resp = self.get_responses[min(self.get_calls, len(self.get_responses) - 1)]
        self.get_calls += 1
        return resp


@pytest.mark.asyncio
async def test_deploy_with_argocd_integration(monkeypatch, config_with_all_integrations):
    healthy_resp = _StubResponse({"status": {"health": {"status": "Healthy"}}})
    monkeypatch.setattr("executors.deploy_executor.httpx.AsyncClient", lambda timeout=30: _StubAsyncClient(post_response=_StubResponse(), get_responses=[healthy_resp]))

    async def no_sleep(_):
        return None

    monkeypatch.setattr("executors.deploy_executor.asyncio.sleep", no_sleep)

    executor = DeployExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "d-int-1", "task_id": "task", "task_type": "DEPLOY", "parameters": {"deployment_name": "app"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_deploy_with_argocd_polling(monkeypatch, config_with_all_integrations):
    responses = [
        _StubResponse({"status": {"health": {"status": "Progressing"}}}),
        _StubResponse({"status": {"health": {"status": "Healthy"}}}),
    ]
    monkeypatch.setattr("executors.deploy_executor.httpx.AsyncClient", lambda timeout=30: _StubAsyncClient(post_response=_StubResponse(), get_responses=responses))

    async def no_sleep(_):
        return None

    monkeypatch.setattr("executors.deploy_executor.asyncio.sleep", no_sleep)

    executor = DeployExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "d-int-2", "task_id": "task", "task_type": "DEPLOY", "parameters": {"deployment_name": "app"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_deploy_fallback_on_argocd_disabled(config_with_fallbacks):
    executor = DeployExecutor(config_with_fallbacks)
    ticket = {"ticket_id": "d-int-3", "task_id": "task", "task_type": "DEPLOY", "parameters": {}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
    assert result["success"] is True


@pytest.mark.asyncio
async def test_deploy_fallback_on_argocd_error(monkeypatch, config_with_all_integrations):
    monkeypatch.setattr(
        "executors.deploy_executor.httpx.AsyncClient",
        lambda timeout=30: _StubAsyncClient(raise_on_post=RuntimeError("post failed"))
    )

    executor = DeployExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "d-int-4", "task_id": "task", "task_type": "DEPLOY", "parameters": {}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True


# ---------------------- ValidateExecutor ---------------------- #
@pytest.mark.asyncio
async def test_validate_with_opa_policy(monkeypatch, config_with_all_integrations):
    payload = {"result": {"allow": True, "violations": []}}
    monkeypatch.setattr(
        "executors.validate_executor.httpx.AsyncClient",
        lambda timeout=30: _StubAsyncClient(post_response=_StubResponse(payload))
    )

    executor = ValidateExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "v-int-1", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "policy"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["violations"] == []


@pytest.mark.asyncio
async def test_validate_with_opa_violations(monkeypatch, config_with_all_integrations):
    payload = {"result": {"allow": False, "violations": ["deny"]}}
    monkeypatch.setattr(
        "executors.validate_executor.httpx.AsyncClient",
        lambda timeout=30: _StubAsyncClient(post_response=_StubResponse(payload))
    )

    executor = ValidateExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "v-int-2", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "policy"}}
    result = await executor.execute(ticket)

    assert result["success"] is False
    assert result["metadata"]["simulated"] is False
    assert result["output"]["violations"] == ["deny"]


@pytest.mark.asyncio
async def test_validate_with_trivy_sast(monkeypatch, tmp_path, config_with_all_integrations):
    report = {"Results": [{"Vulnerabilities": []}]}

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")

    monkeypatch.setattr("executors.validate_executor.subprocess.run", fake_run)

    executor = ValidateExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "v-int-3", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "sast", "working_dir": str(tmp_path)}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["validation_type"] == "sast"


@pytest.mark.asyncio
async def test_validate_fallback_on_opa_disabled(config_with_fallbacks):
    executor = ValidateExecutor(config_with_fallbacks)
    ticket = {"ticket_id": "v-int-4", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "policy"}}
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
    assert result["success"] is True


@pytest.mark.asyncio
async def test_validate_fallback_on_trivy_timeout(monkeypatch, config_with_all_integrations):
    def raise_timeout(*_, **__):
        raise subprocess.TimeoutExpired(cmd="trivy fs", timeout=3)

    monkeypatch.setattr("executors.validate_executor.subprocess.run", raise_timeout)

    executor = ValidateExecutor(config_with_all_integrations)
    ticket = {"ticket_id": "v-int-5", "task_id": "task", "task_type": "VALIDATE", "parameters": {"validation_type": "sast"}}
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is True
    assert result["output"]["validation_type"] == "sast"


# ---------------------- TestExecutor ---------------------- #
@pytest.mark.asyncio
async def test_execute_with_allowed_command(monkeypatch, tmp_path, config_with_all_integrations):
    report = {"tests_passed": 3, "tests_failed": 0, "coverage": 0.9}
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None):
        return SimpleNamespace(returncode=0, stdout=report_path.read_text(), stderr="")

    monkeypatch.setattr("executors.test_executor.subprocess.run", fake_run)

    executor = TestExecutor(config_with_all_integrations)
    ticket = {
        "ticket_id": "t-int-1",
        "task_id": "task",
        "task_type": "TEST",
        "parameters": {"test_command": "pytest", "working_dir": str(tmp_path), "report_path": "report.json"},
    }
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["tests_passed"] == 3


@pytest.mark.asyncio
async def test_execute_with_disallowed_command(monkeypatch, config_with_all_integrations):
    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None):
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("executors.test_executor.subprocess.run", fake_run)

    executor = TestExecutor(config_with_all_integrations)
    ticket = {
        "ticket_id": "t-int-2",
        "task_id": "task",
        "task_type": "TEST",
        "parameters": {"test_command": "rm -rf /", "working_dir": ".", "report_path": "report.json"},
    }
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
    assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_with_report_parsing(monkeypatch, tmp_path, config_with_all_integrations):
    report = {"passed": 2, "failed": 1, "coverage_percent": 75}
    (tmp_path / "report.json").write_text(json.dumps(report))

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None):
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("executors.test_executor.subprocess.run", fake_run)

    executor = TestExecutor(config_with_all_integrations)
    ticket = {
        "ticket_id": "t-int-3",
        "task_id": "task",
        "task_type": "TEST",
        "parameters": {"test_command": "pytest", "working_dir": str(tmp_path), "report_path": "report.json"},
    }
    result = await executor.execute(ticket)

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["tests_failed"] == 1
    assert result["output"]["coverage"] == 75


@pytest.mark.asyncio
async def test_execute_fallback_on_command_error(monkeypatch, config_with_all_integrations):
    def raise_error(cmd, cwd=None, capture_output=True, text=True, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("executors.test_executor.subprocess.run", raise_error)

    executor = TestExecutor(config_with_all_integrations)
    ticket = {
        "ticket_id": "t-int-4",
        "task_id": "task",
        "task_type": "TEST",
        "parameters": {"test_command": "pytest", "working_dir": ".", "report_path": "report.json"},
    }
    result = await executor.execute(ticket)

    assert result["metadata"]["simulated"] is True
    assert result["success"] is True


# ---------------------- Helm Rendering Expectations ---------------------- #
def test_configmap_renders_all_variables():
    content = Path("helm-charts/worker-agents/templates/configmap.yaml").read_text()
    expected_keys = [
        "CODE_FORGE_URL",
        "CODE_FORGE_ENABLED",
        "CODE_FORGE_TIMEOUT_SECONDS",
        "ARGOCD_ENABLED",
        "OPA_URL",
        "OPA_ENABLED",
        "TRIVY_ENABLED",
        "TRIVY_TIMEOUT_SECONDS",
        "TEST_EXECUTION_TIMEOUT_SECONDS",
        "ALLOWED_TEST_COMMANDS",
    ]
    for key in expected_keys:
        assert key in content


def _helm_available():
    from shutil import which
    return which("helm") is not None


def _render_configmap_with_argocd_url(url: str) -> str:
    cmd = [
        "helm",
        "template",
        "worker-agents",
        "helm-charts/worker-agents",
        "--show-only",
        "templates/configmap.yaml",
        f"--set=config.argocd.url={url}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout


@pytest.mark.skipif(not _helm_available(), reason="helm binary not available")
def test_configmap_omits_argocd_url_when_empty():
    rendered = _render_configmap_with_argocd_url("")
    assert "ARGOCD_URL:" not in rendered


@pytest.mark.skipif(not _helm_available(), reason="helm binary not available")
def test_configmap_includes_argocd_url_when_set():
    rendered = _render_configmap_with_argocd_url("https://argo.example.com")
    assert 'ARGOCD_URL: "https://argo.example.com"' in rendered


def test_secret_renders_argocd_token():
    content = Path("helm-charts/worker-agents/templates/secret.yaml").read_text()
    assert "ARGOCD_TOKEN" in content


def test_deployment_mounts_configmap_and_secret():
    content = Path("helm-charts/worker-agents/templates/deployment.yaml").read_text()
    assert "configMapRef" in content
    assert "secretRef" in content
