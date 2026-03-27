"""Repositório para planos arquiteturais."""

from typing import List, Optional
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from src.models.architecture import ArchitecturePlan, ArchitectureType
from src.repositories.base import BaseRepository
from src.config.settings import get_settings


class ArchitectureRepository(BaseRepository[ArchitecturePlan]):
    """Repositório para planos de arquitetura."""

    def __init__(self):
        """Inicializa repositório de planos arquiteturais."""
        settings = get_settings()
        self.client = AsyncIOMotorClient(settings.mongodb.url)
        self.db = self.client[settings.mongodb.database]
        self.collection = self.db[settings.mongodb.collection_architecture]

    async def create(self, plan: ArchitecturePlan) -> str:
        """Cria novo plano arquitetural."""
        # Usar plan_id como _id
        doc = plan.model_dump(by_alias=True, exclude_none=True)
        doc["_id"] = plan.plan_id
        doc["created_at"] = datetime.now(timezone.utc)

        try:
            await self.collection.insert_one(doc)
            return plan.plan_id
        except Exception as e:
            # Documento já existe
            raise ValueError(f"Plano com ID {plan.plan_id} já existe") from e

    def _doc_to_model(self, doc: dict) -> ArchitecturePlan:
        """Converte documento MongoDB para modelo Pydantic."""
        doc.pop("_id", None)
        return ArchitecturePlan(**doc)

    async def get_by_plan_id(self, plan_id: str) -> Optional[ArchitecturePlan]:
        """Busca plano por plan_id."""
        doc = await self.collection.find_one({"_id": plan_id})
        if doc:
            doc["plan_id"] = plan_id
            return self._doc_to_model(doc)
        return None

    async def get_by_cognitive_plan_id(
        self, cognitive_plan_id: str
    ) -> List[ArchitecturePlan]:
        """Busca planos por cognitive_plan_id."""
        cursor = self.collection.find({"cognitive_plan_id": cognitive_plan_id})
        docs = await cursor.to_list(length=100)
        return [self._doc_to_model(doc) for doc in docs]

    async def list_by_type(
        self, arch_type: ArchitectureType, limit: int = 50
    ) -> List[ArchitecturePlan]:
        """Lista planos por tipo de arquitetura."""
        cursor = self.collection.find({"architecture_type": arch_type.value}).limit(
            limit
        )
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_model(doc) for doc in docs]

    async def update_rationale(self, plan_id: str, rationale: str) -> bool:
        """Atualiza rationale de um plano."""
        result = await self.collection.update_one(
            {"_id": plan_id},
            {
                "$set": {
                    "rationale": rationale,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0
