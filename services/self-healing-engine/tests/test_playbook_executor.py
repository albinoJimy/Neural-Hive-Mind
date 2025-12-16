import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))
import asyncio
import yaml
import pytest

from src.services.playbook_executor import PlaybookExecutor


@pytest.mark.asyncio
async def test_execute_playbook_runs_actions(tmp_path):
    playbook_path = tmp_path / "sample.yaml"
    playbook_content = {
        "playbook_name": "sample",
        "actions": [
            {"type": "update_policy", "parameters": {"policy_name": "p1", "enabled": True}},
            {"type": "notify_agent", "parameters": {"agent_id": "worker-1", "notification_type": "INFO", "message": "ok"}}
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
    result = await executor.execute_playbook("sample", context={})

    assert result["success"] is True
    assert result["total_actions"] == 2


@pytest.mark.asyncio
async def test_execute_playbook_timeout(tmp_path):
    playbook_path = tmp_path / "slow.yaml"
    playbook_content = {"playbook_name": "slow", "actions": [{"type": "update_policy"}]}
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)

    async def slow_actions(actions, context, on_action_completed=None):
        await asyncio.sleep(0.05)
        return {"success": True, "actions": []}

    executor._execute_actions = slow_actions  # type: ignore

    result = await executor.execute_playbook("slow", context={}, timeout_seconds=0.01)

    assert result["success"] is False
    assert result.get("status") == "TIMEOUT"
