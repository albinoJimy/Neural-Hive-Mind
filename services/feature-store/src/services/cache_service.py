"""
Redis Cache Service para Feature Store

Gerencia cache de features usando Redis com TTL configurável.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

try:
    import aioredis

    HAS_AIOREDIS = True
except ImportError:
    try:
        import redis.asyncio as aioredis

        HAS_AIOREDIS = True
    except ImportError:
        HAS_AIOREDIS = False

from src.config.settings import Settings

logger = structlog.get_logger()


class RedisCacheService:
    """Serviço de cache Redis para features"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._redis = None
        self._pool = None
        self._is_connected = False

    async def initialize(self):
        """Inicializa conexão Redis"""
        if not HAS_AIOREDIS:
            logger.warning("aioredis não disponível, cache desabilitado")
            return

        try:
            # Cria pool de conexões
            self._pool = aioredis.ConnectionPool.from_url(
                self.settings.redis_url,
                max_connections=self.settings.redis_max_connections,
                socket_timeout=self.settings.redis_socket_timeout,
                socket_connect_timeout=self.settings.redis_socket_connect_timeout,
                decode_responses=True,
            )

            self._redis = aioredis.Redis(connection_pool=self._pool)

            # Testa conexão
            await self._redis.ping()

            self._is_connected = True
            logger.info(
                "Redis cache inicializado",
                url=self.settings.redis_url,
                max_connections=self.settings.redis_max_connections,
            )
        except Exception as e:
            logger.error("Falha ao inicializar Redis", error=str(e))
            self._is_connected = False
            raise

    async def close(self):
        """Fecha conexão Redis"""
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.close()
        self._is_connected = False
        logger.info("Redis cache fechado")

    def is_available(self) -> bool:
        """Verifica se cache está disponível"""
        return self._is_connected and self._redis is not None

    def _make_key(self, plan_id: str) -> str:
        """Gera chave Redis para um plano"""
        return f"feature_store:{plan_id}"

    async def get(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca features do cache

        Args:
            plan_id: ID do plano

        Returns:
            Dict com features ou None se não encontrado/expirado
        """
        if not self.is_available():
            return None

        try:
            key = self._make_key(plan_id)
            cached = await self._redis.get(key)

            if cached:
                data = json.loads(cached)
                logger.debug("Cache hit", plan_id=plan_id)
                return data

            logger.debug("Cache miss", plan_id=plan_id)
            return None

        except Exception as e:
            logger.warning("Erro ao ler do cache", plan_id=plan_id, error=str(e))
            return None

    async def set(
        self, plan_id: str, features: Dict[str, Any], ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Salva features no cache

        Args:
            plan_id: ID do plano
            features: Dict com features
            ttl_seconds: TTL em segundos (usa padrão se None)

        Returns:
            True se salvo com sucesso
        """
        if not self.is_available():
            return False

        try:
            ttl = ttl_seconds or self.settings.redis_cache_ttl_seconds
            key = self._make_key(plan_id)

            # Adiciona timestamp de cache
            features["_cached_at"] = datetime.now(timezone.utc).isoformat()

            await self._redis.setex(key, ttl, json.dumps(features))

            logger.debug("Features salvas no cache", plan_id=plan_id, ttl=ttl)
            return True

        except Exception as e:
            logger.warning("Erro ao salvar no cache", plan_id=plan_id, error=str(e))
            return False

    async def delete(self, plan_id: str) -> bool:
        """
        Remove features do cache

        Args:
            plan_id: ID do plano

        Returns:
            True se removido com sucesso
        """
        if not self.is_available():
            return False

        try:
            key = self._make_key(plan_id)
            result = await self._redis.delete(key)

            logger.debug("Features removidas do cache", plan_id=plan_id, deleted=result > 0)
            return result > 0

        except Exception as e:
            logger.warning("Erro ao deletar do cache", plan_id=plan_id, error=str(e))
            return False

    async def clear_all(self) -> int:
        """
        Limpa todas as features do cache

        Returns:
            Número de chaves removidas
        """
        if not self.is_available():
            return 0

        try:
            pattern = "feature_store:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self._redis.delete(*keys)
                logger.info("Cache limpo", deleted=deleted)
                return deleted

            return 0

        except Exception as e:
            logger.error("Erro ao limpar cache", error=str(e))
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do cache

        Returns:
            Dict com estatísticas
        """
        if not self.is_available():
            return {"available": False, "keys_count": 0}

        try:
            pattern = "feature_store:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            return {
                "available": True,
                "keys_count": len(keys),
                "ttl_seconds": self.settings.redis_cache_ttl_seconds,
            }

        except Exception as e:
            logger.error("Erro ao obter stats do cache", error=str(e))
            return {"available": False, "error": str(e)}
