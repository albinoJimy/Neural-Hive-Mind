"""Gerenciador de Cache Redis para NLU.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)
"""

import hashlib
import logging
from typing import Any, Optional

from models.intent_envelope import NLUResult

logger = logging.getLogger(__name__)

# Importar métricas
try:
    from observability.metrics import (
        nlu_cache_corruption_total,
        nlu_cache_operations_total,
    )

    CACHE_METRICS_AVAILABLE = True
except ImportError:
    CACHE_METRICS_AVAILABLE = False


class CacheManager:
    """Gerenciador de cache Redis para resultados NLU."""

    def __init__(
        self,
        redis_client=None,
        enabled: bool = True,
        default_ttl: int = 3600,
        key_prefix: str = "nlu",
    ):
        """Inicializa gerenciador de cache.

        Args:
            redis_client: Cliente Redis (pode ser None para cache in-memory)
            enabled: Se cache está habilitado
            default_ttl: TTL padrão em segundos
            key_prefix: Prefixo para chaves Redis
        """
        self.redis_client = redis_client
        self.enabled = enabled and redis_client is not None
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix

        # Cache in-memory fallback
        self._memory_cache: dict[str, tuple[Any, float]] = {}

    def _generate_key(self, text: str, language: str) -> str:
        """Gera chave de cache baseada no texto e idioma.

        Args:
            text: Texto processado
            language: Idioma do texto

        Returns:
            Chave de cache
        """
        content = f"{language}:{text}"
        hash_digest = hashlib.sha256(content.encode()).hexdigest()
        return f"{self.key_prefix}:{hash_digest}"

    async def get(self, text: str, language: str = "pt") -> Optional[NLUResult]:
        """Busca resultado em cache.

        Args:
            text: Texto para buscar
            language: Idioma do texto

        Returns:
            Resultado NLU ou None se não encontrado
        """
        if not self.enabled:
            return None

        key = self._generate_key(text, language)

        try:
            if self.redis_client:
                cached = await self.redis_client.get(key)
                if cached:
                    if CACHE_METRICS_AVAILABLE:
                        nlu_cache_operations_total.labels(operation="hit").inc()
                    return NLUResult.model_validate_json(cached)
            else:
                # Fallback para memória
                if key in self._memory_cache:
                    result, _ = self._memory_cache[key]
                    return result
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            if CACHE_METRICS_AVAILABLE:
                nlu_cache_corruption_total.inc()

        if CACHE_METRICS_AVAILABLE:
            nlu_cache_operations_total.labels(operation="miss").inc()
        return None

    async def set(
        self,
        text: str,
        result: NLUResult,
        language: str = "pt",
        ttl: Optional[int] = None,
    ) -> bool:
        """Salva resultado em cache.

        Args:
            text: Texto processado
            result: Resultado NLU
            language: Idioma do texto
            ttl: Tempo de vida em segundos

        Returns:
            True se salvo com sucesso
        """
        if not self.enabled:
            return False

        key = self._generate_key(text, language)
        ttl = ttl or self.default_ttl

        try:
            serialized = result.model_dump_json()

            if self.redis_client:
                await self.redis_client.set(key, serialized, ex=ttl)
            else:
                # Fallback para memória
                import time

                self._memory_cache[key] = (result, time.time() + ttl)

            if CACHE_METRICS_AVAILABLE:
                nlu_cache_operations_total.labels(operation="set").inc()
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def delete(self, text: str, language: str = "pt") -> bool:
        """Remove entrada do cache.

        Args:
            text: Texto para remover
            language: Idioma do texto

        Returns:
            True se removido com sucesso
        """
        if not self.enabled:
            return False

        key = self._generate_key(text, language)

        try:
            if self.redis_client:
                await self.redis_client.delete(key)
            else:
                self._memory_cache.pop(key, None)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    async def clear(self) -> bool:
        """Limpa todo o cache NLU.

        Returns:
            True se limpo com sucesso
        """
        if not self.enabled:
            return False

        try:
            if self.redis_client:
                pattern = f"{self.key_prefix}:*"
                keys = []
                async for key in self.redis_client.scan_iter(match=pattern):
                    keys.append(key)
                if keys:
                    await self.redis_client.delete(*keys)
            else:
                self._memory_cache.clear()
            return True
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return False

    async def warm_up(self, examples: list[tuple[str, str]], processor_func: Any) -> dict[str, int]:
        """Aquece cache com exemplos pré-definidos.

        Args:
            examples: Lista de tuplas (texto, idioma)
            processor_func: Função assíncrona para processar texto

        Returns:
            Estatísticas do aquecimento
        """
        stats = {"success": 0, "failed": 0, "total": len(examples)}

        for text, lang in examples:
            try:
                key = self._generate_key(text, lang)
                # Verificar se já existe
                if await self.get(text, lang):
                    stats["success"] += 1
                    continue

                # Processar e cachear
                result = await processor_func(text, lang)
                if result:
                    await self.set(text, result, lang)
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                logger.warning(f"Cache warm-up error for '{text[:30]}...': {e}")
                stats["failed"] += 1

        logger.info(f"Cache warm-up completed: {stats}")
        return stats

    async def validate_cache(self) -> dict[str, Any]:
        """Valida integridade do cache.

        Returns:
            Estatísticas de validação
        """
        if not self.enabled:
            return {"valid": False, "reason": "cache_disabled"}

        try:
            if self.redis_client:
                # Testar conexão
                await self.redis_client.ping()
                return {"valid": True, "backend": "redis"}
            else:
                return {"valid": True, "backend": "memory"}
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    async def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do cache.

        Returns:
            Estatísticas atuais
        """
        stats = {
            "enabled": self.enabled,
            "backend": "redis" if self.redis_client else "memory",
            "key_prefix": self.key_prefix,
            "default_ttl": self.default_ttl,
        }

        if self.redis_client:
            try:
                pattern = f"{self.key_prefix}:*"
                count = 0
                async for _ in self.redis_client.scan_iter(match=pattern):
                    count += 1
                stats["entries"] = count
            except Exception:
                stats["entries"] = -1
        else:
            stats["entries"] = len(self._memory_cache)

        return stats

    def is_enabled(self) -> bool:
        """Retorna se cache está habilitado.

        Returns:
            True se habilitado
        """
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        """Habilita/desabilita cache.

        Args:
            enabled: Novo estado
        """
        self.enabled = enabled and (self.redis_client is not None)
