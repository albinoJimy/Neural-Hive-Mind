"""Redis client for caching tool selections."""
import json
from typing import Dict, Optional

import structlog
from redis.asyncio import Redis

from src.models.tool_selection import ToolSelectionResponse

logger = structlog.get_logger()


class RedisClient:
    """Async Redis client for caching."""

    def __init__(self, redis_url: str, cache_ttl_seconds: int):
        """Initialize Redis client."""
        self.redis_url = redis_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.client: Optional[Redis] = None

    async def start(self):
        """Connect to Redis."""
        self.client = await Redis.from_url(self.redis_url, decode_responses=True)
        logger.info("redis_connected")

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
