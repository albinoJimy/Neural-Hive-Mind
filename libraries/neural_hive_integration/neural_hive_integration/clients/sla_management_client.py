"""
SLA Management System client for SLO definitions and error budget tracking.
"""

import httpx
import structlog
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel
import redis.asyncio as aioredis
import json

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class SLODefinition(BaseModel):
    """SLO definition."""
    service_name: str
    slo_type: str  # latency, availability, throughput
    target: float
    window: str
    error_budget: float


class ErrorBudgetStatus(BaseModel):
    """Error budget status."""
    service_name: str
    remaining_budget: float
    burn_rate: float
    is_exhausted: bool
    freeze_recommended: bool


class SLAManagementClient:
    """Client for SLA Management System."""

    def __init__(
        self,
        base_url: str = "http://sla-management-system.neural-hive-orchestration:8000",
        redis_url: str = "redis://redis.neural-hive-storage:6379",
        cache_ttl: int = 300,  # 5 minutes
        timeout: int = 30,
    ):
        self.base_url = base_url
        self.redis_url = redis_url
        self.cache_ttl = cache_ttl
        self.client = httpx.AsyncClient(timeout=timeout)
        self.redis: Optional[aioredis.Redis] = None
        self.logger = logger.bind(service="sla_management_client")

    async def initialize(self):
        """Initialize Redis connection."""
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)

    async def close(self):
        """Close HTTP and Redis clients."""
        await self.client.aclose()
        if self.redis:
            await self.redis.close()

    async def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from Redis cache."""
        if not self.redis:
            return None

        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None

    async def _set_to_cache(self, key: str, value: Dict[str, Any]):
        """Set value to Redis cache with TTL."""
        if not self.redis:
            return

        await self.redis.setex(key, self.cache_ttl, json.dumps(value))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("sla_management.get_slo")
    async def get_slo_definition(self, service_name: str) -> SLODefinition:
        """
        Get SLO definition for service.

        Args:
            service_name: Service identifier

        Returns:
            SLO definition
        """
        cache_key = f"slo:{service_name}"
        cached = await self._get_from_cache(cache_key)
        if cached:
            return SLODefinition(**cached)

        response = await self.client.get(
            f"{self.base_url}/api/v1/slo/{service_name}"
        )
        response.raise_for_status()

        data = response.json()
        await self._set_to_cache(cache_key, data)

        return SLODefinition(**data)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("sla_management.check_error_budget")
    async def check_error_budget(self, service_name: str) -> ErrorBudgetStatus:
        """
        Check error budget status.

        Args:
            service_name: Service identifier

        Returns:
            Error budget status
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/error-budget/{service_name}"
        )
        response.raise_for_status()

        status = ErrorBudgetStatus(**response.json())

        # Alert if budget < 10%
        if status.remaining_budget < 0.10:
            self.logger.warning(
                "error_budget_critical",
                service_name=service_name,
                remaining_budget=status.remaining_budget,
            )

        return status

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("sla_management.report_sli")
    async def report_sli(
        self,
        service_name: str,
        metric: str,
        value: float,
    ) -> None:
        """
        Report SLI metric value.

        Args:
            service_name: Service identifier
            metric: Metric name (latency_p95, availability, etc.)
            value: Metric value
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/sli/{service_name}",
            json={"metric": metric, "value": value},
        )
        response.raise_for_status()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    @tracer.start_as_current_span("sla_management.check_freeze_policy")
    async def check_freeze_policy(self) -> bool:
        """
        Check if change freeze is active.

        Returns:
            True if freeze is active
        """
        response = await self.client.get(
            f"{self.base_url}/api/v1/freeze-policy"
        )
        response.raise_for_status()

        return response.json()["freeze_active"]
