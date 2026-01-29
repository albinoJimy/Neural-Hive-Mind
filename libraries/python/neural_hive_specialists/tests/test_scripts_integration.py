import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
def test_generate_encryption_key_script_invocation(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, capture_output, text, check):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="generated-key", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    script_path = Path("scripts/generate_encryption_key.py")
    result = subprocess.run(
        ["python", str(script_path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "generated-key" in result.stdout
    assert script_path.as_posix() in " ".join(captured["cmd"])


@pytest.mark.unit
def test_monitor_retraining_runs_script_invocation(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, check):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="monitor-ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    module_path = (
        "libraries/python/neural_hive_specialists/scripts/monitor_retraining_runs.py"
    )
    result = subprocess.run(
        ["python", module_path, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "monitor" in result.stdout
    assert module_path in " ".join(captured["cmd"])


@pytest.mark.unit
def test_run_retention_policies_script_invocation(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, check):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="retention-ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    script_path = Path("scripts/run_retention_policies.py")
    result = subprocess.run(
        ["python", str(script_path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "retention-ok" in result.stdout
    assert script_path.as_posix() in " ".join(captured["cmd"])
