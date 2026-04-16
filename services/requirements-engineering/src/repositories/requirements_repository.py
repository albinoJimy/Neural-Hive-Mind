"""Repositório para persistência de requisitos."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from structlog import get_logger

from src.db.mongodb import get_mongodb
from src.models.requirements import (
    Requirement,
    RequirementCreate,
    RequirementUpdate,
    RequirementStatus,
    RequirementType,
    RequirementsSet,
)

logger = get_logger(__name__)


class RequirementsRepository:
    """Repositório para operações de CRUD de requisitos."""

    def __init__(self):
        self._mongodb = None

    async def _get_db(self):
        """Obtém conexão MongoDB."""
        if self._mongodb is None:
            self._mongodb = await get_mongodb()
        return self._mongodb

    async def create(self, requirement_data: RequirementCreate) -> Requirement:
        """Cria um novo requisito."""
        import uuid

        db = await self._get_db()

        req_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"

        doc = {
            "id": req_id,
            "title": requirement_data.title,
            "description": requirement_data.description,
            "requirement_type": requirement_data.requirement_type,
            "priority": requirement_data.priority,
            "status": RequirementStatus.DRAFT,
            "rationale": requirement_data.rationale,
            "acceptance_criteria_ids": [],
            "user_story_ids": [],
            "dependencies": [],
            "conflicts": [],
            "tags": requirement_data.tags,
            "metadata": {},
            "cognitive_plan_id": requirement_data.cognitive_plan_id,
            "architecture_plan_id": requirement_data.architecture_plan_id,
            "created_at": datetime.utcnow(),
            "updated_at": None,
            "version": 1,
        }

        await db.requirements_collection.insert_one(doc)

        logger.info("requirement_created", id=req_id, title=requirement_data.title)

        return Requirement(**doc)

    async def get_by_id(self, requirement_id: str) -> Optional[Requirement]:
        """Busca requisito por ID."""
        db = await self._get_db()
        doc = await db.requirements_collection.find_one({"id": requirement_id})

        if doc:
            doc.pop("_id", None)
            return Requirement(**doc)
        return None

    async def list(
        self,
        priority: Optional[str] = None,
        req_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> tuple[List[Requirement], int]:
        """Lista requisitos com filtros."""
        db = await self._get_db()

        filters = {}
        if priority:
            filters["priority"] = priority
        if req_type:
            filters["requirement_type"] = req_type
        if status:
            filters["status"] = status

        cursor = (
            db.requirements_collection.find(filters)
            .skip(skip)
            .limit(limit)
            .sort("created_at", -1)
        )

        docs = await cursor.to_list(length=limit)
        total = await db.requirements_collection.count_documents(filters)

        requirements = []
        for doc in docs:
            doc.pop("_id", None)
            requirements.append(Requirement(**doc))

        return requirements, total

    async def update(self, requirement_id: str, update_data: RequirementUpdate) -> Optional[Requirement]:
        """Atualiza um requisito."""
        db = await self._get_db()

        # Construir update dict apenas com campos não-None
        update_dict = {
            k: v for k, v in update_data.model_dump(exclude_unset=True).items() if v is not None
        }

        if not update_dict:
            return await self.get_by_id(requirement_id)

        update_dict["updated_at"] = datetime.utcnow()

        result = await db.requirements_collection.update_one(
            {"id": requirement_id}, {"$set": update_dict}
        )

        if result.modified_count:
            logger.info("requirement_updated", id=requirement_id)
            return await self.get_by_id(requirement_id)

        return None

    async def delete(self, requirement_id: str) -> bool:
        """Deleta um requisito."""
        db = await self._get_db()
        result = await db.requirements_collection.delete_one({"id": requirement_id})

        if result.deleted_count:
            logger.info("requirement_deleted", id=requirement_id)
            return True
        return False

    async def save_set(self, requirements_set: RequirementsSet) -> RequirementsSet:
        """Salva um conjunto de requisitos."""
        db = await self._get_db()

        doc = requirements_set.model_dump()
        doc["created_at"] = datetime.utcnow()

        await db.requirements_sets_collection.insert_one(doc)

        logger.info("requirements_set_saved", id=requirements_set.id)

        return requirements_set

    async def get_set_by_id(self, set_id: str) -> Optional[RequirementsSet]:
        """Busca conjunto de requisitos por ID."""
        db = await self._get_db()
        doc = await db.requirements_sets_collection.find_one({"id": set_id})

        if doc:
            doc.pop("_id", None)
            return RequirementsSet(**doc)
        return None

    async def get_by_cognitive_plan(self, plan_id: str) -> List[Requirement]:
        """Busca requisitos por CognitivePlan ID."""
        db = await self._get_db()
        cursor = db.requirements_collection.find({"cognitive_plan_id": plan_id})

        docs = await cursor.to_list(length=None)
        requirements = []
        for doc in docs:
            doc.pop("_id", None)
            requirements.append(Requirement(**doc))

        return requirements
