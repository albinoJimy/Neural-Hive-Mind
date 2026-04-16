"""Cache distribuído usando Redis para ML Inference API."""

import json
import pickle
from typing import Any, Optional

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


class RedisCache:
    """Cache distribuído usando Redis."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_ttl_seconds: int = 3600,
        key_prefix: str = "ml_inference:",
    ) -> None:
        """Inicializa cache Redis.

        Args:
            redis_url: URL de conexão Redis
            default_ttl_seconds: TTL padrão em segundos
            key_prefix: Prefixo para chaves no Redis
        """
        self._redis_url = redis_url
        self._default_ttl = default_ttl_seconds
        self._key_prefix = key_prefix
        self._redis: Optional[Redis] = None
        self._logger = logger

    async def connect(self) -> None:
        """Conecta ao Redis."""
        self._redis = Redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=False,  # Mantemos bytes para pickle
        )
        await self._redis.ping()
        self._logger.info("redis_cache_connected", url=self._redis_url)

    async def disconnect(self) -> None:
        """Desconecta do Redis."""
        if self._redis:
            await self._redis.close()
            self._logger.info("redis_cache_disconnected")

    def _make_key(self, key: str) -> str:
        """Cria chave com prefixo.

        Args:
            key: Chave original

        Returns:
            Chave com prefixo
        """
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Busca valor do cache.

        Args:
            key: Chave para buscar

        Returns:
            Valor cacheado ou None
        """
        if not self._redis:
            self._logger.warning("redis_not_connected", action="get_failed")
            return None

        try:
            redis_key = self._make_key(key)
            value = await self._redis.get(redis_key)

            if value is None:
                return None

            # Tentar deserializar como JSON primeiro
            try:
                return json.loads(value)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Se falhar, tentar pickle
                return pickle.loads(value)

        except RedisError as e:
            self._logger.error("redis_get_failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Define valor no cache.

        Args:
            key: Chave para definir
            value: Valor para armazenar
            ttl_seconds: TTL em segundos (usa default se None)

        Returns:
            True se sucesso, False caso contrário
        """
        if not self._redis:
            self._logger.warning("redis_not_connected", action="set_failed")
            return False

        try:
            redis_key = self._make_key(key)
            ttl = ttl_seconds or self._default_ttl

            # Serializar valor
            if isinstance(value, (dict, list, str, int, float, bool, type(None))):
                serialized = json.dumps(value)
            else:
                serialized = pickle.dumps(value)

            await self._redis.setex(redis_key, ttl, serialized)
            return True

        except RedisError as e:
            self._logger.error("redis_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Remove valor do cache.

        Args:
            key: Chave para remover

        Returns:
            True se removido, False caso contrário
        """
        if not self._redis:
            return False

        try:
            redis_key = self._make_key(key)
            result = await self._redis.delete(redis_key)
            return result > 0

        except RedisError as e:
            self._logger.error("redis_delete_failed", key=key, error=str(e))
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Limpa todas as chaves que seguem um padrão.

        Args:
            pattern: Padrão de chaves (ex: "model:*")

        Returns:
            Número de chaves removidas
        """
        if not self._redis:
            return 0

        try:
            full_pattern = self._make_key(pattern)
            keys = []
            async for key in self._redis.scan_iter(match=f"{full_pattern}*"):
                keys.append(key)

            if keys:
                return await self._redis.delete(*keys)
            return 0

        except RedisError as e:
            self._logger.error("redis_clear_pattern_failed", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """Verifica se chave existe no cache.

        Args:
            key: Chave para verificar

        Returns:
            True se existe, False caso contrário
        """
        if not self._redis:
            return False

        try:
            redis_key = self._make_key(key)
            result = await self._redis.exists(redis_key)
            return result > 0

        except RedisError as e:
            self._logger.error("redis_exists_failed", key=key, error=str(e))
            return False

    async def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do cache Redis.

        Returns:
            Estatísticas do cache
        """
        if not self._redis:
            return {"status": "disconnected"}

        try:
            info = await self._redis.info("stats")
            db_size = await self._redis.dbsize()

            return {
                "status": "connected",
                "total_keys": db_size,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0),
                ),
                "used_memory_human": info.get("used_memory_human", "unknown"),
            }

        except RedisError as e:
            self._logger.error("redis_stats_failed", error=str(e))
            return {"status": "error", "error": str(e)}

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calcula taxa de acerto do cache.

        Args:
            hits: Número de hits
            misses: Número de misses

        Returns:
            Taxa de acerto (0-1)
        """
        total = hits + misses
        if total == 0:
            return 0.0
        return round(hits / total, 4)


class InferenceCache:
    """Cache especializado para inferências ML."""

    def __init__(self, redis_cache: RedisCache) -> None:
        """Inicializa cache de inferência.

        Args:
            redis_cache: Instância do cache Redis
        """
        self._cache = redis_cache
        self._logger = logger

    async def get_inference_result(
        self,
        model_name: str,
        model_version: str,
        features_hash: str,
    ) -> Optional[dict[str, Any]]:
        """Busca resultado de inferência cacheado.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo
            features_hash: Hash das features de entrada

        Returns:
            Resultado cacheado ou None
        """
        key = f"inference:{model_name}:{model_version}:{features_hash}"
        return await self._cache.get(key)

    async def set_inference_result(
        self,
        model_name: str,
        model_version: str,
        features_hash: str,
        result: dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> bool:
        """Salva resultado de inferência no cache.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo
            features_hash: Hash das features de entrada
            result: Resultado da inferência
            ttl_seconds: TTL em segundos

        Returns:
            True se sucesso, False caso contrário
        """
        key = f"inference:{model_name}:{model_version}:{features_hash}"
        return await self._cache.set(key, result, ttl_seconds)

    async def invalidate_model(self, model_name: str, model_version: str = "*") -> int:
        """Invalida cache de um modelo específico.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo (* para todas)

        Returns:
            Número de chaves invalidadas
        """
        pattern = f"inference:{model_name}:{model_version}:*"
        return await self._cache.clear_pattern(pattern)

    async def get_model_stats(
        self, model_name: str, model_version: str = "latest"
    ) -> dict[str, Any]:
        """Retorna estatísticas de cache de um modelo.

        Args:
            model_name: Nome do modelo
            model_version: Versão do modelo

        Returns:
            Estatísticas do modelo no cache
        """
        # Em produção, buscaria chaves específicas do modelo
        # Por ora, retorna estatísticas gerais
        return await self._cache.get_stats()


def hash_features(features: dict[str, Any]) -> str:
    """Gera hash das features para usar como chave de cache.

    Args:
        features: Dicionário de features

    Returns:
        Hash das features
    """
    import hashlib
    import json

    # Normalizar e ordenar features para hash consistente
    normalized = json.dumps(features, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
