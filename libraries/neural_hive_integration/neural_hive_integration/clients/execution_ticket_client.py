"""
Execution Ticket Service client for ticket lifecycle management.
"""

import os
import httpx
import structlog
from typing import Dict, Any, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field
from datetime import datetime

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

# Default URL - can be overridden via EXECUTION_TICKET_SERVICE_URL env var
DEFAULT_EXECUTION_TICKET_URL = os.getenv(
    "EXECUTION_TICKET_SERVICE_URL",
    "http://execution-ticket-service.neural-hive.svc.cluster.local:8000"
)


class SLA(BaseModel):
    """SLA configuration for the ticket."""
    deadline: int
    timeout_ms: int
    max_retries: int


class QoS(BaseModel):
    """Quality of Service settings."""
    delivery_mode: str
    consistency: str
    durability: str


class AllocationMetadata(BaseModel):
    """Resource allocation metadata."""
    agent_id: str
    agent_type: str
    agent_score: float
    composite_score: float
    ml_enriched: bool
    predicted_load_pct: float
    predicted_queue_ms: int
    priority_score: float
    workers_evaluated: int
    allocated_at: int
    allocation_method: str
    predicted_duration_ms: Optional[int] = None


class RejectionMetadata(BaseModel):
    """Ticket rejection information."""
    allocation_method: str
    namespace: str
    rejected_at: int
    rejection_reason: str
    rejection_message: str
    required_capabilities: List[str]


class Predictions(BaseModel):
    """ML predictions for ticket execution."""
    anomaly: Optional[Dict[str, Any]] = None
    duration_confidence: float
    duration_ms: float
    resource_estimate: Optional[Dict[str, float]] = None


class ExecutionTicket(BaseModel):
    """Execution ticket data structure - matches execution-ticket-service API schema."""
    ticket_id: str
    plan_id: str
    intent_id: str
    decision_id: str
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    task_id: str
    task_type: str
    description: str
    dependencies: List[str]
    status: str
    priority: str  # "NORMAL", "HIGH", "LOW"
    risk_band: str
    sla: SLA
    qos: QoS
    parameters: Dict[str, Any]
    required_capabilities: List[str]
    security_level: str
    created_at: int  # Unix timestamp
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    estimated_duration_ms: int
    actual_duration_ms: Optional[int] = None
    retry_count: int
    error_message: Optional[str] = None
    compensation_ticket_id: Optional[str] = None
    metadata: Dict[str, Any]
    predictions: Optional[Predictions] = None
    allocation_metadata: Optional[AllocationMetadata] = None
    rejection_metadata: Optional[RejectionMetadata] = None
    schema_version: int

    # Computed property for backward compatibility
    @property
    def sla_deadline(self) -> int:
        """Return SLA deadline for backward compatibility."""
        return self.sla.deadline

    @property
    def payload(self) -> Dict[str, Any]:
        """Return parameters for backward compatibility."""
        return self.parameters


class ExecutionTicketClient:
    """Client for Execution Ticket Service."""

    def __init__(
        self,
        base_url: str = DEFAULT_EXECUTION_TICKET_URL,
        timeout: int = 30,
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout)
        self.logger = logger.bind(service="execution_ticket_client")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("execution_ticket.create")
    async def create_ticket(self, ticket_data: Dict[str, Any]) -> ExecutionTicket:
        """
        Create new execution ticket.

        Args:
            ticket_data: Ticket payload

        Returns:
            Created ticket
        """
        self.logger.info(
            "creating_ticket",
            plan_id=ticket_data.get("plan_id"),
            task_type=ticket_data.get("task_type"),
        )

        response = await self.client.post(
            f"{self.base_url}/api/v1/tickets/",
            json=ticket_data,
        )
        response.raise_for_status()

        ticket = ExecutionTicket(**response.json())
        self.logger.info("ticket_created", ticket_id=ticket.ticket_id)
        return ticket

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("execution_ticket.get")
    async def get_ticket(self, ticket_id: str) -> ExecutionTicket:
        """
        Get ticket by ID.

        Args:
            ticket_id: Ticket identifier

        Returns:
            Ticket data
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/tickets/{ticket_id}"
        )
        response.raise_for_status()

        return ExecutionTicket(**response.json())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("execution_ticket.update_status")
    async def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        started_at: Optional[int] = None,
        completed_at: Optional[int] = None,
        actual_duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> ExecutionTicket:
        """
        Update ticket status and execution metadata.

        Args:
            ticket_id: Ticket identifier
            status: New status (PENDING, RUNNING, COMPLETED, FAILED, REJECTED)
            started_at: Unix timestamp when execution started
            completed_at: Unix timestamp when execution completed
            actual_duration_ms: Actual execution duration in milliseconds
            error_message: Error message if execution failed

        Returns:
            Updated ticket
        """
        self.logger.info(
            "updating_ticket_status",
            ticket_id=ticket_id,
            status=status,
        )

        payload: Dict[str, Any] = {"status": status}
        if started_at is not None:
            payload["started_at"] = started_at
        if completed_at is not None:
            payload["completed_at"] = completed_at
        if actual_duration_ms is not None:
            payload["actual_duration_ms"] = actual_duration_ms
        if error_message is not None:
            payload["error_message"] = error_message

        response = await self.client.patch(
            f"{self.base_url}/api/v1/tickets/{ticket_id}",
            json=payload,
        )
        response.raise_for_status()

        return ExecutionTicket(**response.json())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("execution_ticket.list_by_plan")
    async def list_tickets_by_plan(self, plan_id: str) -> List[ExecutionTicket]:
        """
        List all tickets for a plan.

        Args:
            plan_id: Plan identifier

        Returns:
            List of tickets
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/tickets/",
            params={"plan_id": plan_id},
        )
        response.raise_for_status()

        tickets = [ExecutionTicket(**t) for t in response.json()]
        return tickets

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("execution_ticket.generate_token")
    async def generate_token(self, ticket_id: str) -> str:
        """
        Generate access token for ticket execution.

        Args:
            ticket_id: Ticket identifier

        Returns:
            JWT token
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/tickets/{ticket_id}/token"
        )
        response.raise_for_status()

        return response.json()["token"]
