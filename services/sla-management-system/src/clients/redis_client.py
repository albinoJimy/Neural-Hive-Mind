"""
Cliente para Redis Cluster (cache de budgets).
"""

from typing import Optional
import json
import redis.asyncio as redis
import structlog

from ..config.settings import RedisSettings
from ..models.error_budget import ErrorBudget


class RedisClient:
    """Cliente para Redis Cluster."""

    def __init__(self, settings: RedisSettings):
        self.settings = settings
        self.cluster: Optional[redis.RedisCluster] = None
        self.ttl_seconds = settings.cache_ttl_seconds
        self.logger = structlog.get_logger(__name__)

    async def connect(self) -> None:
        """Inicializa conexão com Redis Cluster."""
        try:
            startup_nodes = [
                {"host": node.split(":")[0], "port": int(node.split(":")[1])}
                for node in self.settings.cluster_nodes
            ]

            self.cluster = redis.RedisCluster(
                startup_nodes=startup_nodes,
                password=self.settings.password if self.settings.password else None,
                ssl=self.settings.ssl,
                decode_responses=self.settings.decode_responses
            )

            await self.cluster.ping()
            self.logger.info("redis_connected", nodes=self.settings.cluster_nodes)
        except Exception as e:
            self.logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Fecha conexões."""
        if self.cluster:
            await self.cluster.close()
            self.logger.info("redis_disconnected")

    async def cache_budget(self, slo_id: str, budget: ErrorBudget) -> bool:
        """Armazena budget em cache."""
        try:
            key = f"sla:budget:{slo_id}"
            value = budget.model_dump_json()
            await self.cluster.setex(key, self.ttl_seconds, value)
            self.logger.debug("budget_cached", slo_id=slo_id)
            return True
        except Exception as e:
            self.logger.warning("budget_cache_failed", slo_id=slo_id, error=str(e))
            return False

    async def get_cached_budget(self, slo_id: str) -> Optional[ErrorBudget]:
        """Busca budget no cache."""
        try:
            key = f"sla:budget:{slo_id}"
            value = await self.cluster.get(key)
            if value:
                budget_data = json.loads(value)
                self.logger.debug("budget_cache_hit", slo_id=slo_id)
                return ErrorBudget(**budget_data)
            self.logger.debug("budget_cache_miss", slo_id=slo_id)
            return None
        except Exception as e:
            self.logger.warning("budget_cache_read_failed", slo_id=slo_id, error=str(e))
            return None

    async def invalidate_budget(self, slo_id: str) -> bool:
        """Remove budget do cache."""
        try:
            key = f"sla:budget:{slo_id}"
            await self.cluster.delete(key)
            self.logger.debug("budget_cache_invalidated", slo_id=slo_id)
            return True
        except Exception as e:
            self.logger.warning("budget_cache_invalidation_failed", slo_id=slo_id, error=str(e))
            return False

    async def cache_freeze_status(
        self,
        service_name: str,
        is_frozen: bool,
        ttl: Optional[int] = None
    ) -> bool:
        """Armazena status de freeze."""
        try:
            key = f"sla:freeze:{service_name}"
            value = "true" if is_frozen else "false"
            ttl_to_use = ttl if ttl is not None else self.ttl_seconds
            await self.cluster.setex(key, ttl_to_use, value)
            self.logger.debug("freeze_status_cached", service=service_name, frozen=is_frozen)
            return True
        except Exception as e:
            self.logger.warning("freeze_cache_failed", service=service_name, error=str(e))
            return False

    async def get_freeze_status(self, service_name: str) -> Optional[bool]:
        """Busca status de freeze no cache."""
        try:
            key = f"sla:freeze:{service_name}"
            value = await self.cluster.get(key)
            if value:
                return value == "true"
            return None
        except Exception as e:
            self.logger.warning("freeze_cache_read_failed", service=service_name, error=str(e))
            return None

    async def health_check(self) -> bool:
        """Verifica conectividade com Redis."""
        try:
            await self.cluster.ping()
            return True
        except Exception as e:
            self.logger.error("redis_health_check_failed", error=str(e))
            return False
