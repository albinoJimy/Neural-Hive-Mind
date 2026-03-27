"""Repositório para histórico de evolução."""

from typing import List
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from src.models.evolution import EvolutionHistory
from src.repositories.base import BaseRepository
from src.config.settings import get_settings


class EvolutionRepository(BaseRepository[EvolutionHistory]):
    """Repositório para histórico de evolução."""

    def __init__(self):
        """Inicializa repositório de evolução."""
        settings = get_settings()
        self.client = AsyncIOMotorClient(settings.mongodb.url)
        self.db = self.client[settings.mongodb.database]
        self.collection = self.db[settings.mongodb.collection_evolution]

    async def create(self, history: EvolutionHistory) -> str:
        """Cria nova entrada de histórico."""
        doc = history.model_dump(by_alias=True, exclude_none=True)
        doc["_id"] = history.history_id
        doc["created_at"] = datetime.now(timezone.utc)

        try:
            await self.collection.insert_one(doc)
            return history.history_id
        except Exception as e:
            raise ValueError(f"História com ID {history.history_id} já existe") from e

    def _doc_to_model(self, doc: dict) -> EvolutionHistory:
        """Converte documento MongoDB para modelo Pydantic."""
        doc.pop("_id", None)
        return EvolutionHistory(**doc)

    async def get_by_plan_id(
        self, plan_id: str, limit: int = 10
    ) -> List[EvolutionHistory]:
        """Busca histórico de um plano."""
        cursor = (
            self.collection.find({"plan_id": plan_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def get_recent(self, limit: int = 50) -> List[EvolutionHistory]:
        """Busca entradas recentes."""
        cursor = self.collection.find().sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def count_drifts_by_plan(self, plan_id: str) -> int:
        """Conta divergências registradas para um plano."""
        pipeline = [
            {"$match": {"plan_id": plan_id}},
            {"$unwind": "$drifts"},
            {"$count": "total"},
        ]
        cursor = self.collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        if result:
            return result[0].get("total", 0)
        return 0
