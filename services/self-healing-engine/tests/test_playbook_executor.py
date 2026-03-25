import asyncio
import yaml
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.services.playbook_executor import PlaybookExecutor


@pytest.mark.asyncio
async def test_execute_playbook_runs_actions(tmp_path, mock_tracer):
    playbook_path = tmp_path / "sample.yaml"
    playbook_content = {
        "playbook_name": "sample",
        "actions": [
            {"type": "update_policy", "parameters": {"policy_name": "p1", "enabled": True}},
            {"type": "notify_agent", "parameters": {"agent_id": "worker-1", "notification_type": "INFO", "message": "ok"}}
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("sample", context={})

    assert result["success"] is True
    assert result["total_actions"] == 2


@pytest.mark.asyncio
async def test_execute_playbook_timeout(tmp_path, mock_tracer):
    playbook_path = tmp_path / "slow.yaml"
    playbook_content = {"playbook_name": "slow", "actions": [{"type": "update_policy"}]}
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)

        async def slow_actions(actions, context, on_action_completed=None):
            await asyncio.sleep(0.05)
            return {"success": True, "actions": []}

        executor._execute_actions = slow_actions  # type: ignore

        result = await executor.execute_playbook("slow", context={}, timeout_seconds=0.01)

    assert result["success"] is False
    assert result.get("status") == "TIMEOUT"


@pytest.mark.asyncio
async def test_wait_action(tmp_path, mock_tracer):
    """Test the wait action."""
    playbook_path = tmp_path / "wait_test.yaml"
    playbook_content = {
        "playbook_name": "wait_test",
        "actions": [
            {"type": "wait", "parameters": {"seconds": 0.1}}
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("wait_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_apply_policy_action(tmp_path, mock_tracer):
    """Test the apply_policy action (alias for update_policy)."""
    playbook_path = tmp_path / "apply_policy_test.yaml"
    playbook_content = {
        "playbook_name": "apply_policy_test",
        "actions": [
            {"type": "apply_policy", "parameters": {"policy_name": "test-policy", "enabled": True}}
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("apply_policy_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_delete_pod_action(tmp_path, mock_tracer):
    """Test the delete_pod action."""
    playbook_path = tmp_path / "delete_pod_test.yaml"
    playbook_content = {
        "playbook_name": "delete_pod_test",
        "actions": [
            {"type": "delete_pod", "parameters": {"pod_name": "test-pod", "namespace": "default"}}
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("delete_pod_test", context={})

    # Sem Kubernetes configurado, a ação retorna erro, mas execução completa
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_patch_deployment_action(tmp_path, mock_tracer):
    """Test the patch_deployment action."""
    playbook_path = tmp_path / "patch_deployment_test.yaml"
    playbook_content = {
        "playbook_name": "patch_deployment_test",
        "actions": [
            {
                "type": "patch_deployment",
                "parameters": {
                    "deployment_name": "test-deployment",
                    "namespace": "default",
                    "patch": {"spec": {"replicas": 3}}
                }
            }
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("patch_deployment_test", context={})

    # Sem Kubernetes configurado, a ação retorna erro, mas execução completa
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_cleanup_poison_messages_action(tmp_path, mock_tracer):
    """Test the cleanup_poison_messages action."""
    playbook_path = tmp_path / "cleanup_poison_test.yaml"
    playbook_content = {
        "playbook_name": "cleanup_poison_test",
        "actions": [
            {
                "type": "cleanup_poison_messages",
                "parameters": {"topic": "test-topic", "partition": 0, "offset": 123}
            }
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("cleanup_poison_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_combined_actions(tmp_path, mock_tracer):
    """Test a playbook with multiple new action types."""
    playbook_path = tmp_path / "combined_test.yaml"
    playbook_content = {
        "playbook_name": "combined_test",
        "actions": [
            {"type": "wait", "parameters": {"seconds": 0.01}},
            {"type": "update_policy", "parameters": {"policy_name": "test-policy"}},
            {"type": "notify_agent", "parameters": {"agent_id": "test-agent", "notification_type": "INFO", "message": "test"}}
        ]
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("combined_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 3
