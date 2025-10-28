from typing import Dict, Optional

import structlog
from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster

from src.config.settings import get_settings

logger = structlog.get_logger()


class RedisClient:
    """Cliente Redis para cache de métricas e estado de otimizações."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.client: Optional[Redis] = None

    async def connect(self):
        """Estabelecer conexão Redis Cluster."""
        try:
            # Parse cluster nodes
            nodes = self.settings.redis_cluster_nodes.split(",")
            startup_nodes = []
            for node in nodes:
                host, port = node.strip().split(":")
                startup_nodes.append({"host": host, "port": int(port)})

            self.client = RedisCluster(
                startup_nodes=startup_nodes,
                decode_responses=True,
                password=self.settings.redis_password if self.settings.redis_password else None,
                ssl=self.settings.redis_ssl_enabled,
            )

            # Test connection
            await self.client.ping()

            logger.info("redis_connected", nodes=len(startup_nodes))
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Fechar conexão Redis."""
        if self.client:
            await self.client.close()
            logger.info("redis_disconnected")

    async def cache_metrics(self, component: str, metrics: Dict[str, float], ttl: int = 300):
        """Cachear métricas de componente."""
        try:
            key = f"optimizer:metrics:{component}"

            # Serializar métricas como hash
            await self.client.hset(key, mapping={k: str(v) for k, v in metrics.items()})
            await self.client.expire(key, ttl)

            logger.debug("metrics_cached", component=component, count=len(metrics))
        except Exception as e:
            logger.error("metrics_cache_failed", component=component, error=str(e))

    async def get_cached_metrics(self, component: str) -> Optional[Dict[str, float]]:
        """Recuperar métricas cacheadas."""
        try:
            key = f"optimizer:metrics:{component}"
            data = await self.client.hgetall(key)

            if data:
                # Converter strings para floats
                metrics = {k: float(v) for k, v in data.items()}
                logger.debug("metrics_retrieved", component=component, count=len(metrics))
                return metrics

            return None
        except Exception as e:
            logger.error("metrics_retrieval_failed", component=component, error=str(e))
            return None

    async def cache_optimization_state(self, optimization_id: str, state: Dict, ttl: int = 3600):
        """Cachear estado de otimização em andamento."""
        try:
            key = f"optimizer:state:{optimization_id}"

            # Serializar estado como hash
            await self.client.hset(key, mapping={k: str(v) for k, v in state.items()})
            await self.client.expire(key, ttl)

            logger.debug("optimization_state_cached", optimization_id=optimization_id)
        except Exception as e:
            logger.error("optimization_state_cache_failed", optimization_id=optimization_id, error=str(e))

    async def get_optimization_state(self, optimization_id: str) -> Optional[Dict]:
        """Recuperar estado de otimização."""
        try:
            key = f"optimizer:state:{optimization_id}"
            data = await self.client.hgetall(key)

            if data:
                logger.debug("optimization_state_retrieved", optimization_id=optimization_id)
                return data

            return None
        except Exception as e:
            logger.error("optimization_state_retrieval_failed", optimization_id=optimization_id, error=str(e))
            return None

    async def lock_component(self, component: str, ttl: int = 60) -> bool:
        """Adquirir lock distribuído para evitar otimizações concorrentes."""
        try:
            key = f"optimizer:lock:{component}"
            # SET NX (only if not exists) com TTL
            locked = await self.client.set(key, "locked", nx=True, ex=ttl)

            if locked:
                logger.info("component_locked", component=component, ttl=ttl)
                return True
            else:
                logger.warning("component_already_locked", component=component)
                return False
        except Exception as e:
            logger.error("component_lock_failed", component=component, error=str(e))
            return False

    async def unlock_component(self, component: str):
        """Liberar lock distribuído."""
        try:
            key = f"optimizer:lock:{component}"
            await self.client.delete(key)
            logger.info("component_unlocked", component=component)
        except Exception as e:
            logger.error("component_unlock_failed", component=component, error=str(e))

    async def increment_counter(self, key: str, amount: int = 1) -> int:
        """Incrementar contador."""
        try:
            full_key = f"optimizer:counter:{key}"
            new_value = await self.client.incrby(full_key, amount)
            logger.debug("counter_incremented", key=key, value=new_value)
            return new_value
        except Exception as e:
            logger.error("counter_increment_failed", key=key, error=str(e))
            return 0

    async def get_counter(self, key: str) -> int:
        """Obter valor de contador."""
        try:
            full_key = f"optimizer:counter:{key}"
            value = await self.client.get(full_key)
            return int(value) if value else 0
        except Exception as e:
            logger.error("counter_get_failed", key=key, error=str(e))
            return 0

    async def set_metadata(self, optimization_id: str, key: str, value: str, ttl: int = 86400):
        """Definir metadados de otimização."""
        try:
            full_key = f"optimizer:metadata:{optimization_id}:{key}"
            await self.client.set(full_key, value, ex=ttl)
            logger.debug("metadata_set", optimization_id=optimization_id, key=key)
        except Exception as e:
            logger.error("metadata_set_failed", optimization_id=optimization_id, key=key, error=str(e))

    async def get_metadata(self, optimization_id: str, key: str) -> Optional[str]:
        """Obter metadados de otimização."""
        try:
            full_key = f"optimizer:metadata:{optimization_id}:{key}"
            value = await self.client.get(full_key)
            return value
        except Exception as e:
            logger.error("metadata_get_failed", optimization_id=optimization_id, key=key, error=str(e))
            return None
