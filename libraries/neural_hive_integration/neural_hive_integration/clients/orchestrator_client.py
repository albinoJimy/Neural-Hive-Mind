"""
Orchestrator Dynamic client for starting and managing Temporal workflows.
"""

import httpx
import structlog
from typing import Any, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class WorkflowStartRequest(BaseModel):
    """Request to start a workflow."""
    cognitive_plan: Dict[str, Any]
    correlation_id: str
    priority: int = Field(default=5, ge=1, le=10)
    sla_deadline_seconds: int = Field(default=14400)  # 4 hours


class WorkflowStatus(BaseModel):
    """Workflow status response."""
    workflow_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class OrchestratorClient:
    """Client for Orchestrator Dynamic service."""

    def __init__(
        self,
        base_url: str = "http://orchestrator-dynamic.neural-hive-orchestration:8000",
        timeout: int = 30,
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout)
        self.logger = logger.bind(service="orchestrator_client")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("orchestrator.start_workflow")
    async def start_workflow(
        self,
        cognitive_plan: Dict[str, Any],
        correlation_id: str,
        priority: int = 5,
        sla_deadline_seconds: int = 14400,
    ) -> str:
        """
        Start a new orchestration workflow.

        Args:
            cognitive_plan: Cognitive plan data structure
            correlation_id: Correlation ID for tracing
            priority: Workflow priority (1-10)
            sla_deadline_seconds: SLA deadline in seconds

        Returns:
            Workflow ID

        Raises:
            httpx.HTTPError: On HTTP errors
        """
        request = WorkflowStartRequest(
            cognitive_plan=cognitive_plan,
            correlation_id=correlation_id,
            priority=priority,
            sla_deadline_seconds=sla_deadline_seconds,
        )

        self.logger.info(
            "starting_workflow",
            correlation_id=correlation_id,
            priority=priority,
        )

        response = await self.client.post(
            f"{self.base_url}/api/v1/workflows/start",
            json=request.model_dump(),
            headers={"X-Correlation-ID": correlation_id},
        )
        response.raise_for_status()

        data = response.json()
        workflow_id = data["workflow_id"]

        self.logger.info("workflow_started", workflow_id=workflow_id)
        return workflow_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("orchestrator.get_workflow_status")
    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        """
        Get workflow status.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow status
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/workflows/{workflow_id}/status"
        )
        response.raise_for_status()

        return WorkflowStatus(**response.json())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("orchestrator.signal_workflow")
    async def signal_workflow(
        self,
        workflow_id: str,
        signal_name: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Send signal to workflow.

        Args:
            workflow_id: Workflow identifier
            signal_name: Signal name
            data: Signal payload
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/workflows/{workflow_id}/signal",
            json={"signal_name": signal_name, "data": data},
        )
        response.raise_for_status()

        self.logger.info("workflow_signaled", workflow_id=workflow_id, signal=signal_name)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("orchestrator.query_workflow")
    async def query_workflow(
        self,
        workflow_id: str,
        query_name: str,
    ) -> Dict[str, Any]:
        """
        Query workflow state.

        Args:
            workflow_id: Workflow identifier
            query_name: Query name

        Returns:
            Query result
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/workflows/{workflow_id}/query",
            json={"query_name": query_name},
        )
        response.raise_for_status()

        return response.json()
