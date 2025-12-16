"""Temporal SDK helpers for E2E testing of Phase 2 Flow C."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from temporalio.client import Client, WorkflowHandle

logger = logging.getLogger(__name__)

# Default Temporal configuration
DEFAULT_TEMPORAL_ENDPOINT = "temporal-frontend.neural-hive-temporal.svc.cluster.local:7233"
DEFAULT_NAMESPACE = "default"
DEFAULT_TASK_QUEUE = "orchestration-tasks"


@dataclass
class WorkflowStatus:
    """Represents the status of a Temporal workflow."""

    workflow_id: str
    run_id: str
    status: str  # running, completed, failed, cancelled, terminated
    started_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ActivityExecution:
    """Represents an activity execution within a workflow."""

    activity_name: str
    activity_type: str
    status: str  # scheduled, started, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    retry_count: int = 0
    error: Optional[str] = None


class TemporalTestHelper:
    """Helper class for Temporal workflow testing."""

    def __init__(
        self,
        endpoint: str = DEFAULT_TEMPORAL_ENDPOINT,
        namespace: str = DEFAULT_NAMESPACE,
    ):
        self.endpoint = endpoint
        self.namespace = namespace
        self._client: Optional[Client] = None

    async def connect(self) -> None:
        """Connect to the Temporal server."""
        if self._client is None:
            self._client = await Client.connect(
                self.endpoint,
                namespace=self.namespace,
            )
            logger.info(f"Connected to Temporal at {self.endpoint}")

    async def close(self) -> None:
        """Close the Temporal client connection."""
        if self._client:
            # Note: temporalio client doesn't have explicit close
            self._client = None

    @property
    def client(self) -> Client:
        """Get the Temporal client."""
        if self._client is None:
            raise RuntimeError("Temporal client not connected. Call connect() first.")
        return self._client

    async def get_workflow_handle(self, workflow_id: str) -> WorkflowHandle:
        """Get a handle to an existing workflow."""
        return self.client.get_workflow_handle(workflow_id)

    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        """
        Get the current status of a workflow.

        Args:
            workflow_id: The workflow ID to check

        Returns:
            WorkflowStatus with current state information
        """
        handle = await self.get_workflow_handle(workflow_id)
        describe = await handle.describe()

        status_map = {
            1: "running",
            2: "completed",
            3: "failed",
            4: "cancelled",
            5: "terminated",
            6: "continued_as_new",
            7: "timed_out",
        }

        status = status_map.get(describe.status, "unknown")

        execution_time_ms = None
        if describe.start_time and describe.close_time:
            delta = describe.close_time - describe.start_time
            execution_time_ms = int(delta.total_seconds() * 1000)

        result = None
        error = None
        if status == "completed":
            try:
                result = await handle.result()
            except Exception as e:
                error = str(e)
        elif status == "failed":
            error = f"Workflow failed"

        return WorkflowStatus(
            workflow_id=workflow_id,
            run_id=describe.run_id,
            status=status,
            started_at=describe.start_time,
            closed_at=describe.close_time,
            execution_time_ms=execution_time_ms,
            result=result,
            error=error,
        )

    async def query_workflow(
        self, workflow_id: str, query_name: str, *args: Any
    ) -> Any:
        """
        Execute a query on a workflow.

        Args:
            workflow_id: The workflow ID
            query_name: Name of the query (e.g., "get_status", "get_tickets")
            *args: Arguments to pass to the query

        Returns:
            Query result
        """
        handle = await self.get_workflow_handle(workflow_id)
        return await handle.query(query_name, *args)

    async def wait_for_workflow_completion(
        self,
        workflow_id: str,
        timeout_seconds: int = 300,
        poll_interval_seconds: int = 5,
    ) -> WorkflowStatus:
        """
        Wait for a workflow to complete.

        Args:
            workflow_id: The workflow ID to wait for
            timeout_seconds: Maximum time to wait
            poll_interval_seconds: Time between status checks

        Returns:
            Final WorkflowStatus

        Raises:
            TimeoutError if workflow doesn't complete within timeout
        """
        start_time = datetime.utcnow()
        deadline = start_time + timedelta(seconds=timeout_seconds)

        while datetime.utcnow() < deadline:
            status = await self.get_workflow_status(workflow_id)

            if status.status in ["completed", "failed", "cancelled", "terminated", "timed_out"]:
                return status

            await asyncio.sleep(poll_interval_seconds)

        raise TimeoutError(
            f"Workflow {workflow_id} did not complete within {timeout_seconds} seconds"
        )

    async def get_workflow_history(
        self, workflow_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get the event history of a workflow.

        Args:
            workflow_id: The workflow ID

        Returns:
            List of workflow history events with full attributes
        """
        handle = await self.get_workflow_handle(workflow_id)
        events = []

        async for event in handle.fetch_history_events():
            event_dict = {
                "event_id": event.event_id,
                "event_type": event.event_type.name if hasattr(event.event_type, 'name') else str(event.event_type),
                "timestamp": event.event_time,
            }

            # Extract activity-specific attributes for scheduled events
            if hasattr(event, 'activity_task_scheduled_event_attributes'):
                attrs = event.activity_task_scheduled_event_attributes
                if attrs:
                    event_dict["activity_type"] = attrs.activity_type.name if hasattr(attrs.activity_type, 'name') else str(attrs.activity_type)
                    event_dict["activity_id"] = attrs.activity_id if hasattr(attrs, 'activity_id') else None

            # Extract scheduled_event_id for started/completed/failed events
            if hasattr(event, 'activity_task_started_event_attributes'):
                attrs = event.activity_task_started_event_attributes
                if attrs and hasattr(attrs, 'scheduled_event_id'):
                    event_dict["scheduled_event_id"] = attrs.scheduled_event_id

            if hasattr(event, 'activity_task_completed_event_attributes'):
                attrs = event.activity_task_completed_event_attributes
                if attrs and hasattr(attrs, 'scheduled_event_id'):
                    event_dict["scheduled_event_id"] = attrs.scheduled_event_id

            if hasattr(event, 'activity_task_failed_event_attributes'):
                attrs = event.activity_task_failed_event_attributes
                if attrs and hasattr(attrs, 'scheduled_event_id'):
                    event_dict["scheduled_event_id"] = attrs.scheduled_event_id
                    if hasattr(attrs, 'failure'):
                        event_dict["failure_message"] = str(attrs.failure)

            events.append(event_dict)

        return events

    async def get_activity_executions(
        self, workflow_id: str
    ) -> List[ActivityExecution]:
        """
        Extract activity executions from workflow history.

        Args:
            workflow_id: The workflow ID

        Returns:
            List of ActivityExecution objects with real activity names/types
        """
        history = await self.get_workflow_history(workflow_id)
        # Key by scheduled_event_id to correlate scheduled/started/completed events
        activities: Dict[int, ActivityExecution] = {}

        for event in history:
            event_type = event["event_type"]
            event_id = event.get("event_id")

            # Track activity scheduling - capture real activity type name
            if event_type == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
                activity_type = event.get("activity_type", "unknown")
                activities[event_id] = ActivityExecution(
                    activity_name=activity_type,  # Use real activity type as name
                    activity_type=activity_type,
                    status="scheduled",
                )

            # Track activity start - use scheduled_event_id to find the activity
            elif event_type == "EVENT_TYPE_ACTIVITY_TASK_STARTED":
                scheduled_id = event.get("scheduled_event_id")
                if scheduled_id and scheduled_id in activities:
                    activities[scheduled_id].status = "started"
                    activities[scheduled_id].started_at = event.get("timestamp")

            # Track activity completion - use scheduled_event_id
            elif event_type == "EVENT_TYPE_ACTIVITY_TASK_COMPLETED":
                scheduled_id = event.get("scheduled_event_id")
                if scheduled_id and scheduled_id in activities:
                    act = activities[scheduled_id]
                    act.status = "completed"
                    act.completed_at = event.get("timestamp")
                    if act.started_at and act.completed_at:
                        delta = act.completed_at - act.started_at
                        act.duration_ms = int(delta.total_seconds() * 1000)

            # Track activity failure - use scheduled_event_id
            elif event_type == "EVENT_TYPE_ACTIVITY_TASK_FAILED":
                scheduled_id = event.get("scheduled_event_id")
                if scheduled_id and scheduled_id in activities:
                    act = activities[scheduled_id]
                    act.status = "failed"
                    act.error = event.get("failure_message", "Activity execution failed")
                    act.retry_count += 1

        return list(activities.values())


