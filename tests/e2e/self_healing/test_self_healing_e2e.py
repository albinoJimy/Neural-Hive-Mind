import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT_DIR / "services/self-healing-engine/src"))
import pytest

from src.models.remediation_models import RemediationRequest
from src.services.remediation_manager import RemediationManager, RemediationStatus


class FakeExecutor:
    async def execute_playbook(self, playbook_name: str, context: dict, on_action_completed=None, on_playbook_completed=None, **kwargs):
        if on_action_completed:
            await on_action_completed({"success": True})
        result = {"success": True, "actions": []}
        if on_playbook_completed:
            await on_playbook_completed(result)
        return result


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ticket_timeout_flow_completes():
    manager = RemediationManager(default_timeout_seconds=1)
    request = RemediationRequest(
        remediation_id="r-123",
        incident_id="inc-1",
        playbook_name="ticket_timeout_recovery",
        parameters={"ticket_id": "t-1"},
        execution_mode="AUTOMATIC"
    )

    state = manager.start_remediation(request, total_actions=1)
    await manager.execute_remediation(state, FakeExecutor(), request)

    assert state.status == RemediationStatus.COMPLETED
    assert state.actions_completed >= 1
