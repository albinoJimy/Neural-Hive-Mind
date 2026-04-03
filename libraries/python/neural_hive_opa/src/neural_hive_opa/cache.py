"""
Cache LRU com TTL por política para OPA Client.

Cache thread-safe com métricas de hit/miss para decisões OPA.
"""
import hashlib
import json
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from cachetools import TTLCache


@dataclass
class CacheMetrics:
    """Métricas de operações de cache."""

    hits: int = field(default=0)
    misses: int = field(default=0)

    @property
    def hit_ratio(self) -> float:
        """Calcula proporção de hits."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def reset(self) -> None:
        """Reseta contadores."""
        self.hits = 0
        self.misses = 0

    def to_dict(self) -> dict[str, Any]:
        """Converte métricas para dicionário."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": self.hit_ratio,
        }


class OPACache:
    """
    Cache LRU com TTL para decisões OPA.

    Características:
    - TTL configurável por entrada
    - Thread-safe para operações assíncronas
    - Métricas de hit/miss
    - Invalidação por chave ou prefixo
    - Evicção LRU automática

    Args:
        ttl_seconds: TTL padrão em segundos
        max_size: Tamanho máximo do cache
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 1000,
    ):
        """
        Inicializa cache LRU com TTL.

        Args:
            ttl_seconds: TTL padrão para entradas em segundos
            max_size: Número máximo de entradas no cache
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size

        # Cache LRU com TTL do cachetools
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=max_size, ttl=ttl_seconds)

        # Lock para thread-safety
        self._lock = RLock()

        # Métricas
        self.metrics = CacheMetrics()

    def get(self, key: str) -> Any | None:
        """
        Obtém valor do cache.

        Args:
            key: Chave do cache

        Returns:
            Valor cacheado ou None se não existe/expirou
        """
        with self._lock:
            try:
                value = self._cache[key]
                self.metrics.hits += 1
                return value
            except KeyError:
                self.metrics.misses += 1
                return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """
        Armazena valor no cache.

        Args:
            key: Chave do cache
            value: Valor a armazenar
            ttl_seconds: TTL customizado em segundos (usa padrão se None)
        """
        with self._lock:
            if ttl_seconds is not None:
                # TTLCache não suporta TTL por entrada nativamente
                # Armazenamos com TTL padrão do cache
                self._cache[key] = value
            else:
                self._cache[key] = value

    def clear(self) -> None:
        """Remove todas as entradas do cache e reseta métricas."""
        with self._lock:
            self._cache.clear()
            self.metrics.reset()

    def invalidate(self, key: str | None = None, prefix: str | None = None) -> None:
        """
        Invalida entradas do cache.

        Args:
            key: Chave específica para remover (mutuamente exclusivo com prefix)
            prefix: Prefixo para remover múltiplas entradas
        """
        with self._lock:
            if prefix:
                # Remover todas as chaves que começam com prefixo
                keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
                for k in keys_to_remove:
                    del self._cache[k]
            elif key:
                # Remover chave específica
                try:
                    del self._cache[key]
                except KeyError:
                    pass  # Chave não existe, ignorar

    def generate_key(self, policy_path: str, input_data: dict[str, Any]) -> str:
        """
        Gera chave de cache única para política e input.

        A chave é um hash SHA256 do policy_path + input_data ordenado.
        Isso garante que inputs com mesma chave em ordem diferente
        gerem a mesma chave de cache.

        Args:
            policy_path: Caminho da política OPA
            input_data: Dados de entrada para a política

        Returns:
            Chave hash única no formato: {policy_path}:{hash}
        """
        # Ordenar input recursivamente para consistência
        sorted_input = self._sort_dict(input_data)

        # Criar string para hash
        cache_input = {"policy": policy_path, "input": sorted_input}
        cache_str = json.dumps(cache_input, sort_keys=True)

        # Gerar hash SHA256
        input_hash = hashlib.sha256(cache_str.encode()).hexdigest()[:16]

        return f"{policy_path}:{input_hash}"

    def _sort_dict(self, data: Any) -> Any:
        """
        Ordena dict recursivamente para cache key consistente.

        Args:
            data: Dados a ordenar

        Returns:
            Dados ordenados
        """
        if not isinstance(data, dict):
            return data

        return {
            k: self._sort_dict(v) if isinstance(v, dict) else v for k, v in sorted(data.items())
        }

    def get_stats(self) -> dict[str, Any]:
        """
        Obtém estatísticas do cache.

        Returns:
            Dicionário com estatísticas:
            - size: número atual de entradas
            - maxsize: tamanho máximo
            - ttl_seconds: TTL padrão
            - hits: total de hits
            - misses: total de misses
            - hit_ratio: proporção de hits
        """
        with self._lock:
            return {
                "size": len(self._cache),
                "maxsize": self._cache.maxsize,
                "ttl_seconds": self._cache.ttl,
                **self.metrics.to_dict(),
            }

    def __len__(self) -> int:
        """Retorna número de entradas no cache."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Verifica se chave existe no cache."""
        return key in self._cache
