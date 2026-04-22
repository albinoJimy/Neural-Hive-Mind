"""MongoDB repository para hipóteses."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from src.config.settings import Settings, get_settings
from src.models.hypothesis import (
    Hypothesis,
    HypothesisFilter,
    HypothesisPriority,
    HypothesisStatus,
    PyObjectId,
)
from src.models.workflow import WorkflowTransition

logger = logging.getLogger(__name__)
UTC = UTC


class HypothesisRepository:
    """Repository para gerenciar hipóteses no MongoDB."""

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
        self.database: AsyncIOMotorDatabase = client[self.settings.mongodb_database]
        self.collection = self.database[self.settings.mongodb_hypotheses_collection]
        self._transition_history_collection = self.database["hypothesis_transitions"]

    async def create_indexes(self) -> None:
        """Cria índices para a coleção de hipóteses."""
        # Índices principais
        await self.collection.create_index(
            [("hypothesis_id", ASCENDING)], unique=True, name="idx_hypothesis_id"
        )
        await self.collection.create_index([("status", ASCENDING)], name="idx_status")
        await self.collection.create_index([("created_at", DESCENDING)], name="idx_created_at")
        await self.collection.create_index([("updated_at", DESCENDING)], name="idx_updated_at")
        await self.collection.create_index([("author", ASCENDING)], name="idx_author")
        await self.collection.create_index([("priority", ASCENDING)], name="idx_priority")

        # Índices compostos para queries comuns
        await self.collection.create_index(
            [("status", ASCENDING), ("created_at", DESCENDING)], name="idx_status_created"
        )
        await self.collection.create_index(
            [("author", ASCENDING), ("created_at", DESCENDING)], name="idx_author_created"
        )
        await self.collection.create_index([("tags", ASCENDING)], name="idx_tags")

        # Índice para busca texto
        await self.collection.create_index(
            [("title", "text"), ("description", "text")],
            name="idx_text_search",
            default_language="english",
        )

        # Índices para transições
        await self._transition_history_collection.create_index(
            [("hypothesis_id", ASCENDING), ("transitioned_at", DESCENDING)],
            name="idx_hypothesis_transitions",
        )

        logger.info("hypothesis_indexes_created")

    async def create(self, hypothesis: Hypothesis) -> Hypothesis:
        """
        Cria nova hipótese.

        Args:
            hypothesis: Instância de Hypothesis

        Returns:
            Hipótese criada com _id preenchido
        """
        doc = hypothesis.to_dict()
        doc["created_at"] = datetime.now(UTC)
        doc["updated_at"] = datetime.now(UTC)

        result = await self.collection.insert_one(doc)

        hypothesis.id = PyObjectId(result.inserted_id)
        logger.info(
            "hypothesis_created",
            hypothesis_id=hypothesis.hypothesis_id,
            title=hypothesis.title,
        )
        return hypothesis

    async def get_by_id(self, hypothesis_id: str) -> Hypothesis | None:
        """
        Busca hipótese por ID.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            Instância de Hypothesis ou None
        """
        doc = await self.collection.find_one({"hypothesis_id": hypothesis_id})
        if not doc:
            return None

        return self._doc_to_model(doc)

    async def get_by_object_id(self, obj_id: str | ObjectId) -> Hypothesis | None:
        """
        Busca hipótese por ObjectId do MongoDB.

        Args:
            obj_id: ObjectId (string ou ObjectId)

        Returns:
            Instância de Hypothesis ou None
        """
        if isinstance(obj_id, str):
            try:
                obj_id = ObjectId(obj_id)
            except Exception:
                return None

        doc = await self.collection.find_one({"_id": obj_id})
        if not doc:
            return None

        return self._doc_to_model(doc)

    async def list_by_filters(
        self,
        filters: HypothesisFilter | None = None,
    ) -> dict[str, Any]:
        """
        Lista hipóteses com filtros.

        Args:
            filters: Filtros de busca

        Returns:
            Dict com total, offset, limit e items
        """
        filters = filters or HypothesisFilter()
        query = self._build_query(filters)

        # Contar total
        total = await self.collection.count_documents(query)

        # Construir sort
        sort_order = ASCENDING if filters.sort_order == 1 else DESCENDING
        cursor = (
            self.collection.find(query)
            .sort(filters.sort_by, sort_order)
            .skip(filters.offset)
            .limit(filters.limit)
        )

        items = []
        async for doc in cursor:
            items.append(self._doc_to_model(doc))

        return {
            "total": total,
            "offset": filters.offset,
            "limit": filters.limit,
            "items": items,
        }

    async def update(
        self,
        hypothesis_id: str,
        updates: dict[str, Any],
    ) -> Hypothesis | None:
        """
        Atualiza hipótese.

        Args:
            hypothesis_id: ID da hipótese
            updates: Dicionário de campos para atualizar

        Returns:
            Hipótese atualizada ou None se não encontrada
        """
        updates["updated_at"] = datetime.now(UTC)

        result = await self.collection.update_one(
            {"hypothesis_id": hypothesis_id}, {"$set": updates}
        )

        if result.modified_count == 0:
            return None

        return await self.get_by_id(hypothesis_id)

    async def transition_status(
        self,
        hypothesis_id: str,
        new_status: HypothesisStatus,
        transitioned_by: str,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Hypothesis | None, WorkflowTransition | None]:
        """
        Atualiza status de hipótese e registra transição.

        Args:
            hypothesis_id: ID da hipótese
            new_status: Novo status
            transitioned_by: Quem fez a transição
            reason: Razão da transição
            metadata: Metadados adicionais

        Returns:
            Tupla (hipótese atualizada, transição registrada)
        """
        hypothesis = await self.get_by_id(hypothesis_id)
        if not hypothesis:
            return None, None

        old_status = hypothesis.status

        # Criar registro de transição
        transition = WorkflowTransition(
            from_status=old_status,
            to_status=new_status,
            transitioned_by=transitioned_by,
            reason=reason,
            metadata=metadata or {},
        )

        # Atualizar campos baseados no status
        status_updates = {
            "status": new_status,
            "updated_at": datetime.now(UTC),
        }

        # Atualizar timestamps específicos
        if new_status == HypothesisStatus.PROPOSED:
            status_updates["proposed_at"] = datetime.now(UTC)
        elif new_status == HypothesisStatus.APPROVED:
            status_updates["approved_at"] = datetime.now(UTC)
            status_updates["approved_by"] = transitioned_by
        elif new_status == HypothesisStatus.IN_TESTING:
            status_updates["testing_started_at"] = datetime.now(UTC)
        elif new_status == HypothesisStatus.COMPLETED:
            status_updates["completed_at"] = datetime.now(UTC)

        # Atualizar hipótese
        hypothesis = await self.update(hypothesis_id, status_updates)
        if not hypothesis:
            return None, None

        # Registrar transição
        await self._record_transition(hypothesis_id, transition)

        return hypothesis, transition

    async def set_experiment_id(
        self,
        hypothesis_id: str,
        experiment_id: str,
    ) -> bool:
        """
        Associa experimento à hipótese.

        Args:
            hypothesis_id: ID da hipótese
            experiment_id: ID do experimento

        Returns:
            True se atualizado com sucesso
        """
        result = await self.collection.update_one(
            {"hypothesis_id": hypothesis_id},
            {
                "$set": {
                    "experiment_id": experiment_id,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count > 0

    async def set_results(
        self,
        hypothesis_id: str,
        results: dict[str, Any],
    ) -> bool:
        """
        Define resultados do experimento.

        Args:
            hypothesis_id: ID da hipótese
            results: Dicionário de resultados

        Returns:
            True se atualizado com sucesso
        """
        result = await self.collection.update_one(
            {"hypothesis_id": hypothesis_id},
            {
                "$set": {
                    "results": results,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count > 0

    async def archive(self, hypothesis_id: str) -> bool:
        """
        Arquiva hipótese.

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            True se arquivada com sucesso
        """
        result = await self.collection.update_one(
            {"hypothesis_id": hypothesis_id},
            {
                "$set": {
                    "status": HypothesisStatus.ARCHIVED.value,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count > 0

    async def delete(self, hypothesis_id: str) -> bool:
        """
        Remove hipótese (soft delete via arquivo).

        Args:
            hypothesis_id: ID da hipótese

        Returns:
            True se removida com sucesso
        """
        return await self.archive(hypothesis_id)

    async def count_by_status(self) -> dict[str, int]:
        """
        Conta hipóteses por status.

        Returns:
            Dict com contagem por status
        """
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]

        result = {}
        async for doc in self.collection.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]

        # Garantir todos os status
        for status in HypothesisStatus:
            if status.value not in result:
                result[status.value] = 0

        return result

    async def get_aggregations(self) -> dict[str, Any]:
        """
        Retorna agregações para dashboard.

        Returns:
            Dict com métricas agregadas
        """
        total = await self.collection.count_documents({})

        # Contagem por status
        status_counts = await self.count_by_status()

        # Contagem por prioridade
        priority_pipeline = [{"$group": {"_id": "$priority", "count": {"$sum": 1}}}]
        priority_counts = {}
        async for doc in self.collection.aggregate(priority_pipeline):
            priority_counts[doc["_id"]] = doc["count"]

        # Hipóteses com experimentos em andamento
        in_testing = await self.collection.count_documents(
            {"status": HypothesisStatus.IN_TESTING.value}
        )

        # Hipóteses aguardando aprovação
        pending_approval = await self.collection.count_documents(
            {"status": HypothesisStatus.PROPOSED.value}
        )

        return {
            "total": total,
            "by_status": status_counts,
            "by_priority": priority_counts,
            "in_testing": in_testing,
            "pending_approval": pending_approval,
        }

    async def get_transition_history(
        self,
        hypothesis_id: str,
        limit: int = 50,
    ) -> list[WorkflowTransition]:
        """
        Retorna histórico de transições de uma hipótese.

        Args:
            hypothesis_id: ID da hipótese
            limit: Limite de registros

        Returns:
            Lista de transições
        """
        cursor = (
            self._transition_history_collection.find({"hypothesis_id": hypothesis_id})
            .sort("transitioned_at", DESCENDING)
            .limit(limit)
        )

        transitions = []
        async for doc in cursor:
            transitions.append(
                WorkflowTransition(
                    from_status=HypothesisStatus(doc["from_status"]),
                    to_status=HypothesisStatus(doc["to_status"]),
                    transitioned_at=doc["transitioned_at"],
                    transitioned_by=doc["transitioned_by"],
                    reason=doc.get("reason", ""),
                    metadata=doc.get("metadata", {}),
                )
            )

        return transitions

    def _build_query(self, filters: HypothesisFilter) -> dict[str, Any]:
        """Constrói query MongoDB a partir dos filtros."""
        query = {}

        if filters.status:
            query["status"] = filters.status.value

        if filters.priority:
            query["priority"] = filters.priority.value

        if filters.author:
            query["author"] = filters.author

        if filters.reviewer:
            query["reviewers"] = filters.reviewer

        if filters.tags:
            query["tags"] = {"$in": filters.tags}

        if filters.requires_experiment is not None:
            query["requires_experiment"] = filters.requires_experiment

        if filters.has_experiment is not None:
            if filters.has_experiment:
                query["experiment_id"] = {"$ne": None}
            else:
                query["experiment_id"] = None

        if filters.outcome:
            query["results.outcome"] = filters.outcome

        if filters.created_after:
            query["created_at"] = {"$gte": filters.created_after}

        if filters.created_before:
            if "created_at" not in query:
                query["created_at"] = {}
            query["created_at"]["$lte"] = filters.created_before

        if filters.search_text:
            query["$text"] = {"$search": filters.search_text}

        return query

    def _doc_to_model(self, doc: dict[str, Any]) -> Hypothesis:
        """Converte documento MongoDB para modelo Pydantic."""
        # Converter ObjectId
        if "_id" in doc:
            doc["id"] = PyObjectId(doc["_id"])

        # Converter enums de string
        if "status" in doc and isinstance(doc["status"], str):
            doc["status"] = HypothesisStatus(doc["status"])

        if "priority" in doc and isinstance(doc["priority"], str):
            doc["priority"] = HypothesisPriority(doc["priority"])

        # Remover _id do dict para não duplicar
        doc.pop("_id", None)

        return Hypothesis(**doc)

    async def _record_transition(
        self,
        hypothesis_id: str,
        transition: WorkflowTransition,
    ) -> None:
        """Registra transição no histórico."""
        await self._transition_history_collection.insert_one(
            {
                "hypothesis_id": hypothesis_id,
                "from_status": transition.from_status.value,
                "to_status": transition.to_status.value,
                "transitioned_at": transition.transitioned_at,
                "transitioned_by": transition.transitioned_by,
                "reason": transition.reason,
                "metadata": transition.metadata,
            }
        )


# Singleton instance
_repository: HypothesisRepository | None = None


async def get_repository(
    client: AsyncIOMotorClient,
    settings: Settings | None = None,
) -> HypothesisRepository:
    """Retorna instância singleton do repository."""
    global _repository
    if _repository is None:
        _repository = HypothesisRepository(client, settings)
        await _repository.create_indexes()
    return _repository
