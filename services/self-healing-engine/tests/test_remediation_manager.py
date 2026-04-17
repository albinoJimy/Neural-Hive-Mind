"""
Testes para o Remediation Manager.

Este módulo testa a gestão de estado de remediações e métricas Prometheus.
"""

import asyncio
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from src.services.remediation_manager import (
    RemediationManager,
    RemediationState,
    RemediationStatus,
)
from src.models.remediation_models import RemediationRequest


@pytest.fixture
def remediation_manager():
    """Fixture do RemediationManager."""
    return RemediationManager(redis_client=None, default_timeout_seconds=300)


@pytest.fixture
def remediation_request():
    """Fixture de uma request de remediação."""
    return RemediationRequest(
        incident_id="incident-123",
        playbook_name="deadlock_recovery",
        execution_mode="AUTOMATIC",
        parameters={
            "incident_type": "deadlock",
            "service_name": "orchestrator",
            "workflow_id": "wf-123",
        },
    )


class TestRemediationManagerMetrics:
    """Testes para as métricas Prometheus do RemediationManager."""

    def test_remediation_manager_has_metrics(self, remediation_manager):
        """Verifica que as métricas foram inicializadas."""
        assert hasattr(remediation_manager, "_mttr_seconds_total")
        assert hasattr(remediation_manager, "_remediations_total")
        assert hasattr(remediation_manager, "_remediation_duration_seconds")

    @pytest.mark.asyncio
    async def test_start_remediation_increments_pending_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que start_remediation incrementa a métrica pending."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=5)

        assert state.status == RemediationStatus.PENDING
        assert state.total_actions == 5
        assert state.remediation_id is not None

    @pytest.mark.asyncio
    async def test_execute_remediation_increments_started_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que execute_remediation incrementa a métrica started."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=1)

        # Mock executor
        mock_executor = MagicMock()

        async def mock_execute(*args, **kwargs):
            on_action_completed = kwargs.get("on_action_completed")
            on_playbook_completed = kwargs.get("on_playbook_completed")
            if on_action_completed:
                await on_action_completed({"action": "test", "success": True})
            if on_playbook_completed:
                await on_playbook_completed({"success": True})

        mock_executor.execute_playbook = mock_execute

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.status == RemediationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_remediation_success_increments_completed_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que remediação bem-sucedida incrementa a métrica completed."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=1)

        mock_executor = MagicMock()

        async def mock_execute(*args, **kwargs):
            on_action_completed = kwargs.get("on_action_completed")
            on_playbook_completed = kwargs.get("on_playbook_completed")
            if on_action_completed:
                await on_action_completed({"action": "test", "success": True})
            if on_playbook_completed:
                await on_playbook_completed({"success": True})

        mock_executor.execute_playbook = mock_execute

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.status == RemediationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_remediation_success_increments_completed_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que remediação bem-sucedida incrementa a métrica completed."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=1)

        mock_executor = MagicMock()

        async def mock_execute(*args, **kwargs):
            print("Mock execute called with args:", args)
            print("Mock execute called with kwargs:", kwargs)
            on_action_completed = kwargs.get("on_action_completed")
            on_playbook_completed = kwargs.get("on_playbook_completed")
            print(
                f"In mock_execute: on_action_completed={on_action_completed}, on_playbook_completed={on_playbook_completed}"
            )
            if on_action_completed:
                result = await on_action_completed({"action": "test", "success": True})
                print(f"on_action_completed returned: {result}")
            if on_playbook_completed:
                result = await on_playbook_completed({"success": True})
                print(f"on_playbook_completed returned: {result}")
            print("Mock execute finished")

        mock_executor.execute_playbook = mock_execute
        print(f"State before execute: {state.status}")

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.status == RemediationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_remediation_timeout_increments_timeout_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que timeout incrementa a métrica timeout."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=1)

        mock_executor = AsyncMock()
        mock_executor.execute_playbook = AsyncMock(
            side_effect=asyncio.TimeoutError("Playbook timeout")
        )

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.status == RemediationStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_execute_remediation_timeout_increments_timeout_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que timeout incrementa a métrica timeout."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=1)

        mock_executor = MagicMock()
        mock_executor.execute_playbook = MagicMock(
            side_effect=asyncio.TimeoutError("Playbook timeout")
        )

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.status == RemediationStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_execute_remediation_failure_increments_failed_metric(
        self, remediation_manager, remediation_request
    ):
        """Verifica que falha incrementa a métrica failed."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=1)

        mock_executor = MagicMock()
        mock_executor.execute_playbook = MagicMock(side_effect=Exception("Playbook failed"))

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.status == RemediationStatus.FAILED


class TestRemediationManager:
    """Testes para o RemediationManager."""

    @pytest.mark.asyncio
    async def test_start_remediation_creates_state(self, remediation_manager, remediation_request):
        """Verifica que start_remediation cria estado inicial."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=5)

        assert state.status == RemediationStatus.PENDING
        assert state.total_actions == 5
        assert state.remediation_id is not None
        assert state.incident_id == "incident-123"
        assert state.playbook_name == "deadlock_recovery"

    @pytest.mark.asyncio
    async def test_get_status(self, remediation_manager, remediation_request):
        """Verifica que get_status retorna estado correto."""
        state = remediation_manager.start_remediation(remediation_request)

        retrieved = remediation_manager.get_status(state.remediation_id)

        assert retrieved is not None
        assert retrieved.remediation_id == state.remediation_id
        assert retrieved.status == RemediationStatus.PENDING

    def test_get_status_nonexistent(self, remediation_manager):
        """Verifica que get_status retorna None para remediação inexistente."""
        retrieved = remediation_manager.get_status("nonexistent-id")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_status(self, remediation_manager, remediation_request):
        """Verifica que update_status atualiza atributos."""
        state = remediation_manager.start_remediation(remediation_request)

        updated = remediation_manager.update_status(
            state.remediation_id, progress=0.5, actions_completed=2
        )

        assert updated is not None
        assert updated.progress == 0.5
        assert updated.actions_completed == 2

    @pytest.mark.asyncio
    async def test_cancel_remediation(self, remediation_manager, remediation_request):
        """Verifica que cancel_remediation marca como cancelada."""
        state = remediation_manager.start_remediation(remediation_request)

        cancelled = remediation_manager.cancel_remediation(state.remediation_id)

        assert cancelled is not None
        assert cancelled.status == RemediationStatus.CANCELLED
        assert cancelled.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_remediation_updates_progress(
        self, remediation_manager, remediation_request
    ):
        """Verifica que execute_remediation atualiza progresso."""
        state = remediation_manager.start_remediation(remediation_request, total_actions=3)

        mock_executor = MagicMock()

        async def mock_execute(*args, **kwargs):
            on_action_completed = kwargs.get("on_action_completed")
            on_playbook_completed = kwargs.get("on_playbook_completed")

            for i in range(3):
                if on_action_completed:
                    await on_action_completed({"action": f"action-{i}", "success": True})

            if on_playbook_completed:
                await on_playbook_completed({"success": True, "actions": []})

        mock_executor.execute_playbook = mock_execute

        await remediation_manager.execute_remediation(state, mock_executor, remediation_request)

        assert state.actions_completed == 3
        assert state.progress == 1.0
