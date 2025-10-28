"""
Worker Agent client for task assignment and monitoring.
"""

import httpx
import structlog
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class TaskAssignment(BaseModel):
    """Task assignment request."""
    task_id: str
    ticket_id: str
    task_type: str
    payload: Dict[str, Any]
    sla_deadline: str


class TaskStatus(BaseModel):
    """Task status response."""
    task_id: str
    status: str
    progress: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkerAgentClient:
    """Client for Worker Agent service."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        """
        Initialize Worker Agent client.

        Args:
            base_url: Worker endpoint (discovered via Service Registry if None)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout) if base_url else None
        self.logger = logger.bind(service="worker_agent_client")

    def set_endpoint(self, base_url: str):
        """Set worker endpoint after discovery."""
        self.base_url = base_url
        if not self.client:
            self.client = httpx.AsyncClient(timeout=30)

    async def close(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("worker_agent.assign_task")
    async def assign_task(self, task: TaskAssignment) -> bool:
        """
        Assign task to worker.

        Args:
            task: Task assignment data

        Returns:
            True if assigned successfully
        """
        if not self.base_url or not self.client:
            raise ValueError("Worker endpoint not configured")

        self.logger.info(
            "assigning_task",
            task_id=task.task_id,
            ticket_id=task.ticket_id,
        )

        response = await self.client.post(
            f"{self.base_url}/api/v1/tasks",
            json=task.model_dump(),
        )
        response.raise_for_status()

        self.logger.info("task_assigned", task_id=task.task_id)
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("worker_agent.get_status")
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """
        Get task execution status.

        Args:
            task_id: Task identifier

        Returns:
            Task status
        """
        if not self.base_url or not self.client:
            raise ValueError("Worker endpoint not configured")

        response = await self.client.get(
            f"{self.base_url}/api/v1/tasks/{task_id}"
        )
        response.raise_for_status()

        return TaskStatus(**response.json())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("worker_agent.cancel_task")
    async def cancel_task(self, task_id: str) -> None:
        """
        Cancel task execution.

        Args:
            task_id: Task identifier
        """
        if not self.base_url or not self.client:
            raise ValueError("Worker endpoint not configured")

        self.logger.info("cancelling_task", task_id=task_id)

        response = await self.client.delete(
            f"{self.base_url}/api/v1/tasks/{task_id}"
        )
        response.raise_for_status()

        self.logger.info("task_cancelled", task_id=task_id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("worker_agent.health_check")
    async def health_check(self) -> bool:
        """
        Check if worker is healthy.

        Returns:
            True if healthy
        """
        if not self.base_url or not self.client:
            return False

        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            self.logger.warning("health_check_failed", error=str(e))
            return False
