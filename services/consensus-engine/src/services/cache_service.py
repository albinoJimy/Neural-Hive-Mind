"""
Cache Service com Cache-aside Pattern para Consensus Engine.

Implementa cache-aside pattern para:
1. Plan approvals - acesso frequente, TTL 5 minutos
2. Consensus decisions - acesso moderado, TTL 2 minutos
3. Specialist status - acesso frequente, TTL 30 segundos

Cache-aside workflow:
- READ: Check cache → miss → fetch DB → write cache → return
- WRITE: Update DB → invalidate cache
"""

from collections.abc import Callable
from typing import Any, Optional

import structlog
from src.clients.redis_client import RedisClient

logger = structlog.get_logger()


class CacheAsideService:
    """
    Serviço de cache usando padrão cache-aside.

    O padrão cache-aside delega o gerenciamento do cache à aplicação:
    - Cache é verificado primeiro
    - Em caso de miss, dados são buscados na fonte
    - Dados são escritos no cache para próximos acessos
    - Escritas invalidam o cache para garantir consistência
    """

    def __init__(self, redis_client: RedisClient, config):
        """
        Inicializa serviço de cache-aside.

        Args:
            redis_client: Cliente Redis configurado
            config: Configurações do consensus-engine
        """
        self.redis = redis_client
        self.config = config

        # Métricas
        self._hits = 0
        self._misses = 0
        self._errors = 0

        logger.info(
            "Cache-aside service inicializado",
            enabled=self.redis.is_enabled(),
            ttl_plan_approval=self.redis.ttl_plan_approval,
            ttl_consensus_decision=self.redis.ttl_consensus_decision,
            ttl_specialist_status=self.redis.ttl_specialist_status,
        )

    async def get_plan_approval(
        self, plan_id: str, db_fetcher: Callable[[], Any]
    ) -> Optional[dict[str, Any]]:
        """
        Obtém plan approval com cache-aside.

        Args:
            plan_id: ID do plano
            db_fetcher: Função assíncrona para buscar do MongoDB

        Returns:
            Dados do plan approval ou None
        """
        cache_key = self.redis.build_key_plan_approval(plan_id)

        # 1. Check cache
        cached_data = await self.redis.get(cache_key)
        if cached_data is not None:
            self._hits += 1
            logger.debug("Cache hit: plan_approval", plan_id=plan_id)
            return cached_data

        # 2. Cache miss - fetch from DB
        self._misses += 1
        logger.debug("Cache miss: plan_approval", plan_id=plan_id)

        try:
            data = await db_fetcher()
            if data:
                # 3. Write to cache
                await self.redis.set(cache_key, data, self.redis.ttl_plan_approval)
                logger.info(
                    "Plan approval cacheado",
                    plan_id=plan_id,
                    ttl=self.redis.ttl_plan_approval,
                )
            return data

        except Exception as e:
            self._errors += 1
            logger.error(
                "Erro ao buscar plan approval do DB",
                plan_id=plan_id,
                error=str(e),
            )
            raise

    async def get_consensus_decision(
        self, decision_id: str, db_fetcher: Callable[[], Any]
    ) -> Optional[dict[str, Any]]:
        """
        Obtém consensus decision com cache-aside.

        Args:
            decision_id: ID da decisão
            db_fetcher: Função assíncrona para buscar do MongoDB

        Returns:
            Dados da decisão ou None
        """
        cache_key = self.redis.build_key_consensus_decision(decision_id)

        # 1. Check cache
        cached_data = await self.redis.get(cache_key)
        if cached_data is not None:
            self._hits += 1
            logger.debug("Cache hit: consensus_decision", decision_id=decision_id)
            return cached_data

        # 2. Cache miss - fetch from DB
        self._misses += 1
        logger.debug("Cache miss: consensus_decision", decision_id=decision_id)

        try:
            data = await db_fetcher()
            if data:
                # 3. Write to cache
                await self.redis.set(cache_key, data, self.redis.ttl_consensus_decision)
                logger.info(
                    "Consensus decision cacheada",
                    decision_id=decision_id,
                    ttl=self.redis.ttl_consensus_decision,
                )
            return data

        except Exception as e:
            self._errors += 1
            logger.error(
                "Erro ao buscar consensus decision do DB",
                decision_id=decision_id,
                error=str(e),
            )
            raise

    async def get_specialist_status(
        self, specialist_type: str, db_fetcher: Callable[[], Any]
    ) -> Optional[dict[str, Any]]:
        """
        Obtém specialist status com cache-aside.

        Args:
            specialist_type: Tipo do especialista
            db_fetcher: Função assíncrona para buscar status

        Returns:
            Dados do status ou None
        """
        cache_key = self.redis.build_key_specialist_status(specialist_type)

        # 1. Check cache
        cached_data = await self.redis.get(cache_key)
        if cached_data is not None:
            self._hits += 1
            logger.debug("Cache hit: specialist_status", specialist_type=specialist_type)
            return cached_data

        # 2. Cache miss - fetch from DB
        self._misses += 1
        logger.debug("Cache miss: specialist_status", specialist_type=specialist_type)

        try:
            data = await db_fetcher()
            if data:
                # 3. Write to cache
                await self.redis.set(cache_key, data, self.redis.ttl_specialist_status)
                logger.debug(
                    "Specialist status cacheado",
                    specialist_type=specialist_type,
                    ttl=self.redis.ttl_specialist_status,
                )
            return data

        except Exception as e:
            self._errors += 1
            logger.error(
                "Erro ao buscar specialist status",
                specialist_type=specialist_type,
                error=str(e),
            )
            raise

    async def invalidate_plan_approval(self, plan_id: str) -> bool:
        """
        Invalida cache de plan approval.

        Deve ser chamado após atualização do plan approval.

        Args:
            plan_id: ID do plano

        Returns:
            True se sucesso
        """
        cache_key = self.redis.build_key_plan_approval(plan_id)
        result = await self.redis.delete(cache_key)
        if result:
            logger.info("Cache invalidado: plan_approval", plan_id=plan_id)
        return result

    async def invalidate_consensus_decision(self, decision_id: str) -> bool:
        """
        Invalida cache de consensus decision.

        Deve ser chamado após atualização da decisão.

        Args:
            decision_id: ID da decisão

        Returns:
            True se sucesso
        """
        cache_key = self.redis.build_key_consensus_decision(decision_id)
        result = await self.redis.delete(cache_key)
        if result:
            logger.info("Cache invalidado: consensus_decision", decision_id=decision_id)
        return result

    async def invalidate_specialist_status(self, specialist_type: str) -> bool:
        """
        Invalida cache de specialist status.

        Deve ser chamado após mudança de status do especialista.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            True se sucesso
        """
        cache_key = self.redis.build_key_specialist_status(specialist_type)
        result = await self.redis.delete(cache_key)
        if result:
            logger.info("Cache invalidado: specialist_status", specialist_type=specialist_type)
        return result

    async def invalidate_all_plan_approvals(self) -> int:
        """
        Invalida todos os caches de plan approval.

        Útil para limpeza massiva ou mudanças globais.

        Returns:
            Número de chaves invalidadas
        """
        pattern = f"{self.redis.PREFIX_PLAN_APPROVAL}:*"
        count = await self.redis.invalidate_pattern(pattern)
        logger.info("Todos os caches de plan_approval invalidados", count=count)
        return count

    async def invalidate_all_consensus_decisions(self) -> int:
        """
        Invalida todos os caches de consensus decision.

        Returns:
            Número de chaves invalidadas
        """
        pattern = f"{self.redis.PREFIX_CONSENSUS_DECISION}:*"
        count = await self.redis.invalidate_pattern(pattern)
        logger.info("Todos os caches de consensus_decision invalidados", count=count)
        return count

    def get_metrics(self) -> dict[str, Any]:
        """
        Obtém métricas do cache.

        Returns:
            Dicionário com métricas
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "miss_rate": 1.0 - hit_rate,
        }

    def reset_metrics(self):
        """Reseta métricas do cache"""
        self._hits = 0
        self._misses = 0
        self._errors = 0
        logger.info("Métricas do cache resetadas")

    async def get_health_status(self) -> dict[str, Any]:
        """
        Obtém status de saúde do cache.

        Returns:
            Dicionário com status
        """
        try:
            cache_stats = await self.redis.get_cache_stats()
            metrics = self.get_metrics()

            return {
                "status": "healthy" if self.redis.is_enabled() else "disabled",
                "enabled": self.redis.is_enabled(),
                "cache_stats": cache_stats,
                "metrics": metrics,
            }
        except Exception as e:
            logger.error("Erro ao obter status do cache", error=str(e))
            return {
                "status": "error",
                "error": str(e),
            }
