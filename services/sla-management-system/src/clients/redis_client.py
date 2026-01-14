"""
Cliente para Redis Cluster (cache de budgets).
"""

from typing import Optional, Union
import json
import redis.asyncio as redis
import structlog

from ..config.settings import RedisSettings
from ..models.error_budget import ErrorBudget
from ..observability.metrics import sla_metrics


class RedisClient:
    """Cliente para Redis Cluster."""

    def __init__(self, settings: RedisSettings):
        self.settings = settings
        self.cluster: Optional[Union[redis.RedisCluster, redis.Redis]] = None
        self.ttl_seconds = settings.cache_ttl_seconds
        self.logger = structlog.get_logger(__name__)

    async def connect(self) -> None:
        """Inicializa conexão com Redis (Standalone primeiro, Cluster como fallback)."""
        try:
            # Parse first node for connection (usando cluster_nodes_list property)
            nodes_list = self.settings.cluster_nodes_list
            first_node = nodes_list[0] if nodes_list else "localhost:6379"
            host, port_str = first_node.split(":")
            port = int(port_str)

            # Try standalone mode first (mais comum em desenvolvimento)
            try:
                self.cluster = redis.Redis(
                    host=host,
                    port=port,
                    password=self.settings.password if self.settings.password else None,
                    ssl=self.settings.ssl,
                    decode_responses=self.settings.decode_responses
                )
                await self.cluster.ping()
                self.logger.info("redis_standalone_connected", host=host, port=port)
            except Exception as standalone_error:
                # Fallback to cluster mode
                self.logger.warning(
                    "redis_standalone_unavailable_trying_cluster",
                    error=str(standalone_error)
                )
                try:
                    self.cluster = redis.RedisCluster(
                        host=host,
                        port=port,
                        password=self.settings.password if self.settings.password else None,
                        ssl=self.settings.ssl,
                        decode_responses=self.settings.decode_responses
                    )
                    await self.cluster.ping()
                    self.logger.info("redis_cluster_connected", nodes=nodes_list)
                except Exception as cluster_error:
                    self.logger.error("redis_cluster_also_failed", error=str(cluster_error))
                    raise
        except Exception as e:
            self.logger.error("redis_connection_failed", error=str(e))
            sla_metrics.record_redis_error()
            # Don't raise - allow service to start without Redis cache
            self.cluster = None

    async def disconnect(self) -> None:
        """Fecha conexões."""
        if self.cluster:
            await self.cluster.close()
            self.logger.info("redis_disconnected")

    async def cache_budget(self, slo_id: str, budget: ErrorBudget) -> bool:
        """Armazena budget em cache."""
        if not self.cluster:
            return False
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
        if not self.cluster:
            return None
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
        if not self.cluster:
            return False
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
        if not self.cluster:
            return False
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
        if not self.cluster:
            return None
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
        if not self.cluster:
            return False
        try:
            await self.cluster.ping()
            return True
        except Exception as e:
            self.logger.error("redis_health_check_failed", error=str(e))
            sla_metrics.record_redis_error()
            return False

    # Métodos para cache de histórico de budgets
    async def cache_budget_history(
        self,
        slo_id: str,
        days: int,
        aggregation: str,
        budgets_json: str,
        ttl: int = 300
    ) -> bool:
        """
        Armazena histórico de budgets em cache.

        Args:
            slo_id: ID do SLO
            days: Número de dias do histórico
            aggregation: Tipo de agregação (none, hourly, daily)
            budgets_json: JSON serializado dos budgets
            ttl: TTL em segundos (default: 300s = 5min)
        """
        if not self.cluster:
            return False
        try:
            agg_key = aggregation or "none"
            key = f"budget:history:{slo_id}:{days}:{agg_key}"
            await self.cluster.setex(key, ttl, budgets_json)
            self.logger.debug(
                "budget_history_cached",
                slo_id=slo_id,
                days=days,
                aggregation=agg_key
            )
            return True
        except Exception as e:
            self.logger.warning(
                "budget_history_cache_failed",
                slo_id=slo_id,
                error=str(e)
            )
            return False

    async def get_cached_budget_history(
        self,
        slo_id: str,
        days: int,
        aggregation: str
    ) -> Optional[str]:
        """
        Busca histórico de budgets no cache.

        Returns:
            JSON string dos budgets ou None se não encontrado
        """
        if not self.cluster:
            return None
        try:
            agg_key = aggregation or "none"
            key = f"budget:history:{slo_id}:{days}:{agg_key}"
            value = await self.cluster.get(key)
            if value:
                self.logger.debug(
                    "budget_history_cache_hit",
                    slo_id=slo_id,
                    days=days,
                    aggregation=agg_key
                )
                return value
            self.logger.debug(
                "budget_history_cache_miss",
                slo_id=slo_id,
                days=days,
                aggregation=agg_key
            )
            return None
        except Exception as e:
            self.logger.warning(
                "budget_history_cache_read_failed",
                slo_id=slo_id,
                error=str(e)
            )
            return None

    async def check_rate_limit(
        self,
        slo_id: str,
        limit: int = 10,
        window_seconds: int = 60
    ) -> tuple[bool, int]:
        """
        Verifica rate limit para queries de histórico por SLO.

        Args:
            slo_id: ID do SLO
            limit: Número máximo de requests na janela
            window_seconds: Tamanho da janela em segundos

        Returns:
            Tupla (permitido, requests_restantes)
        """
        if not self.cluster:
            # Se Redis não disponível, permitir (fail-open)
            return (True, limit)
        try:
            key = f"ratelimit:history:{slo_id}"
            current = await self.cluster.get(key)

            if current is None:
                # Primeiro request na janela
                await self.cluster.setex(key, window_seconds, "1")
                return (True, limit - 1)

            count = int(current)
            if count >= limit:
                self.logger.warning(
                    "rate_limit_exceeded",
                    slo_id=slo_id,
                    count=count,
                    limit=limit
                )
                return (False, 0)

            # Incrementar contador
            await self.cluster.incr(key)
            remaining = limit - count - 1
            return (True, remaining)

        except Exception as e:
            self.logger.warning(
                "rate_limit_check_failed",
                slo_id=slo_id,
                error=str(e)
            )
            # Fail-open: permitir se houver erro
            return (True, limit)
