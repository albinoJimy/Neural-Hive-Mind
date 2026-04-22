"""Pattern matching for similar plans."""

import structlog

from .models import Fingerprint, PatternRecord
from .pattern_registry import PatternRegistry

logger = structlog.get_logger()


class PatternMatcher:
    """Busca padroes similares para adaptacao de pesos."""

    def __init__(self, mongo_client):
        """
        Inicializa matcher.

        Args:
            mongo_client: Cliente MongoDB
        """
        self.registry = PatternRegistry(mongo_client)
        self.collection = self.registry.collection
        self.logger = logger
        self._match_cache = {}

    async def find_similar(
        self, fingerprint: Fingerprint, limit: int = 50, min_similarity: float = 0.0
    ) -> list[PatternRecord]:
        """
        Busca padroes similares.

        Args:
            fingerprint: Fingerprint para matching
            limit: Maximo de resultados
            min_similarity: Similaridade Jaccard minima

        Returns:
            Lista de PatternRecord ordenados por similaridade
        """
        cache_key = self._cache_key(fingerprint, min_similarity)

        # Check cache
        if cache_key in self._match_cache:
            self.logger.debug("Cache hit for pattern matching")
            return self._match_cache[cache_key][:limit]

        # Buscar no registry
        similar = await self.registry.find_similar_patterns(
            fingerprint, limit=limit, min_similarity=min_similarity
        )

        # Cache e retornar
        self._match_cache[cache_key] = similar
        return similar[:limit]

    def get_match_count(self, fingerprint: Fingerprint) -> int:
        """Retorna numero de matches (usando cache)."""
        cache_key = self._cache_key(fingerprint, 0.0)
        return len(self._match_cache.get(cache_key, []))

    def clear_cache(self):
        """Limpa cache de matching."""
        self._match_cache.clear()

    def _cache_key(self, fingerprint: Fingerprint, min_similarity: float) -> str:
        """Gera chave de cache."""
        types_str = ",".join(sorted(fingerprint.task_types))
        return f"{fingerprint.domain}:{fingerprint.task_count_range}:{min_similarity}:{types_str}"
