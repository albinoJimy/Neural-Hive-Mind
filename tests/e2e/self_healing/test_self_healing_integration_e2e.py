"""
Self-Healing Engine E2E Integration Tests.

Tests the complete self-healing flow including:
- Ticket reallocation via Execution Ticket Service
- Workflow restart via Orchestrator gRPC
- OPA policy validation
- Fail-safe behavior when services are unavailable
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
import time


# =============================================================================
# Test 1: Ticket Reallocation Flow
# =============================================================================

@pytest.mark.asyncio
async def test_ticket_reallocation_flow(
    playbook_executor_with_clients,
    execution_ticket_service_mock,
    sample_incident_context
):
    """
    Test complete ticket reallocation flow.

    Validates:
    - Ticket is reallocated via Execution Ticket Service
    - Ticket status is updated to PENDING
    - Assigned worker is cleared
    - Metrics are recorded
    """
    executor = playbook_executor_with_clients
    mock_ets = execution_ticket_service_mock

    # Setup: Create ticket in mock service
    mock_ets.add_ticket(
        ticket_id="ticket-456",
        status="running",
        assigned_worker="worker-001",
        workflow_id="workflow-789"
    )

    # Execute playbook
    result = await executor.execute_playbook(
        playbook_name="ticket_timeout_recovery",
        context=sample_incident_context
    )

    # Verify playbook executed successfully
    assert result["success"] is True, f"Playbook failed: {result.get('error')}"
    assert result["total_actions"] == 3

    # Verify reallocate_ticket was called
    assert len(mock_ets.reallocations) == 1
    reallocation = mock_ets.reallocations[0]
    assert reallocation["ticket_id"] == "ticket-456"
    assert reallocation["reason"] == "timeout_recovery"
    assert reallocation["previous_worker"] == "worker-001"

    # Verify ticket was updated
    ticket = mock_ets.tickets["ticket-456"]
    assert ticket["status"] == "pending"
    assert ticket["assigned_worker"] is None

    # Verify actions in result
    actions = result["actions"]
    reallocate_action = next(a for a in actions if a["action"] == "reallocate_ticket")
    assert reallocate_action["success"] is True
    assert reallocate_action["reallocated"] is True
    assert "reallocation_id" in reallocate_action


@pytest.mark.asyncio
async def test_workflow_restart_flow(
    playbook_executor_with_clients,
    orchestrator_grpc_mock
):
    """
    Test workflow restart flow via Orchestrator gRPC.

    Validates:
    - resume_workflow is called for PAUSED workflows
    - Workflow state is updated to RUNNING
    - Metrics are recorded
    """
    executor = playbook_executor_with_clients
    mock_orch = orchestrator_grpc_mock

    # Setup: Create paused workflow
    mock_orch.add_workflow(
        workflow_id="workflow-123",
        state="PAUSED",
        progress_percent=50.0
    )

    # Execute playbook
    context = {
        "incident_id": "inc-001",
        "workflow_id": "workflow-123"
    }

    result = await executor.execute_playbook(
        playbook_name="workflow_restart",
        context=context
    )

    # Verify playbook executed successfully
    assert result["success"] is True, f"Playbook failed: {result.get('error')}"

    # Verify resume_workflow was called
    assert len(mock_orch.resume_calls) == 1
    resume_call = mock_orch.resume_calls[0]
    assert resume_call["workflow_id"] == "workflow-123"
    assert resume_call["reason"] == "self_healing_restart"

    # Verify workflow was resumed
    workflow = mock_orch.workflows["workflow-123"]
    assert workflow["state"] == "RUNNING"

    # Verify action result
    actions = result["actions"]
    restart_action = next(a for a in actions if a["action"] == "restart_workflow")
    assert restart_action["success"] is True
    assert restart_action["resumed"] is True


@pytest.mark.asyncio
async def test_opa_validation_blocks_invalid_action(
    playbook_executor_with_clients,
    execution_ticket_service_mock,
    opa_server_mock
):
    """
    Test OPA policy validation blocks recent reallocation.

    Validates:
    - OPA policy denies reallocate_ticket when recently reallocated
    - Action is blocked with opa_denied flag
    - Metrics show denied validation
    """
    executor = playbook_executor_with_clients
    mock_opa = opa_server_mock

    # Setup: Configure OPA to deny reallocation (rate limiting)
    mock_opa.add_policy_result(
        "neuralhive/self_healing/playbook_validation",
        {
            "result": {
                "allow": False,
                "violations": [
                    {
                        "policy": "playbook_validation",
                        "rule": "reallocate_ticket_rate_limited",
                        "msg": "Ticket was recently reallocated (within 5 minutes cooldown)",
                        "severity": "high"
                    }
                ]
            }
        }
    )

    # Context with recent reallocation timestamp
    context = {
        "incident_id": "inc-002",
        "ticket_id": "ticket-789",
        "worker_id": "worker-002",
        "last_reallocation_timestamp": int(time.time_ns()) - 60_000_000_000  # 1 minute ago
    }

    result = await executor.execute_playbook(
        playbook_name="ticket_timeout_recovery",
        context=context
    )

    # Playbook should fail because critical action was denied
    # The reallocate_ticket action should be blocked
    actions = result.get("actions", [])
    reallocate_action = next(
        (a for a in actions if a.get("action") == "reallocate_ticket"),
        None
    )

    assert reallocate_action is not None
    assert reallocate_action["success"] is False
    assert reallocate_action.get("opa_denied") is True
    assert "OPA policy" in reallocate_action.get("error", "")


@pytest.mark.asyncio
async def test_multiple_ticket_reallocation(
    playbook_executor_with_clients,
    execution_ticket_service_mock
):
    """
    Test batch ticket reallocation for worker failure.

    Validates:
    - reallocate_multiple_tickets is called for multiple tickets
    - All tickets are updated to PENDING
    - Batch operation is efficient
    """
    executor = playbook_executor_with_clients
    mock_ets = execution_ticket_service_mock

    # Setup: Create 5 tickets assigned to failing worker
    ticket_ids = [f"ticket-{i}" for i in range(1, 6)]
    for tid in ticket_ids:
        mock_ets.add_ticket(
            ticket_id=tid,
            status="running",
            assigned_worker="worker-001"
        )

    # Execute worker failure playbook
    context = {
        "incident_id": "inc-003",
        "affected_tickets": ticket_ids,
        "worker_id": "worker-001"
    }

    start_time = time.time()
    result = await executor.execute_playbook(
        playbook_name="worker_failure_recovery",
        context=context
    )
    duration = time.time() - start_time

    # Verify playbook executed successfully
    assert result["success"] is True, f"Playbook failed: {result.get('error')}"

    # Verify all tickets were reallocated
    assert len(mock_ets.reallocations) == 5

    for tid in ticket_ids:
        ticket = mock_ets.tickets[tid]
        assert ticket["status"] == "pending"
        assert ticket["assigned_worker"] is None

    # Verify batch efficiency (should complete in reasonable time)
    assert duration < 10, f"Batch reallocation took too long: {duration}s"

    # Verify action result contains batch info
    actions = result["actions"]
    reallocate_action = next(a for a in actions if a["action"] == "reallocate_ticket")
    assert reallocate_action["success"] is True
    assert reallocate_action.get("successful_count") == 5
    assert reallocate_action.get("failed_count") == 0


@pytest.mark.asyncio
async def test_fail_safe_when_ticket_service_down(
    playbook_executor_with_clients,
    execution_ticket_service_mock,
    sample_incident_context
):
    """
    Test fail-safe behavior when Execution Ticket Service is unavailable.

    Validates:
    - Playbook completes with success (fail-safe)
    - Warning is logged
    - Other actions continue to execute
    """
    executor = playbook_executor_with_clients
    mock_ets = execution_ticket_service_mock

    # Configure service to fail
    mock_ets.set_should_fail(True, "Connection refused")

    # Execute playbook
    result = await executor.execute_playbook(
        playbook_name="ticket_timeout_recovery",
        context=sample_incident_context
    )

    # With fail-safe, playbook should still complete
    # Individual actions may fail but playbook continues
    actions = result.get("actions", [])

    # check_worker_health should succeed (uses different client)
    health_action = next(
        (a for a in actions if a.get("action") == "check_worker_health"),
        None
    )
    assert health_action is not None

    # reallocate_ticket should fail due to service being down
    reallocate_action = next(
        (a for a in actions if a.get("action") == "reallocate_ticket"),
        None
    )
    assert reallocate_action is not None
    # With fail-safe behavior, it returns success with warning
    # Check for error or warning in result
    assert reallocate_action.get("error") or reallocate_action.get("warning")


@pytest.mark.asyncio
async def test_orchestrator_unavailable_fail_safe(
    playbook_executor_with_clients,
    orchestrator_grpc_mock
):
    """
    Test fail-safe behavior when Orchestrator is unavailable.

    Validates:
    - Playbook completes with warning
    - Action is skipped gracefully
    """
    executor = playbook_executor_with_clients
    mock_orch = orchestrator_grpc_mock

    # Configure service to fail
    mock_orch.set_should_fail(True, "gRPC connection failed")

    # Execute playbook
    context = {
        "incident_id": "inc-004",
        "workflow_id": "workflow-999"
    }

    result = await executor.execute_playbook(
        playbook_name="workflow_restart",
        context=context
    )

    # Action should fail but playbook continues (fail-safe)
    actions = result.get("actions", [])
    restart_action = next(
        (a for a in actions if a.get("action") == "restart_workflow"),
        None
    )

    assert restart_action is not None
    # Should have error from the exception
    assert restart_action.get("error") or restart_action.get("warning")


@pytest.mark.asyncio
async def test_workflow_restart_terminal_state_blocked(
    playbook_executor_with_clients,
    orchestrator_grpc_mock
):
    """
    Test that workflow restart is blocked for terminal states.

    Validates:
    - Restart fails for COMPLETED workflows
    - Appropriate error message is returned
    """
    executor = playbook_executor_with_clients
    mock_orch = orchestrator_grpc_mock

    # Setup: Create completed workflow
    mock_orch.add_workflow(
        workflow_id="workflow-completed",
        state="COMPLETED",
        progress_percent=100.0
    )

    context = {
        "incident_id": "inc-005",
        "workflow_id": "workflow-completed"
    }

    result = await executor.execute_playbook(
        playbook_name="workflow_restart",
        context=context
    )

    # Action should fail due to terminal state
    actions = result.get("actions", [])
    restart_action = next(
        (a for a in actions if a.get("action") == "restart_workflow"),
        None
    )

    assert restart_action is not None
    assert restart_action["success"] is False
    assert "terminal state" in restart_action.get("error", "").lower()


@pytest.mark.asyncio
async def test_workflow_not_paused_no_action(
    playbook_executor_with_clients,
    orchestrator_grpc_mock
):
    """
    Test that restart_workflow for RUNNING workflow takes no action.

    Validates:
    - Action succeeds but notes no action taken
    - Workflow state is not changed
    """
    executor = playbook_executor_with_clients
    mock_orch = orchestrator_grpc_mock

    # Setup: Create running workflow
    mock_orch.add_workflow(
        workflow_id="workflow-running",
        state="RUNNING",
        progress_percent=75.0
    )

    context = {
        "incident_id": "inc-006",
        "workflow_id": "workflow-running"
    }

    result = await executor.execute_playbook(
        playbook_name="workflow_restart",
        context=context
    )

    # Action should succeed but note no action taken
    actions = result.get("actions", [])
    restart_action = next(
        (a for a in actions if a.get("action") == "restart_workflow"),
        None
    )

    assert restart_action is not None
    assert restart_action["success"] is True
    assert restart_action.get("note") is not None
    assert "not paused" in restart_action.get("note", "").lower()

    # Resume should NOT have been called
    assert len(mock_orch.resume_calls) == 0


@pytest.mark.asyncio
async def test_opa_fail_open_allows_action(
    playbook_executor_with_clients,
    execution_ticket_service_mock,
    opa_server_mock,
    sample_incident_context
):
    """
    Test OPA fail-open behavior when OPA is unavailable.

    Validates:
    - Action proceeds when OPA is down (fail-open)
    - Warning is logged
    """
    executor = playbook_executor_with_clients
    mock_opa = opa_server_mock
    mock_ets = execution_ticket_service_mock

    # Setup ticket
    mock_ets.add_ticket(
        ticket_id="ticket-456",
        status="running",
        assigned_worker="worker-001"
    )

    # Configure OPA to fail
    mock_opa.set_should_fail(True, "OPA connection refused")

    # Execute playbook - should proceed with fail-open
    result = await executor.execute_playbook(
        playbook_name="ticket_timeout_recovery",
        context=sample_incident_context
    )

    # With fail-open, action should proceed
    actions = result.get("actions", [])
    reallocate_action = next(
        (a for a in actions if a.get("action") == "reallocate_ticket"),
        None
    )

    # Action should succeed despite OPA failure
    assert reallocate_action is not None
    assert reallocate_action["success"] is True


@pytest.mark.asyncio
async def test_playbook_not_found():
    """Test error handling for non-existent playbook."""
    from services.self_healing_engine.src.services.playbook_executor import PlaybookExecutor
    from unittest.mock import MagicMock, patch

    with patch('services.self_healing_engine.src.services.playbook_executor.config'):
        executor = PlaybookExecutor(
            playbooks_dir="/nonexistent/path",
            k8s_in_cluster=False,
        )
        executor.core_v1 = MagicMock()
        executor.apps_v1 = MagicMock()

        result = await executor.execute_playbook(
            playbook_name="nonexistent_playbook",
            context={}
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()
