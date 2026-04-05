"""
Repositório MongoDB para Feature Flags.

Implementa CRUD completo com:
- Operações assíncronas usando motor/mongo
- Tratamento de erros com RepositoryError
- Suporte a filtros e paginação
- Operações em lote
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from pymongo.errors import PyMongoError

from src.models.feature_flag import FeatureFlag

logger = structlog.get_logger(__name__)


class RepositoryError(Exception):
    """Erro base para operações do repositório."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class FeatureFlagRepository:
    """
    Repositório MongoDB para Feature Flags.

    Fornece operações CRUD para gerenciamento de flags.
    """

    def __init__(self, db, collection_name: str = "feature_flags"):
        """
        Inicializa repositório.

        Args:
            db: Instância de database MongoDB (motor)
            collection_name: Nome da coleção (default: feature_flags)
        """
        self._db = db
        self.collection_name = collection_name

    @property
    def _collection(self):
        """Retorna coleção MongoDB."""
        return self._db[self.collection_name]

    async def create(self, flag: FeatureFlag) -> FeatureFlag:
        """
        Cria nova feature flag.

        Args:
            flag: Instância de FeatureFlag

        Returns:
            Flag criada com timestamps atualizados

        Raises:
            RepositoryError: Se já existe flag com mesmo nome ou erro MongoDB
        """
        try:
            flag_data = flag.to_dict()
            flag_data["_id"] = flag.name  # Usar nome como ID único

            await self._collection.insert_one(flag_data)

            logger.info(
                "feature_flag_created",
                name=flag.name,
                enabled=flag.enabled,
                strategy=flag.rollout_strategy.type.value,
            )

            return flag

        except PyMongoError as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                logger.warning("feature_flag_duplicate", name=flag.name)
                raise RepositoryError(
                    f"Feature flag '{flag.name}' já existe", original_error=e
                ) from e
            logger.error(
                "feature_flag_create_error",
                name=flag.name,
                error=str(e),
            )
            raise RepositoryError(f"Erro ao criar flag: {e}", original_error=e) from e

    async def get_by_name(self, name: str) -> FeatureFlag | None:
        """
        Busca flag por nome.

        Args:
            name: Nome da flag

        Returns:
            Instância de FeatureFlag ou None se não encontrada

        Raises:
            RepositoryError: Em caso de erro MongoDB
        """
        try:
            document = await self._collection.find_one({"_id": name})

            if not document:
                return None

            # Remover _id para não conflitar com campo name
            document.pop("_id", None)

            return FeatureFlag.from_dict(document)

        except PyMongoError as e:
            logger.error(
                "feature_flag_get_error",
                name=name,
                error=str(e),
            )
            raise RepositoryError(f"Erro ao buscar flag: {e}", original_error=e) from e
        except ValueError:
            # Erro de desserialização - retornar None
            logger.warning("feature_flag_deserialize_error", name=name)
            return None

    async def update(self, name: str, flag: FeatureFlag, partial: bool = False) -> bool:
        """
        Atualiza flag existente.

        Args:
            name: Nome da flag a atualizar
            flag: Novos dados
            partial: Se True, apenas atualiza campos fornecidos

        Returns:
            True se atualizou, False se não encontrou

        Raises:
            RepositoryError: Em caso de erro MongoDB
        """
        try:
            flag_data = flag.to_dict()

            # Garantir que nome não muda
            flag_data["name"] = name

            if partial:
                # Atualização parcial: remover campos não fornecidos
                update_doc = {"$set": flag_data}
            else:
                # Atualização completa: substituir documento
                update_doc = {"$set": flag_data}

            result = await self._collection.update_one({"_id": name}, update_doc)

            if result.modified_count > 0:
                logger.info("feature_flag_updated", name=name)
                return True

            return False

        except PyMongoError as e:
            logger.error(
                "feature_flag_update_error",
                name=name,
                error=str(e),
            )
            raise RepositoryError(
                f"Erro ao atualizar flag: {e}", original_error=e
            ) from e

    async def delete(self, name: str) -> bool:
        """
        Remove flag.

        Args:
            name: Nome da flag a remover

        Returns:
            True se removeu, False se não encontrou

        Raises:
            RepositoryError: Em caso de erro MongoDB
        """
        try:
            result = await self._collection.delete_one({"_id": name})

            if result.deleted_count > 0:
                logger.info("feature_flag_deleted", name=name)
                return True

            return False

        except PyMongoError as e:
            logger.error(
                "feature_flag_delete_error",
                name=name,
                error=str(e),
            )
            raise RepositoryError(f"Erro ao deletar flag: {e}", original_error=e) from e

    async def list(
        self,
        enabled_only: bool | None = None,
        tags: list[str] | None = None,
        owner: str | None = None,
        skip: int = 0,
        limit: int | None = None,
    ) -> list[FeatureFlag]:
        """
        Lista flags com filtros opcionais.

        Args:
            enabled_only: Filtrar apenas habilitadas/desabilitadas
            tags: Filtrar por tags
            owner: Filtrar por owner
            skip: Pular N resultados (paginação)
            limit: Limitar a N resultados

        Returns:
            Lista de FeatureFlag
        """
        try:
            query = {}

            if enabled_only is not None:
                query["enabled"] = enabled_only

            if tags:
                query["tags"] = {"$in": tags}

            if owner:
                query["owner"] = owner

            cursor = self._collection.find(query)

            # Aplicar paginação
            if skip:
                cursor = cursor.skip(skip)
            if limit is not None:
                cursor = cursor.limit(limit)

            documents = await cursor.to_list(length=limit or 1000)

            flags = []
            for doc in documents:
                doc.pop("_id", None)
                try:
                    flags.append(FeatureFlag.from_dict(doc))
                except ValueError:
                    # Skip documentos inválidos
                    logger.warning(
                        "feature_flag_invalid_document", name=doc.get("name")
                    )

            return flags

        except PyMongoError as e:
            logger.error(
                "feature_flag_list_error",
                query=query,
                error=str(e),
            )
            raise RepositoryError(f"Erro ao listar flags: {e}", original_error=e) from e

    async def enable(self, name: str) -> bool:
        """
        Habilita flag.

        Args:
            name: Nome da flag

        Returns:
            True se habilitou, False se não encontrou
        """
        try:
            result = await self._collection.update_one(
                {"_id": name},
                {
                    "$set": {
                        "enabled": True,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                },
            )

            if result.modified_count > 0:
                logger.info("feature_flag_enabled", name=name)
                return True

            return False

        except PyMongoError as e:
            logger.error("feature_flag_enable_error", name=name, error=str(e))
            raise RepositoryError(
                f"Erro ao habilitar flag: {e}", original_error=e
            ) from e

    async def disable(self, name: str) -> bool:
        """
        Desabilita flag.

        Args:
            name: Nome da flag

        Returns:
            True se desabilitou, False se não encontrou
        """
        try:
            result = await self._collection.update_one(
                {"_id": name},
                {
                    "$set": {
                        "enabled": False,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                },
            )

            if result.modified_count > 0:
                logger.info("feature_flag_disabled", name=name)
                return True

            return False

        except PyMongoError as e:
            logger.error("feature_flag_disable_error", name=name, error=str(e))
            raise RepositoryError(
                f"Erro ao desabilitar flag: {e}", original_error=e
            ) from e

    async def exists(self, name: str) -> bool:
        """
        Verifica se flag existe.

        Args:
            name: Nome da flag

        Returns:
            True se existe, False caso contrário
        """
        try:
            count = await self._collection.count_documents({"_id": name}, limit=1)
            return count > 0

        except PyMongoError as e:
            logger.error("feature_flag_exists_error", name=name, error=str(e))
            return False

    async def count(self, enabled_only: bool | None = None) -> int:
        """
        Conta flags no repositório.

        Args:
            enabled_only: Contar apenas habilitadas/desabilitadas

        Returns:
            Número de flags
        """
        try:
            query = {}
            if enabled_only is not None:
                query["enabled"] = enabled_only

            return await self._collection.count_documents(query)

        except PyMongoError as e:
            logger.error("feature_flag_count_error", error=str(e))
            return 0

    async def bulk_enable(self, names: list[str]) -> int:
        """
        Habilita múltiplas flags.

        Args:
            names: Lista de nomes de flags

        Returns:
            Número de flags habilitadas
        """
        try:
            result = await self._collection.update_many(
                {"_id": {"$in": names}},
                {
                    "$set": {
                        "enabled": True,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                },
            )

            logger.info("feature_flags_bulk_enabled", count=result.modified_count)
            return result.modified_count

        except PyMongoError as e:
            logger.error("feature_flag_bulk_enable_error", error=str(e))
            raise RepositoryError(f"Erro em bulk enable: {e}", original_error=e) from e

    async def bulk_disable(self, names: list[str]) -> int:
        """
        Desabilita múltiplas flags.

        Args:
            names: Lista de nomes de flags

        Returns:
            Número de flags desabilitadas
        """
        try:
            result = await self._collection.update_many(
                {"_id": {"$in": names}},
                {
                    "$set": {
                        "enabled": False,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                },
            )

            logger.info("feature_flags_bulk_disabled", count=result.modified_count)
            return result.modified_count

        except PyMongoError as e:
            logger.error("feature_flag_bulk_disable_error", error=str(e))
            raise RepositoryError(f"Erro em bulk disable: {e}", original_error=e) from e

    async def bulk_delete(self, names: list[str]) -> int:
        """
        Remove múltiplas flags.

        Args:
            names: Lista de nomes de flags

        Returns:
            Número de flags removidas
        """
        try:
            result = await self._collection.delete_many({"_id": {"$in": names}})

            logger.info("feature_flags_bulk_deleted", count=result.deleted_count)
            return result.deleted_count

        except PyMongoError as e:
            logger.error("feature_flag_bulk_delete_error", error=str(e))
            raise RepositoryError(f"Erro em bulk delete: {e}", original_error=e) from e
