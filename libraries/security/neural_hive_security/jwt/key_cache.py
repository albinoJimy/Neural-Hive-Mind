"""
KeyCache - Cache de Chaves Públicas com TTL

Implementa cache thread-safe para chaves públicas JWK com expiração
baseada em TTL. Usado pelo SPIFFE Manager para cache de trust bundle keys.

Feature: TTL configurável (padrão: 5 minutos)
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CachedKey:
    """Chave em cache com timestamp de expiração."""

    key_id: str
    key_data: Any
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        """Verifica se a chave está expirada."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def ttl_remaining(self) -> float | None:
        """Retorna TTL restante em segundos, ou None se não expira."""
        if self.expires_at is None:
            return None
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)


class KeyCache:
    """
    Cache de chaves públicas com TTL.

    Características:
    - Thread-safe com lock
    - TTL configurável (padrão: 300 segundos)
    - Estatísticas de hits/misses
    - Invalidação por key ID ou limpeza total

    Exemplo de uso:
        cache = KeyCache(ttl_seconds=300)

        # Armazenar chave
        cache.put("key-1", {"kty": "RSA", "kid": "key-1", ...})

        # Recuperar chave
        key = cache.get("key-1")
    """

    # TTL padrão: 5 minutos
    DEFAULT_TTL_SECONDS = 300

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """
        Inicializa cache de chaves.

        Args:
            ttl_seconds: Tempo de vida das chaves em segundos (padrão: 300)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, CachedKey] = {}
        self._lock = threading.RLock()

        # Estatísticas
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        logger.debug("key_cache_initialized", ttl_seconds=ttl_seconds)

    def put(self, key_id: str, key_data: Any, ttl_seconds: int | None = None) -> None:
        """
        Armazena uma chave no cache.

        Args:
            key_id: Identificador da chave (kid)
            key_data: Dados da chave (dict JWK)
            ttl_seconds: TTL específico para esta chave (opcional)
        """
        with self._lock:
            ttl = ttl_seconds or self.ttl_seconds
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

            cached_key = CachedKey(key_id=key_id, key_data=key_data, expires_at=expires_at)

            self._cache[key_id] = cached_key

            logger.debug(
                "key_cached", key_id=key_id, ttl_seconds=ttl, expires_at=expires_at.isoformat()
            )

    def get(self, key_id: str) -> Any | None:
        """
        Recupera uma chave do cache.

        Args:
            key_id: Identificador da chave

        Returns:
            Dados da chave ou None se não existe ou está expirada
        """
        with self._lock:
            cached_key = self._cache.get(key_id)

            if cached_key is None:
                self._misses += 1
                logger.debug("cache_miss", key_id=key_id)
                return None

            # Verificar expiração
            if cached_key.is_expired():
                # Remover chave expirada
                del self._cache[key_id]
                self._misses += 1
                self._evictions += 1
                logger.debug(
                    "cache_miss_expired",
                    key_id=key_id,
                    expired_at=cached_key.expires_at.isoformat(),
                )
                return None

            self._hits += 1
            logger.debug("cache_hit", key_id=key_id, ttl_remaining=cached_key.ttl_remaining())
            return cached_key.key_data

    def invalidate(self, key_id: str) -> bool:
        """
        Invalida uma chave específica do cache.

        Args:
            key_id: Identificador da chave

        Returns:
            True se a chave foi removida, False se não existia
        """
        with self._lock:
            if key_id in self._cache:
                del self._cache[key_id]
                logger.debug("key_invalidated", key_id=key_id)
                return True
            return False

    def clear(self) -> int:
        """
        Limpa todas as chaves do cache.

        Returns:
            Número de chaves removidas
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info("cache_cleared", keys_removed=count)
            return count

    def cleanup_expired(self) -> int:
        """
        Remove todas as chaves expiradas do cache.

        Returns:
            Número de chaves removidas
        """
        with self._lock:
            expired_keys = [
                key_id for key_id, cached_key in self._cache.items() if cached_key.is_expired()
            ]

            for key_id in expired_keys:
                del self._cache[key_id]
                self._evictions += 1

            if expired_keys:
                logger.debug("expired_keys_cleaned", count=len(expired_keys))

            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """
        Retorna estatísticas do cache.

        Returns:
            Dict com hits, misses, evictions, size, hit_rate
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._cache),
                "hit_rate": hit_rate,
            }

    def reset_stats(self) -> None:
        """Reseta estatísticas do cache."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def get_ttl_remaining(self, key_id: str) -> float | None:
        """
        Retorna TTL restante para uma chave específica.

        Args:
            key_id: Identificador da chave

        Returns:
            TTL restante em segundos ou None se a chave não existe
        """
        with self._lock:
            cached_key = self._cache.get(key_id)
            if cached_key:
                return cached_key.ttl_remaining()
            return None

    def extend_ttl(self, key_id: str, additional_seconds: int) -> bool:
        """
        Estende o TTL de uma chave existente.

        Args:
            key_id: Identificador da chave
            additional_seconds: Segundos a adicionar ao TTL atual

        Returns:
            True se a chave existe e foi estendida, False caso contrário
        """
        with self._lock:
            cached_key = self._cache.get(key_id)
            if cached_key and not cached_key.is_expired():
                if cached_key.expires_at:
                    cached_key.expires_at += timedelta(seconds=additional_seconds)
                    logger.debug(
                        "key_ttl_extended",
                        key_id=key_id,
                        additional_seconds=additional_seconds,
                        new_expires_at=cached_key.expires_at.isoformat(),
                    )
                    return True
            return False

    def __len__(self) -> int:
        """Retorna número de chaves no cache (incluindo expiradas)."""
        with self._lock:
            return len(self._cache)

    def __contains__(self, key_id: str) -> bool:
        """Verifica se key_id existe no cache (e não está expirado)."""
        return self.get(key_id) is not None

    def keys(self) -> list:
        """Retorna lista de key_ids no cache (apenas não expirados)."""
        with self._lock:
            return [
                key_id for key_id, cached_key in self._cache.items() if not cached_key.is_expired()
            ]

    def items(self) -> list:
        """Retorna itens (key_id, key_data) do cache (apenas não expirados)."""
        with self._lock:
            return [
                (key_id, cached_key.key_data)
                for key_id, cached_key in self._cache.items()
                if not cached_key.is_expired()
            ]
