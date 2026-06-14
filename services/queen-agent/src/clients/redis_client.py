import json
from typing import Any

import structlog
from redis.asyncio.cluster import ClusterNode, RedisCluster

from src.config import Settings

logger = structlog.get_logger()


class RedisClient:
    """Cliente Redis Cluster assíncrono para cache e coordenação.

    Usa `redis.asyncio.cluster.RedisCluster` para suportar os 16384 slots
    distribuídos pelos master nodes do cluster. Trata automaticamente os
    redirects `MOVED` e `ASK` no transporte — uma chave hasheada para um
    slot não-local é re-encaminhada sem expor erro `CLUSTERDOWN` ao caller.

    Background TR-1 (spec 2026-05-22-pipeline-flow-recovery): a versão
    anterior usava `Redis(host=nodes[0])`, conectando-se apenas ao primeiro
    nó da lista. Operações cujo hash slot caísse fora desse nó recebiam
    `CLUSTERDOWN Hash slot not served`, bloqueando leader election e
    cache de contexto estratégico.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: RedisCluster | None = None

    async def initialize(self) -> None:
        """Conectar ao Redis Cluster usando todos os nodes como bootstrap."""
        try:
            startup_nodes = [
                ClusterNode(
                    host=entry.split(":")[0],
                    port=int(entry.split(":")[1]) if ":" in entry else 6379,
                )
                for entry in self.settings.REDIS_CLUSTER_NODES.split(",")
                if entry.strip()
            ]

            password = self.settings.REDIS_PASSWORD or None

            self.client = RedisCluster(
                startup_nodes=startup_nodes,
                password=password,
                ssl=self.settings.REDIS_SSL_ENABLED,
                decode_responses=True,
                # Tolerar slots em re-shard / nó offline parcial — caso
                # contrário um único nó indisponível bloqueia o cliente.
                require_full_coverage=False,
                # reinitialize_steps controla quantos MOVED até recarregar
                # a topology. Mantém-se explícito (apesar de ser o default
                # da lib em redis-py 7.x) para tornar o trade-off visível
                # e estável face a alterações de default upstream.
                reinitialize_steps=5,
            )

            await self.client.ping()
            logger.info(
                "redis_cluster_initialized",
                node_count=len(startup_nodes),
            )

        except Exception as e:
            logger.exception("redis_cluster_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Fechar conexão Redis Cluster.

        TR-1: `RedisCluster.close()` está deprecated desde redis-py 5.0
        (delega para `aclose()` mas emite DeprecationWarning). Usar
        `aclose()` directamente para compatibilidade futura.
        """
        if self.client:
            await self.client.aclose()
            logger.info("redis_cluster_closed")

    async def cache_strategic_context(
        self, key: str, data: dict[str, Any], ttl_seconds: int
    ) -> None:
        """Cachear contexto estratégico"""
        try:
            await self.client.setex(key, ttl_seconds, json.dumps(data))

            logger.debug("context_cached", key=key, ttl=ttl_seconds)

        except Exception as e:
            logger.exception("context_cache_failed", key=key, error=str(e))

    async def get_cached_context(self, key: str) -> dict[str, Any] | None:
        """Recuperar contexto cacheado"""
        try:
            data = await self.client.get(key)
            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.exception("context_get_failed", key=key, error=str(e))
            return None

    async def set_decision_lock(self, decision_type: str, ttl_seconds: int) -> bool:
        """Criar lock distribuído para evitar decisões concorrentes"""
        try:
            lock_key = f"decision:lock:{decision_type}"
            result = await self.client.set(lock_key, "1", nx=True, ex=ttl_seconds)
            return result is not None

        except Exception as e:
            logger.exception("decision_lock_failed", decision_type=decision_type, error=str(e))
            return False

    async def release_decision_lock(self, decision_type: str) -> None:
        """Liberar lock de decisão"""
        try:
            lock_key = f"decision:lock:{decision_type}"
            await self.client.delete(lock_key)

        except Exception as e:
            logger.exception(
                "decision_lock_release_failed",
                decision_type=decision_type,
                error=str(e),
            )

    async def increment_decision_counter(self, decision_type: str) -> int:
        """Incrementar contador de decisões por tipo"""
        try:
            counter_key = f"decision:counter:{decision_type}"
            return await self.client.incr(counter_key)

        except Exception as e:
            logger.exception(
                "decision_counter_increment_failed",
                decision_type=decision_type,
                error=str(e),
            )
            return 0

    async def get_decision_stats(self) -> dict[str, int]:
        """Obter estatísticas de decisões"""
        try:
            stats = {}
            keys = await self.client.keys("decision:counter:*")

            for key in keys:
                decision_type = key.split(":")[-1]
                count = await self.client.get(key)
                stats[decision_type] = int(count) if count else 0

            return stats

        except Exception as e:
            logger.exception("decision_stats_failed", error=str(e))
            return {}
