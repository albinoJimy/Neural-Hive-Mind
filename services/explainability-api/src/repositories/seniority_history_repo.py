"""
Seniority History Repository.

Repository para tracking de mudancas de senioridade de especialistas.
"""

from datetime import UTC, datetime
from typing import Any, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger(__name__)


class SeniorityHistoryRepository:
    """Repository for senioridade change history."""

    def __init__(self, mongo_client: AsyncIOMotorClient):
        self.db = mongo_client["neural_hive"]
        self.collection = self.db.seniority_history

    async def save_change(
        self,
        specialist_id: str,
        specialist_name: str,
        domain: str,
        previous_level: str,
        previous_multiplier: float,
        new_level: str,
        new_multiplier: float,
        changed_by: str,
        change_reason: str,
        decision_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> str:
        """Save a senioridade change."""
        doc = {
            "specialist_id": specialist_id,
            "specialist_name": specialist_name,
            "domain": domain,
            "changed_at": datetime.now(UTC),
            "previous_level": previous_level,
            "previous_multiplier": previous_multiplier,
            "new_level": new_level,
            "new_multiplier": new_multiplier,
            "changed_by": changed_by,
            "change_reason": change_reason,
            "decision_id": decision_id,
            "plan_id": plan_id,
        }

        result = await self.collection.insert_one(doc)
        logger.info(
            "seniority_change_saved",
            specialist_id=specialist_id,
            new_level=new_level,
            doc_id=str(result.inserted_id),
        )
        return str(result.inserted_id)

    async def get_history(self, specialist_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get history for a specialist."""
        cursor = (
            self.collection.find({"specialist_id": specialist_id})
            .sort("changed_at", -1)
            .limit(limit)
        )

        return await self._parse_cursor(cursor)

    async def get_recent_changes(
        self, specialists: list[str], since: datetime, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get recent changes for multiple specialists."""
        cursor = (
            self.collection.find(
                {"specialist_id": {"$in": specialists}, "changed_at": {"$gte": since}}
            )
            .sort("changed_at", -1)
            .limit(limit)
        )

        return await self._parse_cursor(cursor)

    async def get_by_domain(
        self, domain: str, since: Optional[datetime] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get changes by domain."""
        query = {"domain": domain}
        if since:
            query["changed_at"] = {"$gte": since}

        cursor = self.collection.find(query).sort("changed_at", -1).limit(limit)
        return await self._parse_cursor(cursor)

    async def _parse_cursor(self, cursor) -> list[dict[str, Any]]:
        """Parse cursor to list, removing _id."""
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results
