import redis.asyncio as redis
import structlog
import json
from typing import List, Dict, Optional
from ..models.insight import AnalystInsight

logger = structlog.get_logger()


class RedisClient:
    def __init__(self, host: str, port: int, password: Optional[str], db: int, ttl: int):
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.default_ttl = ttl
        self.client = None

    async def initialize(self):
        """Conectar ao Redis"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True
            )
            await self.client.ping()
            logger.info('redis_client_initialized', host=self.host)
        except Exception as e:
            logger.error('redis_client_initialization_failed', error=str(e))
            raise

    async def close(self):
        """Fechar conexão"""
        if self.client:
            await self.client.close()
            logger.info('redis_client_closed')

    async def cache_insight(self, insight: AnalystInsight, ttl: Optional[int] = None) -> bool:
        """Cachear insight com TTL"""
        try:
            key = f'insight:{insight.insight_id}'
            value = insight.model_dump_json()
            cache_ttl = ttl or self.default_ttl
            await self.client.setex(key, cache_ttl, value)
            logger.debug('insight_cached', insight_id=insight.insight_id, ttl=cache_ttl)
            return True
        except Exception as e:
            logger.error('cache_insight_failed', error=str(e), insight_id=insight.insight_id)
            return False

    async def get_cached_insight(self, insight_id: str) -> Optional[dict]:
        """Buscar insight no cache"""
        try:
            key = f'insight:{insight_id}'
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error('get_cached_insight_failed', error=str(e), insight_id=insight_id)
            return None

    async def invalidate_insight(self, insight_id: str) -> bool:
        """Invalidar cache de insight"""
        try:
            key = f'insight:{insight_id}'
            result = await self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error('invalidate_insight_failed', error=str(e), insight_id=insight_id)
            return False

    async def cache_query_result(self, query_key: str, results: List[dict], ttl: Optional[int] = None) -> bool:
        """Cachear resultado de consulta"""
        try:
            key = f'insight:query:{query_key}'
            value = json.dumps(results)
            cache_ttl = ttl or self.default_ttl
            await self.client.setex(key, cache_ttl, value)
            logger.debug('query_result_cached', query_key=query_key, count=len(results))
            return True
        except Exception as e:
            logger.error('cache_query_result_failed', error=str(e))
            return False

    async def get_cached_query_result(self, query_key: str) -> Optional[List[dict]]:
        """Buscar resultado de consulta no cache"""
        try:
            key = f'insight:query:{query_key}'
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error('get_cached_query_result_failed', error=str(e))
            return None

    async def invalidate_query_cache(self, pattern: str = 'insight:query:*') -> int:
        """Invalidar cache de consultas por padrão"""
        try:
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                deleted = await self.client.delete(*keys)
                logger.info('query_cache_invalidated', count=deleted)
                return deleted
            return 0
        except Exception as e:
            logger.error('invalidate_query_cache_failed', error=str(e))
            return 0

    async def increment_insight_access_count(self, insight_id: str) -> int:
        """Incrementar contador de acessos"""
        try:
            key = f'insight:access:{insight_id}'
            count = await self.client.incr(key)
            await self.client.expire(key, 86400)  # 24 horas
            return count
        except Exception as e:
            logger.error('increment_access_count_failed', error=str(e))
            return 0

    async def get_insight_access_count(self, insight_id: str) -> int:
        """Obter contador de acessos"""
        try:
            key = f'insight:access:{insight_id}'
            count = await self.client.get(key)
            return int(count) if count else 0
        except Exception as e:
            logger.error('get_access_count_failed', error=str(e))
            return 0

    async def set_insight_metadata(self, insight_id: str, metadata: dict, ttl: Optional[int] = None) -> bool:
        """Armazenar metadados temporários"""
        try:
            key = f'insight:meta:{insight_id}'
            value = json.dumps(metadata)
            cache_ttl = ttl or self.default_ttl
            await self.client.setex(key, cache_ttl, value)
            return True
        except Exception as e:
            logger.error('set_insight_metadata_failed', error=str(e))
            return False
