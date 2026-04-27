"""MongoDB repository para versionamento de hipóteses."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from src.config.settings import Settings, get_settings
from src.models.hypothesis_version import HypothesisVersion, VersionDiff

logger = logging.getLogger(__name__)
UTC = UTC


class HypothesisVersionRepository:
    """Repository para gerenciar versões de hipóteses."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        settings: Settings | None = None,
    ):
        """
        Inicializa repository.

        Args:
            client: Cliente Motor MongoDB
            settings: Configurações (usa get_settings() se None)
        """
        self.settings = settings or get_settings()
        self.client = client
        self.database = client[self.settings.mongodb_database]
        self.collection = self.database[self.settings.mongodb_versions_collection]

    async def create_indexes(self) -> None:
        """Cria índices para a coleção de versões."""
        await self.collection.create_index(
            [("version_id", ASCENDING)], unique=True, name="idx_version_id"
        )
        await self.collection.create_index(
            [("hypothesis_id", ASCENDING), ("version_number", DESCENDING)],
            name="idx_hypothesis_version",
        )
        await self.collection.create_index(
            [("hypothesis_id", ASCENDING), ("created_at", DESCENDING)],
            name="idx_hypothesis_created",
        )
        await self.collection.create_index([("created_at", DESCENDING)], name="idx_created_at")

        logger.info("hypothesis_version_indexes_created")

    async def save(self, version: HypothesisVersion) -> HypothesisVersion:
        """
        Salva nova versão.

        Args:
            version: Instância de HypothesisVersion

        Returns:
            Versão salva com _id preenchido
        """
        doc = version.to_dict()
        result = await self.collection.insert_one(doc)

        version.id = result.inserted_id
        logger.info(
            "hypothesis_version_saved",
            version_id=version.version_id,
            hypothesis_id=version.hypothesis_id,
            version_number=version.version_number,
        )
        return version

    async def get_version(
        self,
        hypothesis_id: str,
        version_number: int,
    ) -> HypothesisVersion | None:
        """
        Busca versão específica.

        Args:
            hypothesis_id: ID da hipótese
            version_number: Número da versão

        Returns:
            Instância de HypothesisVersion ou None
        """
        doc = await self.collection.find_one(
            {
                "hypothesis_id": hypothesis_id,
                "version_number": version_number,
            }
        )
        if not doc:
            return None

        return self._doc_to_model(doc)

    async def list_versions(
        self,
        hypothesis_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> list[HypothesisVersion]:
        """
        Lista todas as versões de uma hipótese.

        Args:
            hypothesis_id: ID da hipótese
            limit: Limite de resultados
            skip: Resultados a pular

        Returns:
            Lista de versões ordenadas (mais recente primeiro)
        """
        cursor = (
            self.collection.find({"hypothesis_id": hypothesis_id})
            .sort("version_number", DESCENDING)
            .skip(skip)
            .limit(limit)
        )

        versions = []
        async for doc in cursor:
            versions.append(self._doc_to_model(doc))

        return versions

    async def get_latest_version(
        self,
        hypothesis_id: str,
    ) -> HypothesisVersion | None:
        """
        Busca versão mais recente de uma hipótese.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            Versão mais recente ou None
        """
        doc = await self.collection.find_one(
            {"hypothesis_id": hypothesis_id}, sort=[("version_number", DESCENDING)]
        )
        if not doc:
            return None

        return self._doc_to_model(doc)

    async def compare_versions(
        self,
        hypothesis_id: str,
        from_version: int,
        to_version: int,
    ) -> VersionDiff | None:
        """
        Compara duas versões de uma hipótese.

        Args:
            hypothesis_id: ID da hipótese
            from_version: Versão de origem
            to_version: Versão de destino

        Returns:
            VersionDiff com as diferenças ou None
        """
        from_v = await self.get_version(hypothesis_id, from_version)
        to_v = await self.get_version(hypothesis_id, to_version)

        if not from_v or not to_v:
            return None

        return VersionDiff.compare(
            from_snapshot=from_v.snapshot,
            to_snapshot=to_v.snapshot,
        )

    async def count_versions(self, hypothesis_id: str) -> int:
        """
        Conta versões de uma hipótese.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            Número de versões
        """
        return await self.collection.count_documents({"hypothesis_id": hypothesis_id})

    async def cleanup_old_versions(
        self,
        hypothesis_id: str,
        keep: int | None = None,
    ) -> int:
        """
        Remove versões antigas mantendo as N mais recentes.

        Args:
            hypothesis_id: ID da hipótese
            keep: Quantas versões manter (usa settings se None)

        Returns:
            Número de versões removidas
        """
        keep = keep or self.settings.max_versions_per_hypothesis

        total = await self.count_versions(hypothesis_id)
        if total <= keep:
            return 0

        # Buscar versões a remover (as mais antigas além do limite)
        cursor = (
            self.collection.find({"hypothesis_id": hypothesis_id})
            .sort("version_number", ASCENDING)
            .limit(total - keep)
        )

        versions_to_remove = []
        async for doc in cursor:
            versions_to_remove.append(doc["_id"])

        if not versions_to_remove:
            return 0

        result = await self.collection.delete_many({"_id": {"$in": versions_to_remove}})

        logger.info(
            "old_versions_cleaned",
            hypothesis_id=hypothesis_id,
            removed_count=result.deleted_count,
        )
        return result.deleted_count

    async def get_all_hypotheses_with_versions(
        self,
        min_versions: int = 2,
    ) -> list[str]:
        """
        Lista hipóteses que têm múltiplas versões.

        Args:
            min_versions: Número mínimo de versões

        Returns:
            Lista de hypothesis_ids
        """
        pipeline = [
            {"$group": {"_id": "$hypothesis_id", "version_count": {"$sum": 1}}},
            {"$match": {"version_count": {"$gte": min_versions}}},
            {"$sort": {"version_count": DESCENDING}},
        ]

        hypothesis_ids = []
        async for doc in self.collection.aggregate(pipeline):
            hypothesis_ids.append(doc["_id"])

        return hypothesis_ids

    def _doc_to_model(self, doc: dict[str, Any]) -> HypothesisVersion:
        """Converte documento MongoDB para modelo Pydantic."""
        if "_id" in doc:
            doc["id"] = doc["_id"]

        # Remover _id para não duplicar
        doc.pop("_id", None)

        return HypothesisVersion(**doc)


# Singleton instance
_version_repository: HypothesisVersionRepository | None = None


async def get_version_repository(
    client: AsyncIOMotorClient,
    settings: Settings | None = None,
) -> HypothesisVersionRepository:
    """Retorna instância singleton do repository de versões."""
    global _version_repository
    if _version_repository is None:
        _version_repository = HypothesisVersionRepository(client, settings)
        await _version_repository.create_indexes()
    return _version_repository
