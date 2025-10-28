"""
Queen Agent client for strategic decision requests.
"""

import httpx
import structlog
from typing import Dict, Any, List
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class StrategicDecisionRequest(BaseModel):
    """Request for strategic decision."""
    context: Dict[str, Any]
    intent_id: str
    correlation_id: str


class StrategicDecision(BaseModel):
    """Strategic decision response."""
    decision_id: str
    decision_type: str
    recommended_actions: List[Dict[str, Any]]
    reasoning: str
    confidence: float
    risk_assessment: Dict[str, Any]


class QueenAgentClient:
    """Client for Queen Agent service."""

    def __init__(
        self,
        base_url: str = "http://queen-agent.neural-hive-orchestration:8000",
        timeout: int = 30,
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout)
        self.logger = logger.bind(service="queen_agent_client")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("queen_agent.request_decision")
    async def request_strategic_decision(
        self,
        context: Dict[str, Any],
        intent_id: str,
        correlation_id: str,
    ) -> StrategicDecision:
        """
        Request strategic decision from Queen Agent.

        Args:
            context: Decision context
            intent_id: Related intent ID
            correlation_id: Correlation ID

        Returns:
            Strategic decision
        """
        request = StrategicDecisionRequest(
            context=context,
            intent_id=intent_id,
            correlation_id=correlation_id,
        )

        self.logger.info(
            "requesting_strategic_decision",
            intent_id=intent_id,
            correlation_id=correlation_id,
        )

        response = await self.client.post(
            f"{self.base_url}/api/v1/decisions",
            json=request.model_dump(),
            headers={"X-Correlation-ID": correlation_id},
        )
        response.raise_for_status()

        decision = StrategicDecision(**response.json())
        self.logger.info("decision_received", decision_id=decision.decision_id)
        return decision

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("queen_agent.report_status")
    async def report_execution_status(
        self,
        plan_id: str,
        status: str,
        metrics: Dict[str, Any],
    ) -> None:
        """
        Report execution status to Queen Agent.

        Args:
            plan_id: Plan identifier
            status: Execution status
            metrics: Execution metrics
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/plans/{plan_id}/status",
            json={"status": status, "metrics": metrics},
        )
        response.raise_for_status()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("queen_agent.request_replanning")
    async def request_replanning(
        self,
        plan_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Request plan revision.

        Args:
            plan_id: Plan identifier
            reason: Replanning reason

        Returns:
            New plan or replanning decision
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/plans/{plan_id}/replan",
            json={"reason": reason},
        )
        response.raise_for_status()

        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("queen_agent.get_priorities")
    async def get_priorities(self) -> List[Dict[str, Any]]:
        """
        Get current strategic priorities.

        Returns:
            List of priorities
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/priorities"
        )
        response.raise_for_status()

        return response.json()
