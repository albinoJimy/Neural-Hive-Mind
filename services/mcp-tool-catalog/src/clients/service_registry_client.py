"""Service Registry client for service discovery."""
from typing import Dict, List

import httpx
import structlog

logger = structlog.get_logger()


class ServiceRegistryClient:
    """Client for Service Registry integration."""

    def __init__(self, host: str, port: int):
        """Initialize Service Registry client."""
        self.base_url = f"http://{host}:{port}"
        self.service_id: str = None

    async def register(self, service_name: str, capabilities: List[str], metadata: Dict):
        """Register service with Service Registry."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/services/register",
                json={
                    "service_name": service_name,
                    "capabilities": capabilities,
                    "metadata": metadata,
                },
            )
            response.raise_for_status()
            self.service_id = response.json()["service_id"]
            logger.info("service_registered", service_id=self.service_id)

    async def send_heartbeat(self, health_data: Dict):
        """Send heartbeat to Service Registry."""
        if not self.service_id:
            return

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.base_url}/api/v1/services/{self.service_id}/heartbeat",
                json=health_data,
            )

    async def deregister(self):
        """Deregister service from Service Registry."""
        if not self.service_id:
            return

        async with httpx.AsyncClient() as client:
            await client.delete(f"{self.base_url}/api/v1/services/{self.service_id}")
            logger.info("service_deregistered", service_id=self.service_id)
