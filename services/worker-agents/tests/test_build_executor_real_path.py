"""Testes do caminho real do BuildExecutor (Task 4 — Code Forge build verificável).

Contrato: o output do BUILD tem de incluir `artifact` (= {registry}/{nome}:{version})
e `digest` (= sha256:...) para satisfazer o gate de evidência da Task 1
(`ExecutionEngine._evidence_build`). NUNCA deve cair em `stub://` nem marcar
`simulated=True` com `success=True`.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from executors.build_executor import BuildExecutor

from neural_hive_integration.clients.code_forge_client import PipelineStatus

# Import do gate de evidência da Task 1 para validação ponta-a-ponta do contrato.
ENGINE_SRC = ROOT / "src"
sys.path.append(str(ENGINE_SRC))
from engine.execution_engine import ExecutionEngine


def _ticket(ticket_id: str = "b-real-1") -> dict:
    return {
        "ticket_id": ticket_id,
        "task_id": "task",
        "task_type": "BUILD",
        "parameters": {"artifact_id": "svc", "version": "1.0.0"},
    }


class _RealCF:
    """Code Forge client mockado que devolve um pipeline completo com digest+uri."""

    def __init__(self):
        self.triggered = False

    async def trigger_pipeline(self, artifact_id):
        self.triggered = True
        return "pipe-real-1"

    async def wait_for_pipeline_completion(self, pipeline_id, poll_interval=30, timeout=14400):
        return PipelineStatus(
            pipeline_id=pipeline_id,
            status="completed",
            stage="PACKAGING",
            duration_ms=4200,
            artifacts=[
                {
                    "type": "image",
                    "digest": "sha256:abc123def456",
                    "uri": "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0",
                    "registry": "ghcr.io/albinojimy/neural-hive-mind",
                    "image": "svc",
                    "tag": "1.0.0",
                }
            ],
        )


@pytest.mark.asyncio()
async def test_build_real_path_extracts_artifact_and_digest():
    """Caminho real: output expõe artifact (ref completa) + digest reais."""
    executor = BuildExecutor(SimpleNamespace())
    executor.code_forge_client = _RealCF()

    result = await executor.execute(_ticket())

    assert result["success"] is True
    assert result["metadata"]["simulated"] is False
    assert result["output"]["artifact"] == "ghcr.io/albinojimy/neural-hive-mind/svc:1.0.0"
    assert result["output"]["digest"] == "sha256:abc123def456"
    # Nunca stub
    assert result["output"].get("artifact_url") != "stub://artifact"


@pytest.mark.asyncio()
async def test_build_real_path_satisfies_evidence_gate():
    """O output do caminho real satisfaz o gate de evidência da Task 1."""
    executor = BuildExecutor(SimpleNamespace())
    executor.code_forge_client = _RealCF()

    result = await executor.execute(_ticket())

    ok, reason = ExecutionEngine._evidence_build(result["output"])
    assert ok is True, f"gate de evidência rejeitou output real: {reason}"
    assert reason is None


@pytest.mark.asyncio()
async def test_build_no_forge_fails_fast_no_stub():
    """Sem code-forge (client=None) → FAILED, sem stub, sem simulação."""
    metrics = SimpleNamespace(
        real_path_unavailable_total=_CounterSpy(),
    )
    executor = BuildExecutor(SimpleNamespace(), metrics=metrics)
    executor.code_forge_client = None

    result = await executor.execute(_ticket("b-real-nf"))

    assert result["success"] is False
    assert result["output"].get("artifact_url") != "stub://artifact"
    assert result["metadata"].get("simulated") is not True
    assert metrics.real_path_unavailable_total.incremented >= 1


@pytest.mark.asyncio()
async def test_build_forge_failure_fails_fast_no_stub():
    """Forge a falhar (exceção após retries) → FAILED, sem stub."""

    class _ErrorCF:
        async def trigger_pipeline(self, artifact_id):
            raise RuntimeError("boom")

    metrics = SimpleNamespace(real_path_unavailable_total=_CounterSpy())
    config = SimpleNamespace(code_forge_retry_attempts=1, retry_backoff_base_seconds=0)
    executor = BuildExecutor(config, metrics=metrics)
    executor.code_forge_client = _ErrorCF()

    result = await executor.execute(_ticket("b-real-fail"))

    assert result["success"] is False
    assert result["output"].get("artifact_url") != "stub://artifact"
    assert result["metadata"].get("simulated") is not True


@pytest.mark.asyncio()
async def test_build_never_returns_silent_simulation():
    """Nenhum caminho devolve stub:// nem simulated=True com success=True."""
    # Caminho real
    executor = BuildExecutor(SimpleNamespace())
    executor.code_forge_client = _RealCF()
    result = await executor.execute(_ticket("b-real-ns"))
    assert not (result["metadata"].get("simulated") and result["success"])

    # Sem forge
    executor2 = BuildExecutor(SimpleNamespace())
    executor2.code_forge_client = None
    result2 = await executor2.execute(_ticket("b-real-ns2"))
    assert result2["output"].get("artifact_url") != "stub://artifact"
    assert not (result2["metadata"].get("simulated") and result2["success"])


class _CounterSpy:
    """Counter Prometheus-like minimalista para asserts."""

    def __init__(self):
        self.incremented = 0
        self._last_labels = None

    def labels(self, *args, **kwargs):
        self._last_labels = (args, kwargs)
        return self

    def inc(self, amount: int = 1):
        self.incremented += amount
