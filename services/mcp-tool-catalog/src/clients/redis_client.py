"""Redis client for caching tool selections."""
import asyncio
import json
from typing import Dict, Optional

import structlog
from redis.asyncio import Redis

from src.models.tool_selection import ToolSelectionResponse

logger = structlog.get_logger()


class RedisClient:
    """Async Redis client for caching."""

    def __init__(
        self,
        redis_url: str,
        cache_ttl_seconds: int,
        socket_timeout_seconds: float = 10.0,
        connect_timeout_seconds: float = 10.0,
    ):
        """Initialize Redis client.

        Args:
            redis_url: Redis connection URL
            cache_ttl_seconds: Cache TTL in seconds
            socket_timeout_seconds: Socket timeout in seconds
            connect_timeout_seconds: Connection timeout in seconds
        """
        self.redis_url = redis_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.socket_timeout_seconds = socket_timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.client: Optional[Redis] = None

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """Connect to Redis with retry logic.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay between retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "connecting_to_redis",
                    url=self.redis_url,
                    attempt=attempt + 1,
                )

                self.client = await Redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=self.socket_timeout_seconds,
                    socket_connect_timeout=self.connect_timeout_seconds,
                )

                # Test connection
                await self.client.ping()

                logger.info("redis_connected")
                return

            except Exception as e:
                delay = initial_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    "redis_connection_failed",
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("redis_connection_exhausted_retries")
                    raise

    async def stop(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("redis_disconnected")

    async def cache_selection(self, request_hash: str, response: ToolSelectionResponse):
        """Cache selection response."""
        key = f"mcp:selection:{request_hash}"
        await self.client.setex(key, self.cache_ttl_seconds, json.dumps(response.to_avro()))

    async def get_cached_selection(self, request_hash: str) -> Optional[Dict]:
        """Get cached selection."""
        key = f"mcp:selection:{request_hash}"
        cached = await self.client.get(key)
        return json.loads(cached) if cached else None

    async def invalidate_cache(self, pattern: str):
        """Invalidate cache by pattern."""
        async for key in self.client.scan_iter(match=pattern):
            await self.client.delete(key)

    async def increment_tool_usage(self, tool_id: str) -> int:
        """Increment tool usage counter."""
        key = f"mcp:tool:usage:{tool_id}"
        return await self.client.incr(key)

    async def get_tool_usage(self, tool_id: str) -> int:
        """Get tool usage count."""
        key = f"mcp:tool:usage:{tool_id}"
        count = await self.client.get(key)
        return int(count) if count else 0

    async def set_tool_health(self, tool_id: str, healthy: bool, ttl: int = 300):
        """Mark tool health status."""
        key = f"mcp:tool:health:{tool_id}"
        await self.client.setex(key, ttl, "1" if healthy else "0")

    async def get_tool_health(self, tool_id: str) -> Optional[bool]:
        """Get tool health status."""
        key = f"mcp:tool:health:{tool_id}"
        health = await self.client.get(key)
        return health == "1" if health else None

    async def increment_tool_feedback(self, tool_id: str, success: bool) -> int:
        """Incrementa contadores de feedback de ferramentas."""
        key = f"mcp:tool:feedback:{'success' if success else 'failure'}:{tool_id}"
        return await self.client.incr(key)
