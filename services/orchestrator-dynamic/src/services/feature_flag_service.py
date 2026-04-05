"""
FeatureFlagService - Gestão de Feature Flags Dinâmicas.

Serviço centralizado para gerir feature flags com:
- Persistência em MongoDB
- Cache distribuído em Redis
- Avaliação baseada em contexto
- Integração com RolloutStrategy
"""
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from src.services.rollout_strategy import RolloutStrategy

logger = structlog.get_logger(__name__)


class FeatureFlagService:
    """
    Serviço de gestão de feature flags.

    Fornece CRUD completo, cache em Redis e avaliação de flags
    baseada em contexto de execução.
    """

    # TTL do cache em segundos (padrão: 60s)
    CACHE_TTL = 60

    # Prefixo de chaves no Redis
    CACHE_KEY_PREFIX = "feature_flag"

    def __init__(self, mongodb, redis):
        """
        Inicializa o serviço de feature flags.

        Args:
            mongodb: Cliente MongoDB (coleção de feature flags)
            redis: Cliente Redis para cache
        """
        self.mongodb = mongodb
        self.redis = redis

    def _get_cache_key(self, flag_name: str) -> str:
        """Retorna chave de cache para uma flag."""
        return f"{self.CACHE_KEY_PREFIX}:{flag_name}"

    async def get_flag(self, flag_name: str) -> dict[str, Any] | None:
        """
        Busca uma feature flag por nome.

        Tenta cache Redis primeiro, depois MongoDB.

        Args:
            flag_name: Nome da feature flag

        Returns:
            Dados da flag ou None se não encontrada
        """
        cache_key = self._get_cache_key(flag_name)

        # Tentar cache Redis
        cached = await self.redis.get(cache_key)
        if cached:
            logger.debug("flag_cache_hit", flag_name=flag_name)
            return json.loads(cached)

        logger.debug("flag_cache_miss", flag_name=flag_name)

        # Buscar do MongoDB
        document = await self.mongodb.find_one({"flag_name": flag_name})
        if not document:
            logger.warning("flag_not_found", flag_name=flag_name)
            return None

        # Remover _id do MongoDB
        if "_id" in document:
            document.pop("_id")

        # Popular cache
        await self._populate_cache(cache_key, document)

        return document

    async def set_flag(
        self, flag_name: str, flag_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Cria ou atualiza uma feature flag.

        Args:
            flag_name: Nome da feature flag
            flag_data: Dados da flag (enabled, rollout_strategy, etc.)

        Returns:
            Dados da flag atualizados
        """
        now = datetime.now(timezone.utc).isoformat()

        # Adicionar campos de auditoria
        flag_data["flag_name"] = flag_name
        flag_data["updated_at"] = now

        # Upsert no MongoDB
        await self.mongodb.update_one(
            {"flag_name": flag_name},
            {"$set": flag_data},
            upsert=True,
        )

        # Invalidar cache
        cache_key = self._get_cache_key(flag_name)
        await self.redis.delete(cache_key)

        logger.info(
            "flag_updated",
            flag_name=flag_name,
            enabled=flag_data.get("enabled"),
            strategy=flag_data.get("rollout_strategy"),
        )

        return flag_data

    async def delete_flag(self, flag_name: str) -> bool:
        """
        Remove uma feature flag.

        Args:
            flag_name: Nome da feature flag

        Returns:
            True se flag foi deletada, False se não existia
        """
        # Deletar do MongoDB
        result = await self.mongodb.delete_one({"flag_name": flag_name})

        # Invalidar cache
        cache_key = self._get_cache_key(flag_name)
        await self.redis.delete(cache_key)

        deleted = result.deleted_count > 0

        if deleted:
            logger.info("flag_deleted", flag_name=flag_name)
        else:
            logger.warning("flag_delete_not_found", flag_name=flag_name)

        return deleted

    async def list_flags(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """
        Lista todas as feature flags.

        Args:
            enabled_only: Se True, retorna apenas flags ativas

        Returns:
            Lista de flags ordenadas por created_at (decrescente)
        """
        query = {}
        if enabled_only:
            query["enabled"] = True

        cursor = self.mongodb.find(query, sort=[("created_at", -1)])
        flags = await cursor.to_list(length=None)

        # Remover _id dos documentos
        for flag in flags:
            flag.pop("_id", None)

        logger.debug(
            "flags_listed",
            count=len(flags),
            enabled_only=enabled_only,
        )

        return flags

    async def list_filters(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """
        Alias para list_flags (compatibilidade com testes).

        Args:
            enabled_only: Se True, retorna apenas flags ativas

        Returns:
            Lista de flags
        """
        return await self.list_flags(enabled_only=enabled_only)

    async def evaluate_flag(self, flag_name: str, context: dict[str, Any]) -> bool:
        """
        Avalia se uma flag está ativa para o contexto fornecido.

        Args:
            flag_name: Nome da feature flag
            context: Contexto de avaliação (tenant_id, user_id, namespace, etc.)

        Returns:
            True se flag está ativa, False caso contrário
        """
        flag = await self.get_flag(flag_name)

        if not flag:
            logger.debug("flag_evaluation_not_found", flag_name=flag_name)
            return False

        # Verificar se flag está enabled
        if not flag.get("enabled", False):
            logger.debug(
                "flag_evaluation_disabled",
                flag_name=flag_name,
            )
            return False

        # Delegar avaliação para RolloutStrategy
        result = RolloutStrategy.evaluate(flag, context)

        logger.debug(
            "flag_evaluation_result",
            flag_name=flag_name,
            result=result,
            strategy=flag.get("rollout_strategy"),
            tenant_id=context.get("tenant_id"),
            namespace=context.get("namespace"),
        )

        return result

    async def _populate_cache(self, key: str, data: dict[str, Any]) -> None:
        """
        Popula o cache Redis com dados da flag.

        Args:
            key: Chave do cache
            data: Dados a armazenar
        """
        try:
            serialized = json.dumps(data)
            await self.redis.setex(key, self.CACHE_TTL, serialized)
        except Exception as e:
            logger.warning(
                "flag_cache_populate_failed",
                key=key,
                error=str(e),
            )
            # Fail-open: continuar sem cache
