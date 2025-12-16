import random
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER_SRC = ROOT / "services" / "worker-agents" / "src"

# Stub do CodeForgeClient para evitar dependência externa em ambiente de teste
if "neural_hive_integration" not in sys.modules:
    integration_pkg = ModuleType("neural_hive_integration")
    clients_pkg = ModuleType("neural_hive_integration.clients")

    class CodeForgeClient:  # type: ignore
        async def trigger_pipeline(self, *_args, **_kwargs):
            return "pipeline-1"

        async def wait_for_pipeline_completion(self, *_args, **_kwargs):
            return SimpleNamespace(status="completed", duration_ms=10, artifacts={}, sbom={}, signature={})

    clients_pkg.code_forge_client = ModuleType("neural_hive_integration.clients.code_forge_client")
    clients_pkg.code_forge_client.CodeForgeClient = CodeForgeClient
    sys.modules["neural_hive_integration"] = integration_pkg
    sys.modules["neural_hive_integration.clients"] = clients_pkg
    sys.modules["neural_hive_integration.clients.code_forge_client"] = clients_pkg.code_forge_client

if str(WORKER_SRC) not in sys.path:
    sys.path.append(str(WORKER_SRC))

from src.executors.build_executor import BuildExecutor  # noqa: E402


def _build_ticket():
    return {
        "ticket_id": "t-build",
        "task_id": "task-build",
        "task_type": "BUILD",
        "parameters": {"artifact_id": "a-1"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_build_executor(monkeypatch):
    # Reduz tempo de simulação para manter teste estável
    monkeypatch.setattr(random, "uniform", lambda *_: 0.01)

    executor = BuildExecutor(config=SimpleNamespace())
    result = await executor.execute(_build_ticket())

    assert result["success"] is True
    assert "artifact_url" in result["output"]
    assert result["metadata"]["simulated"] is True
