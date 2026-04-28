"""
Cliente Redis para cache-aside pattern no consensus-engine.

Implementa cache-aside pattern para reduzir latência e carga no MongoDB:
- Plan approvals frequentemente acessados (5min TTL)
- Decisões de consenso cacheable (2min TTL)
- Specialist status (30s TTL)
"""

import json
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class CacheEntry:
    """Entrada de cache com metadados"""

    def __init__(self, data: dict[str, Any], cached_at: float, ttl: int):
        self.data = data
        self.cached_at = cached_at
        self.ttl = ttl

    def is_expired(self, current_time: float) -> bool:
        """Verifica se a entrada expirou"""
        return (current_time - self.cached_at) >= self.ttl

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict"""
        return {
            "data": self.data,
            "cached_at": self.cached_at,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        """Desserializa de dict"""
        return cls(data=data["data"], cached_at=data["cached_at"], ttl=data["ttl"])


class RedisClient:
    """
    Cliente Redis para cache-aside pattern.

    Cache-aside workflow:
    1. Application checks cache
    2. Cache miss → fetch from DB
    3. Write to cache for next read
    4. Cache hit → return data directly

    TTLs por tipo de dado:
    - Plan approvals: 5 minutos (300s)
    - Consenso decisions: 2 minutos (120s)
    - Specialist status: 30 segundos (30s)
    """

    # Cache key prefixes
    PREFIX_PLAN_APPROVAL = "cache:plan_approval"
    PREFIX_CONSENSUS_DECISION = "cache:consensus_decision"
    PREFIX_SPECIALIST_STATUS = "cache:specialist_status"

    # TTLs em segundos
    TTL_PLAN_APPROVAL = 300  # 5 minutos
    TTL_CONSENSUS_DECISION = 120  # 2 minutos
    TTL_SPECIALIST_STATUS = 30  # 30 segundos

    def __init__(self, redis_client, config):
        """
        Inicializa cliente Redis.

        Args:
            redis_client: Instância de redis.asyncio.Redis
            config: Configurações do consensus-engine
        """
        self.redis = redis_client
        self.config = config
        self._enabled = True

        # Override TTLs via config se disponível
        self.ttl_plan_approval = getattr(config, "cache_ttl_plan_approval", self.TTL_PLAN_APPROVAL)
        self.ttl_consensus_decision = getattr(
            config, "cache_ttl_consensus_decision", self.TTL_CONSENSUS_DECISION
        )
        self.ttl_specialist_status = getattr(
            config, "cache_ttl_specialist_status", self.TTL_SPECIALIST_STATUS
        )

        logger.info(
            "Redis cache client inicializado",
            ttl_plan_approval=self.ttl_plan_approval,
            ttl_consensus_decision=self.ttl_consensus_decision,
            ttl_specialist_status=self.ttl_specialist_status,
        )

    def disable(self):
        """Desabilita cache (para testes ou degradação)"""
        self._enabled = False
        logger.warning("Cache desabilitado")

    def enable(self):
        """Habilita cache"""
        self._enabled = True
        logger.info("Cache habilitado")

    def is_enabled(self) -> bool:
        """Verifica se cache está habilitado"""
        return self._enabled

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        """
        Obtém valor do cache.

        Args:
            key: Chave do cache

        Returns:
            Dados do cache ou None se miss/expirado
        """
        if not self._enabled:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                entry_data = json.loads(value)
                entry = CacheEntry.from_dict(entry_data)

                # Verificar expiração (double-check com TTL do Redis)
                import time

                if not entry.is_expired(time.time()):
                    logger.debug("Cache hit", key=key)
                    return entry.data
                else:
                    # Remover entrada expirada
                    await self.delete(key)
                    logger.debug("Cache entry expirado", key=key)
                    return None

            logger.debug("Cache miss", key=key)
            return None

        except Exception as e:
            logger.warning("Erro ao obter do cache", key=key, error=str(e))
            return None

    async def set(self, key: str, data: dict[str, Any], ttl: int) -> bool:
        """
        Define valor no cache.

        Args:
            key: Chave do cache
            data: Dados a serem cacheados
            ttl: Time-to-live em segundos

        Returns:
            True se sucesso, False caso contrário
        """
        if not self._enabled:
            return False

        try:
            import time

            entry = CacheEntry(data=data, cached_at=time.time(), ttl=ttl)
            entry_json = json.dumps(entry.to_dict())
            await self.redis.set(key, entry_json, ex=ttl)
            logger.debug("Cache set", key=key, ttl=ttl)
            return True

        except Exception as e:
            logger.warning("Erro ao definir cache", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Remove entrada do cache.

        Args:
            key: Chave do cache

        Returns:
            True se sucesso, False caso contrário
        """
        if not self._enabled:
            return False

        try:
            await self.redis.delete(key)
            logger.debug("Cache delete", key=key)
            return True

        except Exception as e:
            logger.warning("Erro ao deletar do cache", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalida todas as chaves que correspondem ao padrão.

        Args:
            pattern: Padrão de chave (ex: cache:plan_approval:*)

        Returns:
            Número de chaves deletadas
        """
        if not self._enabled:
            return 0

        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self.redis.delete(*keys)
                logger.info("Cache invalidado por padrão", pattern=pattern, count=len(keys))
                return len(keys)

            return 0

        except Exception as e:
            logger.warning("Erro ao invalidar cache por padrão", pattern=pattern, error=str(e))
            return 0

    def build_key_plan_approval(self, plan_id: str) -> str:
        """Constrói chave para plan approval"""
        return f"{self.PREFIX_PLAN_APPROVAL}:{plan_id}"

    def build_key_consensus_decision(self, decision_id: str) -> str:
        """Constrói chave para consensus decision"""
        return f"{self.PREFIX_CONSENSUS_DECISION}:{decision_id}"

    def build_key_specialist_status(self, specialist_type: str) -> str:
        """Constrói chave para specialist status"""
        return f"{self.PREFIX_SPECIALIST_STATUS}:{specialist_type}"

    async def get_cache_stats(self) -> dict[str, Any]:
        """
        Obtém estatísticas do cache.

        Returns:
            Dicionário com estatísticas
        """
        try:
            info = await self.redis.info("stats")
            keyspace_info = await self.redis.info("keyspace")

            # Contar chaves por prefixo
            plan_approval_keys = 0
            consensus_decision_keys = 0
            specialist_status_keys = 0

            async for key in self.redis.scan_iter(match=f"{self.PREFIX_PLAN_APPROVAL}:*"):
                plan_approval_keys += 1

            async for key in self.redis.scan_iter(match=f"{self.PREFIX_CONSENSUS_DECISION}:*"):
                consensus_decision_keys += 1

            async for key in self.redis.scan_iter(match=f"{self.PREFIX_SPECIALIST_STATUS}:*"):
                specialist_status_keys += 1

            return {
                "enabled": self._enabled,
                "plan_approval_keys": plan_approval_keys,
                "consensus_decision_keys": consensus_decision_keys,
                "specialist_status_keys": specialist_status_keys,
                "total_cache_keys": plan_approval_keys
                + consensus_decision_keys
                + specialist_status_keys,
                "redis_info": info,
                "keyspace_info": keyspace_info,
            }

        except Exception as e:
            logger.error("Erro ao obter estatísticas do cache", error=str(e))
            return {
                "enabled": self._enabled,
                "error": str(e),
            }
