"""
Redis Client for caching queries and short-term context

Provides async interface to Redis Cluster or standalone Redis for high-performance caching.
"""

import json
import structlog
from typing import Dict, Optional, Union
from redis.asyncio import Redis, RedisCluster
from redis.exceptions import RedisError

from src.config.settings import Settings

logger = structlog.get_logger()


class RedisClient:
    """Async Redis client for caching operations"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[Union[Redis, RedisCluster]] = None

    async def initialize(self):
        """Initialize Redis client (cluster or standalone)"""
        if self.settings.redis_cluster_enabled:
            # Try cluster mode first
            try:
                startup_nodes = [
                    {"host": node.split(':')[0], "port": int(node.split(':')[1])}
                    for node in self.settings.redis_cluster_nodes.split(',')
                ]

                self.client = RedisCluster(
                    startup_nodes=startup_nodes,
                    password=self.settings.redis_password,
                    ssl=self.settings.redis_ssl_enabled,
                    decode_responses=True
                )

                # Verify connectivity
                await self.client.ping()

                logger.info(
                    'Redis cluster client inicializado',
                    nodes=self.settings.redis_cluster_nodes,
                    ssl=self.settings.redis_ssl_enabled
                )
                return

            except RedisError as e:
                logger.warning(
                    'Redis cluster initialization failed, falling back to standalone',
                    error=str(e)
                )

        # Standalone mode or fallback
        nodes = self.settings.redis_cluster_nodes.split(',')
        first_node = nodes[0]
        host = first_node.split(':')[0]
        port = int(first_node.split(':')[1])

        self.client = Redis(
            host=host,
            port=port,
            password=self.settings.redis_password,
            ssl=self.settings.redis_ssl_enabled,
            decode_responses=True
        )

        # Verify connectivity
        await self.client.ping()

        logger.info(
            'Redis standalone client inicializado',
            host=host,
            port=port,
            ssl=self.settings.redis_ssl_enabled
        )

    async def get_cached_query(self, query_key: str) -> Optional[Dict]:
        """
        Get cached query result

        Args:
            query_key: Cache key

        Returns:
            Cached result or None
        """
        if not self.settings.redis_cache_enabled:
            return None

        try:
            value = await self.client.get(query_key)
            if value:
                logger.debug('Cache hit', key=query_key)
                return json.loads(value)
            else:
                logger.debug('Cache miss', key=query_key)
                return None

        except RedisError as e:
            logger.warning('Redis get error', key=query_key, error=str(e))
            return None

    async def cache_query_result(
        self,
        query_key: str,
        result: Dict,
        ttl: Optional[int] = None
    ):
        """
        Cache query result

        Args:
            query_key: Cache key
            result: Result to cache
            ttl: Time to live in seconds (defaults to config value)
        """
        if not self.settings.redis_cache_enabled:
            return

        ttl = ttl or self.settings.redis_default_ttl

        try:
            value = json.dumps(result, default=str)
            await self.client.setex(query_key, ttl, value)

            logger.debug('Query cached', key=query_key, ttl=ttl)

        except RedisError as e:
            logger.warning('Redis set error', key=query_key, error=str(e))

    async def get_enriched_context(self, intent_id: str) -> Optional[Dict]:
        """
        Get enriched context for intent

        Args:
            intent_id: Intent identifier

        Returns:
            Enriched context or None
        """
        key = f'context:enriched:{intent_id}'
        return await self.get_cached_query(key)

    async def cache_enriched_context(
        self,
        intent_id: str,
        context: Dict,
        ttl: int = 300
    ):
        """
        Cache enriched context

        Args:
            intent_id: Intent identifier
            context: Context data
            ttl: Time to live (default 5 minutes)
        """
        key = f'context:enriched:{intent_id}'
        await self.cache_query_result(key, context, ttl)

    async def invalidate_cache(self, pattern: str):
        """
        Invalidate cache entries matching pattern

        Args:
            pattern: Key pattern (supports wildcards)
        """
        try:
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )

                if keys:
                    await self.client.delete(*keys)
                    deleted += len(keys)

                if cursor == 0:
                    break

            logger.info('Cache invalidated', pattern=pattern, deleted=deleted)

        except RedisError as e:
            logger.warning('Redis invalidate error', pattern=pattern, error=str(e))

    async def close(self):
        """Close Redis client"""
        if self.client:
            await self.client.close()
            logger.info('Redis client fechado')
