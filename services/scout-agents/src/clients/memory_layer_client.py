"""HTTP client for Memory Layer API"""
import asyncio
from typing import Optional, Dict, Any, List
import httpx
import structlog

from ..models.scout_signal import ScoutSignal
from neural_hive_domain import UnifiedDomain
from ..config import get_settings

logger = structlog.get_logger()


class MemoryLayerClient:
    """Client for interacting with Memory Layer API"""

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[httpx.AsyncClient] = None
        self.base_url = self.settings.memory_layer.api_url

    async def start(self):
        """Initialize HTTP client"""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.settings.memory_layer.timeout
        )
        logger.info("memory_layer_client_started", base_url=self.base_url)

    async def stop(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()
            logger.info("memory_layer_client_stopped")

    async def _retry_request(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        """Execute HTTP request with retry logic"""
        for attempt in range(self.settings.memory_layer.retry_attempts):
            try:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPError as e:
                logger.warning(
                    "memory_layer_request_failed",
                    method=method,
                    url=url,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt == self.settings.memory_layer.retry_attempts - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return None

    async def store_signal_redis(self, signal: ScoutSignal) -> bool:
        """
        Store signal in Redis (short-term memory)

        Args:
            signal: ScoutSignal instance

        Returns:
            bool: True if stored successfully
        """
        try:
            response = await self._retry_request(
                "POST",
                "/api/v1/memory/redis/scout-signals",
                json=signal.to_avro_dict()
            )

            if response and response.status_code == 201:
                logger.info(
                    "signal_stored_in_redis",
                    signal_id=signal.signal_id,
                    domain=signal.exploration_domain.value
                )
                return True

            return False

        except Exception as e:
            logger.error(
                "redis_storage_failed",
                signal_id=signal.signal_id,
                error=str(e)
            )
            return False

    async def store_signal_neo4j(self, signal: ScoutSignal) -> bool:
        """
        Store signal in Neo4j (long-term graph memory)

        Args:
            signal: ScoutSignal instance

        Returns:
            bool: True if stored successfully
        """
        try:
            response = await self._retry_request(
                "POST",
                "/api/v1/memory/neo4j/scout-signals",
                json=signal.to_avro_dict()
            )

            if response and response.status_code == 201:
                logger.info(
                    "signal_stored_in_neo4j",
                    signal_id=signal.signal_id,
                    domain=signal.exploration_domain.value
                )
                return True

            return False

        except Exception as e:
            logger.error(
                "neo4j_storage_failed",
                signal_id=signal.signal_id,
                error=str(e)
            )
            return False

    async def query_historical_signals(
        self,
        domain: Optional[UnifiedDomain] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query historical signals for pattern analysis

        Args:
            domain: Filter by exploration domain
            limit: Maximum number of signals to return

        Returns:
            List of signal dictionaries
        """
        try:
            params = {"limit": limit}
            if domain:
                params["domain"] = domain.value

            response = await self._retry_request(
                "GET",
                "/api/v1/memory/scout-signals",
                params=params
            )

            if response and response.status_code == 200:
                return response.json()

            return []

        except Exception as e:
            logger.error("historical_signals_query_failed", error=str(e))
            return []

    async def get_signal_by_id(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve specific signal by ID

        Args:
            signal_id: Signal identifier

        Returns:
            Signal dictionary or None
        """
        try:
            response = await self._retry_request(
                "GET",
                f"/api/v1/memory/scout-signals/{signal_id}"
            )

            if response and response.status_code == 200:
                return response.json()

            return None

        except Exception as e:
            logger.error(
                "signal_retrieval_failed",
                signal_id=signal_id,
                error=str(e)
            )
            return None

    async def update_signal_status(
        self,
        signal_id: str,
        status: str
    ) -> bool:
        """
        Update signal status (PENDING, VALIDATED, REJECTED)

        Args:
            signal_id: Signal identifier
            status: New status value

        Returns:
            bool: True if updated successfully
        """
        try:
            response = await self._retry_request(
                "PATCH",
                f"/api/v1/memory/scout-signals/{signal_id}/status",
                json={"status": status}
            )

            if response and response.status_code == 200:
                logger.info(
                    "signal_status_updated",
                    signal_id=signal_id,
                    status=status
                )
                return True

            return False

        except Exception as e:
            logger.error(
                "signal_status_update_failed",
                signal_id=signal_id,
                error=str(e)
            )
            return False
