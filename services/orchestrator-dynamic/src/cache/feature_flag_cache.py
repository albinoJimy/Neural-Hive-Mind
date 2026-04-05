"""
Cache Redis para Feature Flags.

Implementa cache distribuído com:
- TTL configurável (default 60s)
- get_or_load com fallback para repository
- Invalidação de cache
- Métricas de hit/miss
- Tratamento de erros fail-open
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from src.models.feature_flag import FeatureFlag

logger = structlog.get_logger(__name__)


class CacheError(Exception):
    """Erro base para operações de cache."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class CacheMetrics:
    """
    Métricas de cache para telemetria.

    Rastreia hits, misses e calcula hit ratio.
    """

    def __init__(self) -> None:
        self.total_hits: int = 0
        self.total_misses: int = 0

    def record_hit(self) -> None:
        """Registra um cache hit."""
        self.total_hits += 1

    def record_miss(self) -> None:
        """Registra um cache miss."""
        self.total_misses += 1

    def reset(self) -> None:
        """Reseta contadores."""
        self.total_hits = 0
        self.total_misses = 0

    @property
    def hit_ratio(self) -> float:
        """Calcula hit ratio (0.0-1.0)."""
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas de cache."""
        return {
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_ratio": round(self.hit_ratio, 4),
            "total_operations": self.total_hits + self.total_misses,
        }


class FeatureFlagCache:
    """
    Cache Redis para Feature Flags.

    Fornece cache distribuído com invalidação automática.
    """

    def __init__(
        self,
        redis,
        ttl_seconds: int = 60,
        key_prefix: str = "feature_flag:",
    ):
        """
        Inicializa cache.

        Args:
            redis: Cliente Redis (aioredis)
            ttl_seconds: TTL em segundos (default: 60)
            key_prefix: Prefixo para chaves Redis
        """
        self._redis = redis
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self._metrics = CacheMetrics()

    def _make_key(self, name: str) -> str:
        """Gera chave Redis para flag."""
        return f"{self.key_prefix}{name}"

    async def get(self, name: str) -> FeatureFlag | None:
        """
        Busca flag do cache.

        Args:
            name: Nome da flag

        Returns:
            Instância de FeatureFlag ou None se não encontrada
        """
        if self._redis is None:
            self._metrics.record_miss()
            return None

        try:
            key = self._make_key(name)
            data = await self._redis.get(key)

            if data is None:
                self._metrics.record_miss()
                return None

            flag_dict = json.loads(data)
            flag = FeatureFlag.from_dict(flag_dict)

            self._metrics.record_hit()
            return flag

        except (json.JSONDecodeError, ValueError):
            self._metrics.record_miss()
            logger.warning("feature_flag_cache_invalid_json", name=name)
            return None
        except Exception as e:
            self._metrics.record_miss()
            logger.error("feature_flag_cache_get_error", name=name, error=str(e))
            return None

    async def set(self, flag: FeatureFlag, ttl_seconds: int | None = None) -> bool:
        """
        Armazena flag no cache.

        Args:
            flag: Instância de FeatureFlag
            ttl_seconds: TTL override (usa default se não fornecido)

        Returns:
            True se armazenou com sucesso
        """
        if self._redis is None:
            return False

        try:
            key = self._make_key(flag.name)
            data = json.dumps(flag.to_dict())
            ttl = ttl_seconds or self.ttl_seconds

            await self._redis.setex(key, ttl, data)

            logger.debug("feature_flag_cached", name=flag.name, ttl=ttl)
            return True

        except Exception as e:
            logger.error("feature_flag_cache_set_error", name=flag.name, error=str(e))
            return False

    async def delete(self, name: str) -> bool:
        """
        Remove flag do cache.

        Args:
            name: Nome da flag

        Returns:
            True se removeu, False se não encontrou ou erro
        """
        if self._redis is None:
            return False

        try:
            key = self._make_key(name)
            result = await self._redis.delete(key)

            deleted = result > 0 if result is not None else False

            if deleted:
                logger.debug("feature_flag_cache_deleted", name=name)

            return deleted

        except Exception as e:
            logger.error("feature_flag_cache_delete_error", name=name, error=str(e))
            return False

    async def invalidate(self, name: str) -> None:
        """
        Invalida cache de flag específica.

        Alias para delete.

        Args:
            name: Nome da flag
        """
        await self.delete(name)

    async def clear(self) -> int:
        """
        Limpa todo o cache de flags.

        Returns:
            Número de chaves removidas
        """
        if self._redis is None:
            return 0

        try:
            pattern = f"{self.key_prefix}*"
            keys = await self._redis.keys(pattern)

            if not keys:
                return 0

            result = await self._redis.delete(*keys)

            logger.info("feature_flag_cache_cleared", count=result)
            return result if result is not None else len(keys)

        except Exception as e:
            logger.error("feature_flag_cache_clear_error", error=str(e))
            return 0

    async def get_or_load(self, name: str, loader: callable) -> FeatureFlag | None:
        """
        Busca flag do cache ou carrega do repositório.

        Args:
            name: Nome da flag
            loader: Função assíncrona para carregar do repositório

        Returns:
            Instância de FeatureFlag ou None
        """
        # Tentar cache primeiro
        cached = await self.get(name)
        if cached is not None:
            return cached

        # Cache miss - carregar do repositório
        try:
            flag = await loader(name)

            if flag is not None:
                # Armazenar no cache
                await self.set(flag)

            return flag

        except Exception as e:
            logger.error("feature_flag_cache_load_error", name=name, error=str(e))
            return None

    async def get_multiple(self, names: list[str]) -> list[FeatureFlag | None]:
        """
        Busca múltiplas flags do cache.

        Args:
            names: Lista de nomes de flags

        Returns:
            Lista de FeatureFlag ou None para cada nome
        """
        results = []

        for name in names:
            flag = await self.get(name)
            results.append(flag)

        return results

    async def set_multiple(self, flags: list[FeatureFlag]) -> int:
        """
        Armazena múltiplas flags no cache.

        Args:
            flags: Lista de FeatureFlag

        Returns:
            Número de flags armazenadas
        """
        if self._redis is None:
            return 0

        stored = 0

        for flag in flags:
            if await self.set(flag):
                stored += 1

        return stored

    async def is_enabled_for(self, name: str, context: dict[str, Any]) -> bool:
        """
        Avalia se flag está habilitada para o contexto (usando cache).

        Args:
            name: Nome da flag
            context: Contexto de avaliação

        Returns:
            True se flag está habilitada para o contexto
        """
        flag = await self.get(name)

        if flag is None:
            return False

        return flag.is_enabled_for(context)

    def get_metrics(self) -> dict[str, Any]:
        """
        Retorna métricas de cache.

        Returns:
            Dicionário com estatísticas
        """
        return self._metrics.get_stats()

    def reset_metrics(self) -> None:
        """Reseta métricas de cache."""
        self._metrics.reset()
