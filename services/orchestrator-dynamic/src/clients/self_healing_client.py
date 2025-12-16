"""
Cliente HTTP para integração com Self-Healing Engine (Fluxo E).
"""
import asyncio
import time
from typing import Dict, Any, Optional

import httpx
import structlog
from uuid import uuid4

logger = structlog.get_logger()


class CircuitBreaker:
    """Circuit breaker simples para chamadas HTTP."""

    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.open_until = 0.0

    def record_success(self):
        self.failures = 0
        self.open_until = 0.0

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.open_until = time.time() + self.reset_timeout

    def is_open(self) -> bool:
        if self.open_until and time.time() < self.open_until:
            return True
        if self.open_until and time.time() >= self.open_until:
            self.failures = 0
            self.open_until = 0.0
        return False


class SelfHealingClient:
    """Cliente HTTP para comunicação com Self-Healing Engine."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        failure_threshold: int = 3,
        reset_timeout: int = 60
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(failure_threshold=failure_threshold, reset_timeout=reset_timeout)
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client:
            return self._client

        async with self._lock:
            if self._client:
                return self._client
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=50)
            )
            return self._client

    async def trigger_remediation(self, incident: Dict[str, Any]) -> Optional[str]:
        """Aciona remediação via Self-Healing Engine."""
        if self.circuit_breaker.is_open():
            logger.warning(
                "self_healing_client.circuit_open",
                base_url=self.base_url
            )
            return None

        remediation_id = incident.get("remediation_id") or str(uuid4())
        payload = {
            "remediation_id": remediation_id,
            "incident_id": incident.get("incident_id"),
            "playbook_name": incident.get("recommended_playbook"),
            "parameters": incident.get("parameters", {}),
            "execution_mode": incident.get("execution_mode", "AUTOMATIC")
        }

        try:
            client = await self._get_client()
            response = await client.post("/api/v1/remediation/execute", json=payload)
            response.raise_for_status()
            self.circuit_breaker.record_success()

            logger.info(
                "self_healing_client.remediation_triggered",
                remediation_id=remediation_id,
                playbook=payload.get("playbook_name")
            )
            return remediation_id
        except Exception as exc:  # noqa: BLE001
            self.circuit_breaker.record_failure()
            logger.warning(
                "self_healing_client.trigger_failed",
                remediation_id=remediation_id,
                error=str(exc)
            )
            return None

    async def get_remediation_status(self, remediation_id: str) -> Dict[str, Any]:
        """Consulta status de remediação (fail-open)."""
        if self.circuit_breaker.is_open():
            return {"remediation_id": remediation_id, "status": "circuit_open"}

        try:
            client = await self._get_client()
            response = await client.get(f"/api/v1/remediation/{remediation_id}/status")
            response.raise_for_status()
            self.circuit_breaker.record_success()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            self.circuit_breaker.record_failure()
            logger.warning(
                "self_healing_client.status_failed",
                remediation_id=remediation_id,
                error=str(exc)
            )
            return {"remediation_id": remediation_id, "status": "unknown", "error": str(exc)}

    async def close(self):
        """Fecha cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