async def validate_temporal_workflow(
    workflow_id: str,
    temporal_endpoint: str = DEFAULT_TEMPORAL_ENDPOINT,
    namespace: str = DEFAULT_NAMESPACE,
    expected_status: str = "completed",
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Validate a Temporal workflow execution.

    Args:
        workflow_id: The workflow ID to validate
        temporal_endpoint: Temporal server endpoint
        namespace: Temporal namespace
        expected_status: Expected workflow status
        timeout_seconds: Timeout for waiting

    Returns:
        Validation result dictionary
    """
    helper = TemporalTestHelper(endpoint=temporal_endpoint, namespace=namespace)
    await helper.connect()

    try:
        # Wait for workflow to complete
        status = await helper.wait_for_workflow_completion(
            workflow_id, timeout_seconds=timeout_seconds
        )

        # Validate status
        status_valid = status.status == expected_status

        # Try to get tickets from workflow query
        tickets_count = 0
        try:
            tickets = await helper.query_workflow(workflow_id, "get_tickets")
            tickets_count = len(tickets) if tickets else 0
        except Exception as e:
            logger.warning(f"Could not query tickets: {e}")

        return {
            "valid": status_valid,
            "workflow_id": workflow_id,
            "status": status.status,
            "expected_status": expected_status,
            "execution_time_ms": status.execution_time_ms,
            "tickets_count": tickets_count,
            "result": status.result,
            "error": status.error,
        }
    finally:
        await helper.close()


async def validate_temporal_activities(
    workflow_id: str,
    expected_activities: List[str],
    temporal_endpoint: str = DEFAULT_TEMPORAL_ENDPOINT,
    namespace: str = DEFAULT_NAMESPACE,
) -> Dict[str, Any]:
    """
    Validate that expected activities were executed in a workflow.

    Args:
        workflow_id: The workflow ID
        expected_activities: List of expected activity names (supports partial matching)
        temporal_endpoint: Temporal server endpoint
        namespace: Temporal namespace

    Returns:
        Validation result dictionary
    """
    helper = TemporalTestHelper(endpoint=temporal_endpoint, namespace=namespace)
    await helper.connect()

    try:
        activities = await helper.get_activity_executions(workflow_id)

        # Check for completed activities
        completed_activities = [a for a in activities if a.status == "completed"]
        failed_activities = [a for a in activities if a.status == "failed"]

        # Get activity names and types (both for matching)
        executed_names = set()
        for a in completed_activities:
            executed_names.add(a.activity_name)
            executed_names.add(a.activity_type)
            # Also add lowercase versions for case-insensitive matching
            executed_names.add(a.activity_name.lower())
            executed_names.add(a.activity_type.lower())

        # Check expected activities with partial matching
        missing_activities = []
        found_activities = []
        for expected in expected_activities:
            expected_lower = expected.lower()
            # Exact match
            if expected in executed_names or expected_lower in executed_names:
                found_activities.append(expected)
                continue
            # Partial match (activity names may have prefixes/suffixes)
            found = False
            for name in executed_names:
                if expected_lower in name.lower() or name.lower() in expected_lower:
                    found_activities.append(expected)
                    found = True
                    break
            if not found:
                missing_activities.append(expected)

        return {
            "valid": len(missing_activities) == 0 and len(failed_activities) == 0,
            "workflow_id": workflow_id,
            "total_activities": len(activities),
            "completed_activities": len(completed_activities),
            "failed_activities": len(failed_activities),
            "found_activities": found_activities,
            "missing_activities": missing_activities,
            "executed_activity_names": list({a.activity_name for a in activities}),
            "activity_details": [
                {
                    "name": a.activity_name,
                    "type": a.activity_type,
                    "status": a.status,
                    "duration_ms": a.duration_ms,
                    "error": a.error,
                }
                for a in activities
            ],
        }
    finally:
        await helper.close()
