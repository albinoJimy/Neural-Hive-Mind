"""Repository for impact analysis data access."""

from datetime import datetime, timezone
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.config.settings import Settings, get_settings
from src.models.impact import (
    ImpactCategory,
    ImpactDirection,
    ImpactMagnitude,
    ImpactSummary,
)

UTC = timezone.utc
logger = structlog.get_logger()


class ImpactRepository:
    """Repository for experiment impact data."""

    def __init__(
        self,
        database: AsyncIOMotorDatabase,
        settings: Settings | None = None,
    ):
        """Initialize repository.

        Args:
            database: Motor database instance
            settings: Configuration settings
        """
        self.database = database
        self.settings = settings or get_settings()
        self.collection = database[self.settings.mongodb_impacts_collection]

    async def save_impact(self, impact: dict[str, Any]) -> str:
        """Save impact analysis.

        Args:
            impact: Impact document

        Returns:
            Inserted ID
        """
        result = await self.collection.insert_one(impact)
        logger.info("impact_saved", impact_id=impact.get("impact_id"))
        return str(result.inserted_id)

    async def get_impact(self, impact_id: str) -> dict[str, Any] | None:
        """Get impact by ID.

        Args:
            impact_id: Impact ID

        Returns:
            Impact document or None
        """
        return await self.collection.find_one({"impact_id": impact_id})

    async def get_impact_by_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Get latest impact for experiment.

        Args:
            experiment_id: Experiment ID

        Returns:
            Impact document or None
        """
        return await self.collection.find_one(
            {"experiment_id": experiment_id}, sort=[("created_at", -1)]
        )

    async def update_impact(self, impact_id: str, updates: dict[str, Any]) -> bool:
        """Update impact analysis.

        Args:
            impact_id: Impact ID
            updates: Fields to update

        Returns:
            True if updated
        """
        updates["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one({"impact_id": impact_id}, {"$set": updates})
        return result.modified_count > 0

    async def list_impacts(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: int = -1,
    ) -> list[dict[str, Any]]:
        """List impacts.

        Args:
            filters: Query filters
            limit: Max results
            offset: Skip results
            sort_by: Sort field
            sort_order: Sort direction

        Returns:
            List of impacts
        """
        query = filters or {}

        cursor = self.collection.find(query).sort(sort_by, sort_order).skip(offset).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_impact_summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ImpactSummary:
        """Get summary of impacts.

        Args:
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Impact summary
        """
        match_stage: dict[str, Any] = {}
        if start_date or end_date:
            date_filter: dict[str, Any] = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            match_stage["created_at"] = date_filter

        # Total count
        total_count = await self.collection.count_documents(match_stage)

        # Count by direction
        pipeline = [{"$match": match_stage}] if match_stage else []
        pipeline.extend([{"$group": {"_id": "$overall_direction", "count": {"$sum": 1}}}])

        direction_counts = {}
        async for doc in self.collection.aggregate(pipeline):
            direction_counts[doc["_id"]] = doc["count"]

        # Count by magnitude
        pipeline = [{"$match": match_stage}] if match_stage else []
        pipeline.extend([{"$group": {"_id": "$overall_magnitude", "count": {"$sum": 1}}}])

        magnitude_counts = {}
        async for doc in self.collection.aggregate(pipeline):
            magnitude_counts[doc["_id"]] = doc["count"]

        # High magnitude count (critical + high)
        high_magnitude = magnitude_counts.get("critical", 0) + magnitude_counts.get("high", 0)

        # Average confidence
        pipeline = [{"$match": match_stage}] if match_stage else []
        pipeline.extend(
            [{"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence_level"}}}]
        )

        avg_confidence = 0.5
        async for doc in self.collection.aggregate(pipeline):
            avg_confidence = doc.get("avg_confidence", 0.5)

        # Top categories
        pipeline = [{"$match": match_stage}] if match_stage else []
        pipeline.extend(
            [
                {"$unwind": "$categories"},
                {"$group": {"_id": "$categories", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5},
            ]
        )

        top_categories = []
        async for doc in self.collection.aggregate(pipeline):
            try:
                category = ImpactCategory(doc["_id"])
                top_categories.append((category, doc["count"]))
            except ValueError:
                pass

        return ImpactSummary(
            total_experiments=total_count,
            positive_impacts=direction_counts.get("positive", 0),
            negative_impacts=direction_counts.get("negative", 0),
            neutral_impacts=direction_counts.get("neutral", 0),
            high_magnitude_count=high_magnitude,
            average_confidence=avg_confidence,
            top_categories=top_categories,
        )

    async def find_experiments_with_impact(
        self,
        direction: ImpactDirection | None = None,
        magnitude: ImpactMagnitude | None = None,
        categories: list[ImpactCategory] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find experiments matching impact criteria.

        Args:
            direction: Impact direction filter
            magnitude: Impact magnitude filter
            categories: Impact categories filter (any match)
            limit: Max results

        Returns:
            List of matching impacts
        """
        query = {}

        if direction:
            query["overall_direction"] = direction.value
        if magnitude:
            query["overall_magnitude"] = magnitude.value
        if categories:
            query["categories"] = {"$in": [c.value for c in categories]}

        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_time_series(
        self,
        metric_name: str = "confidence_level",
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get time series data for analysis.

        Args:
            metric_name: Metric to extract
            days: Number of days to look back

        Returns:
            List of (date, value) tuples
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {
                "$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}
                    },
                    "value": {"$avg": f"${metric_name}"},
                }
            },
            {"$sort": {"_id.date": 1}},
        ]

        results = []
        async for doc in self.collection.aggregate(pipeline):
            results.append({"date": doc["_id"]["date"], "value": doc["value"]})

        return results


from datetime import timedelta
