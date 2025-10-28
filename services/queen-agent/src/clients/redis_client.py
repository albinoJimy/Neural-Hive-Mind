import json
import structlog
from redis.asyncio import Redis
from typing import Any, Dict, Optional

from ..config import Settings


logger = structlog.get_logger()


class RedisClient:
    """Cliente Redis assíncrono para cache e coordenação"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[Redis] = None

    async def initialize(self) -> None:
        """Conectar ao Redis Cluster"""
        try:
            # Parsear nodes do cluster
            nodes = self.settings.REDIS_CLUSTER_NODES.split(',')

            # Criar cliente Redis
            self.client = Redis(
                host=nodes[0].split(':')[0],
                port=int(nodes[0].split(':')[1]) if ':' in nodes[0] else 6379,
                password=self.settings.REDIS_PASSWORD if self.settings.REDIS_PASSWORD else None,
                ssl=self.settings.REDIS_SSL_ENABLED,
                decode_responses=True
            )

            # Testar conexão
            await self.client.ping()
            logger.info("redis_initialized")

        except Exception as e:
            logger.error("redis_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fechar conexão Redis"""
        if self.client:
            await self.client.close()
            logger.info("redis_closed")

    async def cache_strategic_context(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        """Cachear contexto estratégico"""
        try:
            await self.client.setex(
                key,
                ttl_seconds,
                json.dumps(data)
            )

            logger.debug("context_cached", key=key, ttl=ttl_seconds)

        except Exception as e:
            logger.error("context_cache_failed", key=key, error=str(e))

    async def get_cached_context(self, key: str) -> Optional[Dict[str, Any]]:
        """Recuperar contexto cacheado"""
        try:
            data = await self.client.get(key)
            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.error("context_get_failed", key=key, error=str(e))
            return None

    async def set_decision_lock(self, decision_type: str, ttl_seconds: int) -> bool:
        """Criar lock distribuído para evitar decisões concorrentes"""
        try:
            lock_key = f"decision:lock:{decision_type}"
            result = await self.client.set(lock_key, "1", nx=True, ex=ttl_seconds)
            return result is not None

        except Exception as e:
            logger.error("decision_lock_failed", decision_type=decision_type, error=str(e))
            return False

    async def release_decision_lock(self, decision_type: str) -> None:
        """Liberar lock de decisão"""
        try:
            lock_key = f"decision:lock:{decision_type}"
            await self.client.delete(lock_key)

        except Exception as e:
            logger.error("decision_lock_release_failed", decision_type=decision_type, error=str(e))

    async def increment_decision_counter(self, decision_type: str) -> int:
        """Incrementar contador de decisões por tipo"""
        try:
            counter_key = f"decision:counter:{decision_type}"
            count = await self.client.incr(counter_key)
            return count

        except Exception as e:
            logger.error("decision_counter_increment_failed", decision_type=decision_type, error=str(e))
            return 0

    async def get_decision_stats(self) -> Dict[str, int]:
        """Obter estatísticas de decisões"""
        try:
            stats = {}
            keys = await self.client.keys("decision:counter:*")

            for key in keys:
                decision_type = key.split(':')[-1]
                count = await self.client.get(key)
                stats[decision_type] = int(count) if count else 0

            return stats

        except Exception as e:
            logger.error("decision_stats_failed", error=str(e))
            return {}
