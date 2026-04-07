"""Testes para o playbook de recuperação de deadlock - TDD Approach."""
import pytest
import yaml
from pathlib import Path


class TestDeadlockRecoveryPlaybook:
    """Testes para verificar a existência e schema do playbook deadlock_recovery.yaml."""

    def test_deadlock_recovery_playbook_exists(self):
        """Verifica que o ficheiro do playbook existe."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent / "playbooks" / "deadlock_recovery.yaml"
        )
        assert playbook_path.exists(), "Playbook file does not exist"

    def test_deadlock_recovery_playbook_valid_schema(self):
        """Verifica que o playbook tem o schema válido."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent / "playbooks" / "deadlock_recovery.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert playbook["playbook_id"] == "deadlock-recovery-v1"
        assert "actions" in playbook
        assert len(playbook["actions"]) == 3

        # Verificar que as ações esperadas existem
        action_names = [action["name"] for action in playbook["actions"]]
        assert "pause_workflow" in action_names
        assert "get_workflow_status" in action_names
        assert "notify_agent" in action_names

    def test_deadlock_recovery_playbook_trigger(self):
        """Verifica que o playbook tem o trigger correto."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent / "playbooks" / "deadlock_recovery.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert "trigger" in playbook
        assert playbook["trigger"]["pattern"] == "workflow_deadlock"
        assert playbook["trigger"]["severity"] == "critical"
