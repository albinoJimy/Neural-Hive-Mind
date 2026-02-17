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


class ExecutionTicket(BaseModel):
    """Execution ticket data structure."""
    ticket_id: str
    plan_id: str
    task_type: str
    required_capabilities: List[str]
    payload: Dict[str, Any]
    sla_deadline: str
    priority: int = Field(ge=1, le=10)
    status: str = "pending"
    assigned_worker: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


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
        result: Optional[Dict[str, Any]] = None,
        assigned_worker: Optional[str] = None,
    ) -> ExecutionTicket:
        """
        Update ticket status and result.

        Args:
            ticket_id: Ticket identifier
            status: New status (pending, in_progress, completed, failed)
            result: Execution result
            assigned_worker: Worker ID if assigned

        Returns:
            Updated ticket
        """
        self.logger.info(
            "updating_ticket_status",
            ticket_id=ticket_id,
            status=status,
        )

        payload = {"status": status}
        if result:
            payload["result"] = result
        if assigned_worker:
            payload["assigned_worker"] = assigned_worker

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
