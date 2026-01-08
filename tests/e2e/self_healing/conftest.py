"""
Pytest fixtures for Self-Healing Engine E2E tests.

Provides mock servers and clients for:
- Execution Ticket Service (HTTP)
- Orchestrator Dynamic (gRPC)
- OPA Policy Engine (HTTP)
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# =============================================================================
# Execution Ticket Service Mock
# =============================================================================

class MockExecutionTicketService:
    """Mock HTTP server for Execution Ticket Service."""

    def __init__(self):
        self.tickets: Dict[str, Dict[str, Any]] = {}
        self.reallocations: List[Dict[str, Any]] = []
        self.status_updates: List[Dict[str, Any]] = []
        self._should_fail = False
        self._failure_message = "Service unavailable"

    def add_ticket(self, ticket_id: str, **kwargs):
        """Add a ticket to the mock store."""
        self.tickets[ticket_id] = {
            "ticket_id": ticket_id,
            "status": kwargs.get("status", "running"),
            "assigned_worker": kwargs.get("assigned_worker"),
            "workflow_id": kwargs.get("workflow_id"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **kwargs
        }

    def set_should_fail(self, should_fail: bool, message: str = "Service unavailable"):
        """Configure the mock to fail requests."""
        self._should_fail = should_fail
        self._failure_message = message

    async def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Get ticket by ID."""
        if self._should_fail:
            raise Exception(self._failure_message)

        if ticket_id not in self.tickets:
            raise Exception(f"Ticket not found: {ticket_id}")

        return self.tickets[ticket_id]

    async def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        result: Optional[Dict] = None,
        assigned_worker: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Update ticket status."""
        if self._should_fail:
            raise Exception(self._failure_message)

        if ticket_id not in self.tickets:
            # Create ticket if it doesn't exist
            self.tickets[ticket_id] = {
                "ticket_id": ticket_id,
                "created_at": datetime.utcnow().isoformat(),
            }

        self.tickets[ticket_id]["status"] = status
        self.tickets[ticket_id]["updated_at"] = datetime.utcnow().isoformat()

        if assigned_worker is not None:
            self.tickets[ticket_id]["assigned_worker"] = assigned_worker
        if result is not None:
            self.tickets[ticket_id]["result"] = result
        if metadata:
            if "metadata" not in self.tickets[ticket_id]:
                self.tickets[ticket_id]["metadata"] = {}
            self.tickets[ticket_id]["metadata"].update(metadata)

        self.status_updates.append({
            "ticket_id": ticket_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })

        return self.tickets[ticket_id]

    async def reallocate_ticket(
        self,
        ticket_id: str,
        reason: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Reallocate a ticket."""
        if self._should_fail:
            raise Exception(self._failure_message)

        reallocation_id = str(uuid4())

        # Get previous worker before clearing
        previous_worker = None
        if ticket_id in self.tickets:
            previous_worker = self.tickets[ticket_id].get("assigned_worker")

        # Update ticket
        result = await self.update_ticket_status(
            ticket_id=ticket_id,
            status="pending",
            assigned_worker=None,
            metadata={
                "reallocation_id": reallocation_id,
                "reallocation_reason": reason,
                "reallocation_timestamp": datetime.utcnow().isoformat(),
                **(metadata or {})
            }
        )

        self.reallocations.append({
            "ticket_id": ticket_id,
            "reallocation_id": reallocation_id,
            "reason": reason,
            "previous_worker": previous_worker,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            **result,
            "reallocation_id": reallocation_id,
            "previous_worker": previous_worker,
            "reallocated": True
        }

    async def reallocate_multiple_tickets(
        self,
        ticket_ids: List[str],
        reason: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Reallocate multiple tickets."""
        if self._should_fail:
            raise Exception(self._failure_message)

        batch_id = str(uuid4())
        results = []
        successful = 0
        failed = 0

        for ticket_id in ticket_ids:
            try:
                result = await self.reallocate_ticket(
                    ticket_id=ticket_id,
                    reason=reason,
                    metadata={**(metadata or {}), "batch_id": batch_id}
                )
                results.append({"ticket_id": ticket_id, "success": True, "result": result})
                successful += 1
            except Exception as e:
                results.append({"ticket_id": ticket_id, "success": False, "error": str(e)})
                failed += 1

        return {
            "batch_id": batch_id,
            "total": len(ticket_ids),
            "successful": successful,
            "failed": failed,
            "results": results
        }


# =============================================================================
# Orchestrator gRPC Mock
# =============================================================================

class MockOrchestratorClient:
    """Mock gRPC client for Orchestrator Dynamic."""

    def __init__(self):
        self.workflows: Dict[str, Dict[str, Any]] = {}
        self.pause_calls: List[Dict[str, Any]] = []
        self.resume_calls: List[Dict[str, Any]] = []
        self.replanning_calls: List[Dict[str, Any]] = []
        self._should_fail = False
        self._failure_message = "gRPC unavailable"

    def add_workflow(self, workflow_id: str, **kwargs):
        """Add a workflow to the mock store."""
        self.workflows[workflow_id] = {
            "workflow_id": workflow_id,
            "plan_id": kwargs.get("plan_id", f"plan-{workflow_id}"),
            "state": kwargs.get("state", "RUNNING"),
            "current_priority": kwargs.get("current_priority", 5),
            "progress_percent": kwargs.get("progress_percent", 50.0),
            "started_at": int(datetime.utcnow().timestamp()),
            "updated_at": int(datetime.utcnow().timestamp()),
            "tickets": kwargs.get("tickets", {
                "total": 10,
                "completed": 5,
                "pending": 3,
                "running": 2,
                "failed": 0
            }),
            **kwargs
        }

    def set_should_fail(self, should_fail: bool, message: str = "gRPC unavailable"):
        """Configure the mock to fail requests."""
        self._should_fail = should_fail
        self._failure_message = message

    async def initialize(self):
        """Initialize mock client."""
        pass

    async def close(self):
        """Close mock client."""
        pass

    async def pause_workflow(
        self,
        workflow_id: str,
        reason: str,
        duration_seconds: Optional[int] = None,
        adjustment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Pause a workflow."""
        if self._should_fail:
            raise Exception(self._failure_message)

        if workflow_id not in self.workflows:
            return {"success": False, "message": f"Workflow not found: {workflow_id}"}

        self.workflows[workflow_id]["state"] = "PAUSED"
        self.workflows[workflow_id]["updated_at"] = int(datetime.utcnow().timestamp())

        adj_id = adjustment_id or str(uuid4())
        paused_at = int(datetime.utcnow().timestamp())

        self.pause_calls.append({
            "workflow_id": workflow_id,
            "reason": reason,
            "adjustment_id": adj_id,
            "timestamp": datetime.utcnow().isoformat()
        })

        result = {
            "success": True,
            "message": "Workflow paused",
            "paused_at": paused_at,
            "workflow_id": workflow_id,
            "adjustment_id": adj_id
        }

        if duration_seconds:
            result["scheduled_resume_at"] = paused_at + duration_seconds

        return result

    async def resume_workflow(
        self,
        workflow_id: str,
        reason: str,
        adjustment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resume a paused workflow."""
        if self._should_fail:
            raise Exception(self._failure_message)

        if workflow_id not in self.workflows:
            return {"success": False, "message": f"Workflow not found: {workflow_id}"}

        prev_state = self.workflows[workflow_id]["state"]
        if prev_state != "PAUSED":
            return {"success": False, "message": f"Workflow not paused: {prev_state}"}

        self.workflows[workflow_id]["state"] = "RUNNING"
        self.workflows[workflow_id]["updated_at"] = int(datetime.utcnow().timestamp())

        adj_id = adjustment_id or str(uuid4())
        resumed_at = int(datetime.utcnow().timestamp())

        self.resume_calls.append({
            "workflow_id": workflow_id,
            "reason": reason,
            "adjustment_id": adj_id,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "success": True,
            "message": "Workflow resumed",
            "resumed_at": resumed_at,
            "pause_duration_seconds": 60,  # Mock value
            "workflow_id": workflow_id,
            "adjustment_id": adj_id
        }

    async def get_workflow_status(
        self,
        workflow_id: str,
        include_tickets: bool = True,
        include_history: bool = False
    ) -> Dict[str, Any]:
        """Get workflow status."""
        if self._should_fail:
            raise Exception(self._failure_message)

        if workflow_id not in self.workflows:
            raise Exception(f"Workflow not found: {workflow_id}")

        result = dict(self.workflows[workflow_id])

        if not include_tickets:
            result.pop("tickets", None)

        return result

    async def trigger_replanning(
        self,
        plan_id: str,
        reason: str,
        trigger_type: str = "TRIGGER_TYPE_STRATEGIC",
        preserve_progress: bool = True,
        context: Optional[Dict[str, str]] = None,
        adjustment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Trigger replanning."""
        if self._should_fail:
            raise Exception(self._failure_message)

        adj_id = adjustment_id or str(uuid4())
        replanning_id = str(uuid4())

        self.replanning_calls.append({
            "plan_id": plan_id,
            "reason": reason,
            "trigger_type": trigger_type,
            "adjustment_id": adj_id,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "success": True,
            "message": "Replanning triggered",
            "replanning_id": replanning_id,
            "triggered_at": int(datetime.utcnow().timestamp()),
            "plan_id": plan_id,
            "adjustment_id": adj_id
        }


# =============================================================================
# OPA Mock
# =============================================================================

class MockOPAClient:
    """Mock OPA client for policy evaluation."""

    def __init__(self):
        self._policies: Dict[str, Dict[str, Any]] = {}
        self._should_fail = False
        self._failure_message = "OPA unavailable"

    def add_policy_result(self, policy_path: str, result: Dict[str, Any]):
        """Add a mock policy result."""
        self._policies[policy_path] = result

    def set_should_fail(self, should_fail: bool, message: str = "OPA unavailable"):
        """Configure the mock to fail requests."""
        self._should_fail = should_fail
        self._failure_message = message

    async def initialize(self):
        """Initialize mock client."""
        pass

    async def close(self):
        """Close mock client."""
        pass

    async def evaluate_policy(self, policy_path: str, input_data: Dict) -> Dict[str, Any]:
        """Evaluate a policy."""
        if self._should_fail:
            raise Exception(self._failure_message)

        if policy_path in self._policies:
            return self._policies[policy_path]

        # Default: allow all
        return {
            "result": {
                "allow": True,
                "violations": []
            }
        }


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def execution_ticket_service_mock():
    """Provide a mock Execution Ticket Service."""
    return MockExecutionTicketService()


@pytest.fixture
def orchestrator_grpc_mock():
    """Provide a mock Orchestrator gRPC client."""
    return MockOrchestratorClient()


@pytest.fixture
def opa_server_mock():
    """Provide a mock OPA server."""
    return MockOPAClient()


@pytest_asyncio.fixture
async def playbook_executor_with_clients(
    execution_ticket_service_mock,
    orchestrator_grpc_mock,
    opa_server_mock,
    tmp_path
):
    """
    Provide a PlaybookExecutor with mock clients.

    Creates a temporary playbooks directory with test playbooks.
    """
    from services.self_healing_engine.src.services.playbook_executor import PlaybookExecutor

    # Create test playbooks directory
    playbooks_dir = tmp_path / "playbooks"
    playbooks_dir.mkdir()

    # Create a test playbook
    test_playbook = playbooks_dir / "ticket_timeout_recovery.yaml"
    test_playbook.write_text("""
name: ticket_timeout_recovery
description: Recover from ticket timeout
timeout_seconds: 60
actions:
  - type: check_worker_health
    parameters:
      worker_id: "{{ worker_id }}"
  - type: reallocate_ticket
    parameters:
      ticket_id: "{{ ticket_id }}"
      reason: timeout_recovery
  - type: update_ticket_status
    parameters:
      ticket_id: "{{ ticket_id }}"
      status: pending
""")

    # Create worker failure playbook
    worker_failure_playbook = playbooks_dir / "worker_failure_recovery.yaml"
    worker_failure_playbook.write_text("""
name: worker_failure_recovery
description: Recover from worker failure
timeout_seconds: 120
actions:
  - type: reallocate_ticket
    parameters:
      affected_tickets: "{{ affected_tickets }}"
      reason: worker_failure
""")

    # Create workflow restart playbook
    workflow_restart_playbook = playbooks_dir / "workflow_restart.yaml"
    workflow_restart_playbook.write_text("""
name: workflow_restart
description: Restart a paused workflow
timeout_seconds: 30
actions:
  - type: restart_workflow
    parameters:
      workflow_id: "{{ workflow_id }}"
      reason: self_healing_restart
""")

    # Mock Kubernetes initialization
    with patch('services.self_healing_engine.src.services.playbook_executor.config'):
        executor = PlaybookExecutor(
            playbooks_dir=str(playbooks_dir),
            k8s_in_cluster=False,
            default_timeout_seconds=60,
            service_registry_client=None,
            execution_ticket_client=execution_ticket_service_mock,
            orchestrator_client=orchestrator_grpc_mock,
            opa_client=opa_server_mock,
            opa_enabled=True,
            opa_fail_open=True,
        )

        # Skip K8s initialization for tests
        executor.core_v1 = MagicMock()
        executor.apps_v1 = MagicMock()

        yield executor


@pytest.fixture
def sample_incident_context():
    """Provide sample incident context for tests."""
    return {
        "incident_id": "inc-123",
        "ticket_id": "ticket-456",
        "workflow_id": "workflow-789",
        "worker_id": "worker-001",
        "namespace": "neural-hive-execution",
        "timestamp": datetime.utcnow().isoformat()
    }
